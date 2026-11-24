"""Every vault operation, as JavaScript run inside Obsidian through `obsidian eval`.

Each `Vault` method is one eval (or one CLI JSON command, for search) against
Obsidian's public plugin API: `app.vault`, `app.metadataCache`, `app.fileManager`
and the daily-notes core plugin's options. Paths are vault-relative and validated
in Python before anything is sent; content travels as a JSON payload, so it is
never re-interpreted (no `\\n`/`\\t` unescaping, no quoting).

Facts about Obsidian's API that shape the JS below (each verified against 1.15):
- `vault.read`/`cachedRead` drop the BOM; `readBinary` + a non-stripping UTF-8 decoder
  returns the exact file text. `vault.process` and `vault.create` keep BOM and CRLF.
- `app.fileManager.processFrontMatter` re-serializes the frontmatter (drops comments,
  turns `01234` into `1234` and `1.10` into `1.1`, mixes CRLF) and deletes a body that
  starts with a `---` block, so frontmatter is edited as text inside `vault.process`.
- `metadataCache.getFileCache(file)` is null or stale for a few ms after a file changes, and its
  offsets count from after a BOM. Code that needs metadata polls until the cache entry's hash is
  that of the bytes on disk now (capped at ~2 s); writes that need none never wait for it.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from .exceptions import InvalidArgumentError, ObsidianCLIError
from .memory import frontmatter_yaml
from .models import (
    FileInfo,
    Link,
    Note,
    SearchHit,
    SearchMatch,
    SearchResults,
    TagChange,
    VaultSnapshot,
)
from .obsidian import ObsidianCLI

# Helpers shared by every eval body. `fail(code, message)` throws an error whose
# `code` ObsidianCLI.eval maps to a typed exception (NOT_FOUND, EXISTS, ...).
_JS_COMMON = r"""
const fail = (code, message) => Object.assign(new Error(message), {code});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const mc = app.metadataCache;
const iso = (ms) => new Date(ms).toISOString();
const getFile = (path) => {
  const f = app.vault.getFileByPath(path);
  if (!f) throw fail('NOT_FOUND', `Note not found: ${path}`);
  return f;
};
const readFile = async (file) => {
  const bytes = await app.vault.readBinary(file);
  try {
    return {bytes, text: new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes)};
  } catch (e) {
    throw fail('INVALID', `${file.path} is not a text file (it is not valid UTF-8).`);
  }
};
const hashOf = async (bytes) =>
  Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map((x) => x.toString(16).padStart(2, '0')).join('');
// Obsidian re-parses a changed file a few ms later: until then `fileCache` keeps the old hash and
// `getFileCache` the old metadata (null for a new file). Metadata is trusted once the cache entry's
// hash is that of the bytes on disk NOW, re-read on every poll because concurrent writers keep
// moving the target. After ~2 s the text comes back with the latest metadata and `ok: false`:
// readers use it as it is, writers that depend on it start over.
const readFresh = async (file) => {
  const start = Date.now();
  for (;;) {
    const {bytes, text} = await readFile(file);
    if (file.extension !== 'md') return {text, cache: null, ok: true};
    const entry = mc.fileCache[file.path];
    const cache = mc.getFileCache(file);
    if (entry && cache && entry.hash === (await hashOf(bytes))) return {text, cache, ok: true};
    const waited = Date.now() - start;
    if (waited > 2000 || (!entry && waited > 300)) return {text, cache, ok: false};  // !entry: not indexed at all
    await sleep(15);
  }
};
// Apply `edit(text, cache)` (the new text, or null to leave the file alone) to the current text and
// its fresh metadata. The write lands only if the file is still exactly `text`; otherwise start
// over, so concurrent writers never lose an update.
const editWithCache = async (file, edit) => {
  const start = Date.now();
  while (Date.now() - start < 15000) {
    const {text, cache, ok} = await readFresh(file);
    if (!ok) continue;
    const result = edit(text, cache);
    if (result === null) return;
    let applied = false;
    await app.vault.process(file, (d) => {
      if (d !== text) return d;
      applied = true;
      return result;
    });
    if (applied) return;
  }
  throw new Error(`Could not update ${file.path}: it keeps changing, or Obsidian has not indexed it; try again.`);
};
// Same wait for many files at once, by mtime/size (cheaper than hashing every file). A file written
// moments ago that has no cache entry yet counts as pending too; an old unindexed one does not.
// `resolvedLinks` is filled in a step after the file cache, so queued link resolution counts as well.
const pending = (f) => {
  if (f.extension !== 'md') return false;
  const entry = mc.fileCache[f.path];
  if (!entry) return Date.now() - f.stat.mtime < 3000;
  return entry.mtime !== f.stat.mtime || entry.size !== f.stat.size || !mc.getFileCache(f) || !(f.path in mc.resolvedLinks);
};
const resolving = () => mc.inProgressTaskCount > 0 || mc.linkResolverQueue?.items?.length > 0;
const settle = async () => {
  const files = app.vault.getMarkdownFiles();
  const start = Date.now();
  while ((resolving() || files.some(pending)) && Date.now() - start < 2000) await sleep(15);
  return files;
};
// The frontmatter `tags` property as Obsidian reads it: any key case, the first such key wins.
// A list, or a text like 'a, b' (kept as tags rather than dropped); `ok` is false for other shapes.
const fmTags = (frontmatter) => {
  const key = Object.keys(frontmatter ?? {}).find((k) => k.toLowerCase() === 'tags');
  const v = key === undefined ? null : frontmatter[key];
  const list = Array.isArray(v) ? v : typeof v === 'string' ? v.split(/[,\s]+/) : v == null ? [] : null;
  const ok = list !== null && list.every((x) => x == null || ['string', 'number'].includes(typeof x));
  return {key, items: ok ? list.filter((x) => x != null).map(String) : [], ok};
};
const cleanTags = (raw) => {
  const seen = new Set();
  const out = [];
  for (const item of raw) {
    const t = item.trim().replace(/^#/, '');
    if (t && !seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); out.push(t); }
  }
  return out;
};
const tagsOf = (cache) => cleanTags([...(cache?.tags ?? []).map((t) => t.tag), ...fmTags(cache?.frontmatter).items]);
const resolve = (link, source) => mc.getFirstLinkpathDest(link.split('#')[0], source)?.path ?? null;
const linksOf = (cache, source) => {
  const out = [];
  const add = (items, kind) => {
    for (const l of items ?? []) out.push({target: resolve(l.link, source), link: l.link, display: l.displayText ?? null, kind});
  };
  add(cache?.links, 'link');
  add(cache?.embeds, 'embed');
  add(cache?.frontmatterLinks, 'frontmatter');
  return out;
};
const noteOf = async (file) => {
  const {text, cache} = await readFresh(file);
  return {
    path: file.path, content: text, frontmatter: cache?.frontmatter ?? {}, tags: tagsOf(cache),
    links: linksOf(cache, file.path), headings: (cache?.headings ?? []).map((h) => h.heading),
    modified: iso(file.stat.mtime), size: file.stat.size,
  };
};
const ensureFolders = async (filePath) => {
  let cur = '';
  for (const part of filePath.split('/').slice(0, -1)) {
    cur = cur ? `${cur}/${part}` : part;
    if (app.vault.getFolderByPath(cur)) continue;
    try { await app.vault.createFolder(cur); } catch (e) { if (!app.vault.getFolderByPath(cur)) throw e; }
  }
};
// Obsidian's `vault.create` checks for an existing file and then writes, so two creates of one path
// can both succeed (the second silently overwrites the first). All evals share this one JS realm:
// creating a path runs one at a time.
const withLock = (key, fn) => {
  const locks = (globalThis.__brainLocks ??= new Map());
  const run = (locks.get(key) ?? Promise.resolve()).then(fn);
  const tail = run.catch(() => {});
  locks.set(key, tail);
  tail.then(() => { if (locks.get(key) === tail) locks.delete(key); });
  return run;
};
"""

# Appending: without a heading, one atomic `vault.process`; with a heading, Obsidian's heading
# positions are applied to the exact text they were computed for (see editWithCache). A missing
# heading is created in the same edit when `input.create` is set, so concurrent callers make one
# section. `input.line` keeps the file's trailing-newline state.
_JS_APPEND = r"""
const eolOf = (text) => (text.includes('\r\n') ? '\r\n' : '\n');
const joinAppend = (d, content, line) => {
  if (d === '') return content;
  if (d.endsWith('\n')) return d + content + (line ? eolOf(d) : '');
  return d + eolOf(d) + content;
};
const addToSection = (text, cache, heading, content, create) => {
  const m = /^(#{1,6})\s+(.*?)\s*$/.exec(heading.trim());
  const level = m ? m[1].length : null;
  const title = m ? m[2] : heading.trim();
  const wanted = title.replace(/\s+#+$/, '').toLowerCase();
  if (!wanted) throw fail('INVALID', 'Heading text must not be empty.');
  const headings = cache?.headings ?? [];
  const i = headings.findIndex((h) => h.heading.trim().toLowerCase() === wanted && (level === null || h.level === level));
  if (i < 0) {
    if (!create) throw fail('HEADING_NOT_FOUND', `Heading not found: ${heading}`);
    const eol = eolOf(text);
    return joinAppend(text, `${text.trim() ? eol : ''}${'#'.repeat(level ?? 2)} ${title}${eol}${eol}${content}`);
  }
  const shift = text.startsWith('\ufeff') ? 1 : 0;  // offsets count from after the BOM
  const next = headings.slice(i + 1).find((h) => h.level <= headings[i].level);
  const start = headings[i].position.end.offset + shift;
  const end = next ? next.position.start.offset + shift : text.length;
  const seg = text.slice(start, end);
  const body = seg.replace(/\s+$/, '');
  return text.slice(0, start) + body + eolOf(text) + content + seg.slice(body.length) + text.slice(end);
};
const appendTo = async (file, content, heading, opts) => {
  if (!heading) {
    await readFile(file);  // refuses bytes that are not UTF-8 text: `process` would re-encode them
    await app.vault.process(file, (d) => joinAppend(d, content, opts.line));
    return;
  }
  await editWithCache(file, (text, cache) => addToSection(text, cache, heading, content, opts.create));
};
// Add `content` as a line unless the note already links to `target` (any link kind). The check and
// the write are one `editWithCache` step, so concurrent callers cannot both add it.
const appendUnlessLinked = async (file, target, content, heading) => {
  let added = false;
  await editWithCache(file, (text, cache) => {
    added = false;
    if (linksOf(cache, file.path).some((l) => l.target === target)) return null;
    added = true;
    return heading ? addToSection(text, cache, heading, content, false) : joinAppend(text, content, true);
  });
  return added;
};
"""

# Frontmatter is edited as text so every line an edit does not own stays byte-identical (comments,
# key order, quoting, number formats, line endings, the BOM). What the properties ARE comes from
# Obsidian's parse (`cache.frontmatter`) and where the block ends from `frontmatterPosition`, so no
# YAML is interpreted here: an entry (key line + continuation lines) is replaced as a whole.
# A `---` block Obsidian did not parse into properties is refused, never edited around: a new
# block put above it would turn it into body text.
_JS_FRONTMATTER = r"""
const EOL_RE = /\r?\n$/;
// An opening `---` line up to the first line that is only `---` (the same rule as memory.py).
const FENCED = /^---[ \t]*\r?\n(?:[^]*?\r?\n)?---[ \t]*(?=\r?\n|$)/;
const keyRe = (key, flags) => new RegExp(`^(?:"${key}"|'${key}'|${key})(?=[ \\t]*:(?:[ \\t\\r\\n]|$))`, flags);
const TAGS_KEY = keyRe('tags', 'i');
const yamlTag = (t) =>
  /^\p{L}[\p{L}\p{N}_\/-]*$/u.test(t) && !/^(?:y|n|yes|no|true|false|on|off|null)$/i.test(t) ? t : JSON.stringify(t);
// The text around the frontmatter block: `lines` is the block (`---`, properties..., `---`; the
// closing fence without its line break) or null when the note has none, `rest` what follows it.
const splitFrontmatter = (file, text, cache) => {
  const bom = text.startsWith('\ufeff') ? '\ufeff' : '';
  const body = text.slice(bom.length);
  let block = cache.frontmatterPosition ? body.slice(0, cache.frontmatterPosition.end.offset) : null;
  if (block === null) {
    const m = FENCED.exec(body);
    if (m) {
      if (m[0].split(/(?<=\n)/).slice(1, -1).some((l) => l.trim() && !l.trimStart().startsWith('#'))) {
        throw fail('INVALID', `${file.path} has frontmatter Obsidian cannot parse (invalid YAML, a duplicate key, or not a list of properties); fix it in Obsidian first.`);
      }
      block = m[0];  // empty or comments only: a block we can put properties into
    }
  }
  const lines = block === null ? null : block.split(/(?<=\n)/);
  const eol = (lines ? lines[0] : body).includes('\r\n') ? '\r\n' : '\n';
  return {bom, lines, eol, rest: body.slice(block === null ? 0 : block.length)};
};
const assemble = (fm, inner, rest) =>
  fm.lines
    ? fm.bom + fm.lines[0] + inner.join('') + fm.lines.at(-1) + rest
    : fm.bom + `---${fm.eol}` + inner.join('') + `---${fm.eol}` + rest;
const entryRange = (inner, re) => {
  const at = inner.findIndex((l) => re.test(l));
  if (at < 0) return null;
  let end = at + 1;
  for (let j = at + 1; j < inner.length; j++) {
    const s = inner[j].replace(EOL_RE, '');
    if (/^[ \t]/.test(s) || /^-([ \t]|$)/.test(s)) end = j + 1;
    else if (s.trim()) break;
  }
  return [at, end];
};
// Replace the entry `re` finds with `build(key text)`'s lines, or add them at the end of the block.
// `parsed`: Obsidian reads the property but no line starts with it (flow or odd layout): refuse.
const putEntry = (inner, re, name, parsed, build) => {
  const range = entryRange(inner, re);
  if (range) inner.splice(range[0], range[1] - range[0], ...build(re.exec(inner[range[0]])[0]));
  else if (parsed) throw fail('INVALID', `The ${name} property is not written as a plain key this tool can edit; fix it in Obsidian first.`);
  else inner.push(...build(name));
};
const setTags = (fm, tags, parsed) => {
  const inner = fm.lines ? fm.lines.slice(1, -1) : [];
  putEntry(inner, TAGS_KEY, 'tags', parsed, (key) =>
    tags.length ? [`${key}:${fm.eol}`, ...tags.map((t) => `  - ${yamlTag(t)}${fm.eol}`)] : [`${key}: []${fm.eol}`]);
  return assemble(fm, inner, fm.rest);
};
// New text for a note: `body` after the frontmatter block (the blank line that follows it is kept,
// or one is added), and each of `props` ({key, entry, replace}) put into the block: written over
// the key's entry when `replace`, only when the key is missing otherwise.
const replaceBody = (file, text, cache, body, props) => {
  const fm = splitFrontmatter(file, text, cache);
  const inner = fm.lines ? fm.lines.slice(1, -1) : [];
  const have = cache.frontmatter ?? {};
  for (const {key, entry, replace} of props) {
    const lines = entry.replace(/\n/g, fm.eol).split(/(?<=\n)/);
    const re = keyRe(key);
    if (replace) putEntry(inner, re, key, Object.hasOwn(have, key), () => lines);
    else if (!entryRange(inner, re) && !Object.hasOwn(have, key)) inner.push(...lines);
  }
  const gap = fm.lines ? /^[ \t]*\r?\n(?:\r?\n)?/.exec(fm.rest)?.[0] ?? fm.eol + fm.eol : fm.eol;
  return assemble(fm, inner, gap + body);
};
"""

# The daily-notes core plugin's file naming and template rendering ({{date}}, {{time}},
# {{title}}, {{date:FMT}}, {{time:FMT}}), for any date.
_JS_DAILY = r"""
const dailyFor = (day) => {
  const plugin = app.internalPlugins.getPluginById('daily-notes');
  if (!plugin?.enabled) throw new Error('The Daily notes core plugin is disabled; enable it in Obsidian Settings > Core plugins.');
  const options = plugin.instance.options ?? {};
  const m = window.moment(day, 'YYYY-MM-DD', true);
  if (!m.isValid()) throw fail('INVALID', `Not a valid date: ${day}`);
  const format = options.format || 'YYYY-MM-DD';
  const folder = (options.folder ?? '').replace(/^\/+|\/+$/g, '');
  return {m, options, format, path: `${folder ? folder + '/' : ''}${m.format(format)}.md`};
};
const renderTemplate = (template, daily) => {
  const title = daily.path.split('/').pop().replace(/\.md$/, '');
  const now = window.moment();
  const date = daily.m.clone().set({hour: now.hour(), minute: now.minute(), second: now.second()});
  return template
    .replace(/{{\s*title\s*}}/gi, title)
    .replace(/{{\s*date\s*}}/gi, title)
    .replace(/{{\s*time\s*}}/gi, now.format('HH:mm'))
    .replace(/{{\s*(?:date|time)\s*:\s*(.+?)\s*}}/gi, (_, fmt) => date.format(fmt));
};
const ensureDaily = (daily) => withLock(daily.path, async () => {
  const existing = app.vault.getFileByPath(daily.path);
  if (existing) return existing;
  let text = '';
  if (daily.options.template) {
    const tpl = mc.getFirstLinkpathDest(daily.options.template.replace(/\.md$/, ''), '');
    if (tpl) text = renderTemplate((await readFile(tpl)).text, daily);
  }
  await ensureFolders(daily.path);
  return await app.vault.create(daily.path, text);
});
"""

_HIDDEN_OR_BAD_SEGMENT = re.compile(r"^\.|^$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
# The file types Obsidian opens (`app.viewRegistry.typeByExtension`). Any other suffix of a new
# note's path is part of its title ("Learning Node.js"), so ".md" is added after it.
_OBSIDIAN_EXTENSIONS = frozenset(
    {"md", "canvas", "base", "pdf", "bmp", "png", "jpg", "jpeg", "gif", "svg", "webp", "avif"}
    | {"mp3", "wav", "m4a", "3gp", "flac", "ogg", "oga", "opus", "mp4", "webm", "ogv", "mov", "mkv"}
)
_TAG = re.compile(r"^[\w/-]+$")
_PROPERTY_KEY = re.compile(r"^[A-Za-z][\w-]*$")


def _clean_path(path: str, *, folder: bool = False) -> str:
    """Return a vault-relative path in NFC, or raise InvalidArgumentError.

    Rejects anything that could leave the vault or touch Obsidian's own config:
    absolute paths, `.`/`..`/empty segments, backslashes, drive letters, control
    characters, and dot-folders (which Obsidian never indexes). With `folder=True`
    the root ("" or "/") is allowed and one trailing slash is dropped. Obsidian stores
    names in NFC, so that is the form every caller (and every response) uses.
    """
    path = unicodedata.normalize("NFC", path)
    if _CONTROL_CHARS.search(path):
        raise InvalidArgumentError("Path must not contain control characters or line breaks.")
    if folder:
        if path in {"", "/"}:
            return ""
        path = path.removesuffix("/")
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or _DRIVE_LETTER.match(path)
        or any(_HIDDEN_OR_BAD_SEGMENT.match(part) or part == ".." for part in path.split("/"))
    ):
        raise InvalidArgumentError(
            "Path must be vault-relative (e.g. 'Folder/Note.md'), stay inside the vault, "
            "and not use hidden (dot) folders."
        )
    return path


def _clean_tags(tags: Sequence[str]) -> list[str]:
    """Strip '#', validate each tag the way Obsidian reads them, drop case-insensitive repeats."""
    unique: dict[str, str] = {}
    for tag in tags:
        name = tag.strip().lstrip("#")
        if not _TAG.match(name) or name.isdigit():
            raise InvalidArgumentError(
                f"Invalid tag {tag!r}: use letters, digits, '_', '-' and '/', not only digits."
            )
        unique.setdefault(name.lower(), name)
    return list(unique.values())


_MAX_MATCH_CHARS = 300


def _snippet(text: str, query: str) -> str:
    """`text`, or ~300 characters of it around the first query word found in it, cut ends marked '…'."""
    if len(text) <= _MAX_MATCH_CHARS:
        return text
    lowered = text.lower()
    words = (w.strip("-/") for w in re.split(r'[\s"()]+', query.lower()) if ":" not in w)
    hits = [i for w in words if w and w != "or" and (i := lowered.find(w)) >= 0]
    start = min(max(0, min(hits, default=0) - _MAX_MATCH_CHARS // 3), len(text) - _MAX_MATCH_CHARS)
    end = start + _MAX_MATCH_CHARS
    return f"{'…' if start else ''}{text[start:end]}{'…' if end < len(text) else ''}"


class Vault:
    """The vault operations tools and resources are built on. Holds no state."""

    def __init__(self, cli: ObsidianCLI | None = None) -> None:
        self.cli = cli if cli is not None else ObsidianCLI()

    async def _eval(
        self, body: str, payload: object = None, *, uses: str = "", idempotent: bool = False
    ) -> Any:
        """Run a body in Obsidian. Only `idempotent` bodies are retried when Obsidian drops the
        reply to a command it already executed (see ObsidianCLI._attempt)."""
        return await self.cli.eval(_JS_COMMON + uses + body, payload, idempotent=idempotent)

    async def _read(self, body: str, payload: object = None, *, uses: str = "") -> Any:
        return await self._eval(body, payload, uses=uses, idempotent=True)

    # -- files and notes ------------------------------------------------------------

    async def list_files(self, folder: str = "", extension: str | None = None) -> list[FileInfo]:
        """Every file under `folder` (recursive; "" is the whole vault), sorted by path."""
        files = await self._read(
            r"""
            if (input.folder && !app.vault.getFolderByPath(input.folder)) {
              throw fail('NOT_FOUND', `Folder not found: ${input.folder}`);
            }
            return app.vault.getFiles()
              .filter((f) => !input.folder || f.path.startsWith(input.folder + '/'))
              .filter((f) => !input.extension || f.extension.toLowerCase() === input.extension)
              .map((f) => ({path: f.path, extension: f.extension, size: f.stat.size, modified: iso(f.stat.mtime)}))
              .sort((a, b) => (a.path < b.path ? -1 : 1));
            """,
            {
                "folder": _clean_path(folder, folder=True),
                "extension": extension.lstrip(".").lower() if extension else None,
            },
        )
        return [FileInfo.model_validate(f) for f in files]

    async def read_note(self, path: str) -> Note:
        """Read any text file with Obsidian's parsed metadata.

        Raises NoteNotFoundError for a missing file and InvalidArgumentError for a binary one.
        """
        result = await self._read(
            "return await noteOf(getFile(input.path));", {"path": _clean_path(path)}
        )
        return Note.model_validate(result)

    async def write_note(self, path: str, content: str, overwrite: bool = False) -> str:
        """Create a note (and its folders), or replace it when `overwrite` is true.

        A path whose suffix is not a file type Obsidian opens (md, canvas, png, pdf, ...) gets
        ".md", so "Learning Node.js" is a note. Content is written exactly as given.
        Raises NoteExistsError if the note exists and `overwrite` is false. Returns the final path.
        """
        clean = _clean_path(path)
        if PurePosixPath(clean).suffix.lstrip(".").lower() not in _OBSIDIAN_EXTENSIONS:
            clean += ".md"
        return str(
            await self._eval(
                r"""
                const exists = () => fail('EXISTS', `Note already exists: ${input.path}; pass overwrite=true to replace it.`);
                return await withLock(input.path, async () => {
                  const existing = app.vault.getFileByPath(input.path);
                  if (existing) {
                    if (!input.overwrite) throw exists();
                    await app.vault.modify(existing, input.content);
                  } else {
                    await ensureFolders(input.path);
                    await app.vault.create(input.path, input.content);
                  }
                  return input.path;
                });
                """,
                {"path": clean, "content": content, "overwrite": overwrite},
                idempotent=overwrite,
            )
        )

    async def append(
        self,
        path: str,
        content: str,
        heading: str | None = None,
        *,
        create_heading: bool = False,
        as_line: bool = False,
    ) -> None:
        """Append `content` atomically, separated from the existing text by one newline.

        With `heading` (text, with or without leading '#'s; case-insensitive) the content goes
        at the end of that section, before the next heading of the same or a higher level.
        A missing heading raises HeadingNotFoundError, or with `create_heading` is added at the
        end of the note (`##` unless the heading carries its #s) in the same atomic edit.
        `as_line` ends the content with a newline when the note ended with one. A file that is not
        UTF-8 text is refused with InvalidArgumentError, never rewritten.
        """
        await self._eval(
            "await appendTo(getFile(input.path), input.content, input.heading, input); return null;",
            {
                "path": _clean_path(path),
                "content": content,
                "heading": heading or None,
                "create": create_heading,
                "line": as_line,
            },
            uses=_JS_APPEND,
        )

    async def append_unless_linked(
        self, path: str, target: str, content: str, heading: str | None = None
    ) -> bool:
        """Append `content` as a line unless the note already links to `target`; True if added.

        `target` is a vault path. The check (every link, embed and frontmatter link, resolved the
        way Obsidian resolves them) and the write are one atomic edit, so concurrent calls for
        one target add exactly one line. With `heading` the line goes at the end of that section,
        which must exist (HeadingNotFoundError otherwise). Same file rules as `append`.
        """
        return bool(
            await self._eval(
                "return await appendUnlessLinked(getFile(input.path), input.target, input.content, input.heading);",
                {
                    "path": _clean_path(path),
                    "target": _clean_path(target),
                    "content": content,
                    "heading": heading or None,
                },
                uses=_JS_APPEND,
            )
        )

    async def replace_body(
        self,
        path: str,
        body: str,
        *,
        properties: Mapping[str, object] | None = None,
        defaults: Mapping[str, object] | None = None,
    ) -> None:
        """Replace the text after the frontmatter block and set properties, in one atomic edit.

        `properties` are written (the key's whole entry is replaced, or added at the end of the
        block), `defaults` only where the key is missing. Every other frontmatter line, the line
        endings and the BOM stay byte-identical; the blank line after the block is kept. A note
        without a block gets one. Raises InvalidArgumentError for a file that is not UTF-8
        markdown text, a `---` block Obsidian cannot read as properties, or a property it cannot
        edit in place (flow-style or nested layouts).
        """
        props = [
            {"key": key, "entry": frontmatter_yaml({key: value}), "replace": replace}
            for source, replace in ((defaults, False), (properties, True))
            for key, value in (source or {}).items()
        ]
        for prop in props:
            if not _PROPERTY_KEY.match(str(prop["key"])):
                raise InvalidArgumentError(f"Invalid property name {prop['key']!r}.")
        await self._eval(
            r"""
            const file = getFile(input.path);
            if (file.extension !== 'md') throw fail('INVALID', 'Only markdown notes have frontmatter.');
            await editWithCache(file, (text, cache) => replaceBody(file, text, cache, input.body, input.props));
            return null;
            """,
            {"path": _clean_path(path), "body": body, "props": props},
            uses=_JS_FRONTMATTER,
            idempotent=True,  # the same body and properties give the same text, however often
        )

    async def delete(self, path: str, permanent: bool = False) -> None:
        """Move a file to Obsidian's trash, or delete it for good when `permanent` is true."""
        await self._eval(
            """
            const file = getFile(input.path);
            if (input.permanent) await app.vault.delete(file);
            else await app.fileManager.trashFile(file);
            return null;
            """,
            {"path": _clean_path(path), "permanent": permanent},
        )

    async def update_tags(
        self, path: str, add: Sequence[str] = (), remove: Sequence[str] = ()
    ) -> TagChange:
        """Add and remove frontmatter tags in one atomic edit, touching the file only on a change.

        Tags are read from Obsidian's parsed `tags` property (any key case); when they change,
        that whole entry is rewritten as a block list and every other line stays byte-identical.
        Tags are validated like Obsidian reads them, `#` stripped, repeats ignoring case dropped.
        Raises InvalidArgumentError for no tags, a tag in both lists, a file that is not UTF-8
        text, a `tags` property that is not a list, or a `---` block at the top that Obsidian
        cannot read as properties (a second block would hide it). Returns the tags after the call
        and what actually changed.
        """
        to_add, to_remove = _clean_tags(add), _clean_tags(remove)
        if not to_add and not to_remove:
            raise InvalidArgumentError("Pass at least one tag in `add` or `remove`.")
        if clash := {t.lower() for t in to_add} & {t.lower() for t in to_remove}:
            raise InvalidArgumentError(
                f"Tag in both `add` and `remove`: {', '.join(sorted(clash))}."
            )
        result = await self._eval(
            r"""
            const file = getFile(input.path);
            if (file.extension !== 'md') throw fail('INVALID', 'Only markdown notes have frontmatter.');
            const norm = (t) => t.toLowerCase();
            const drop = new Set(input.remove.map(norm));
            let result = null;
            await editWithCache(file, (text, cache) => {
              const fm = splitFrontmatter(file, text, cache);
              const {key, items, ok} = fmTags(cache.frontmatter);
              if (!ok) throw fail('INVALID', 'The tags property is not a list this tool can edit; fix it in Obsidian first.');
              const current = cleanTags(items);
              const have = new Set(current.map(norm));
              const added = input.add.filter((t) => !have.has(norm(t)));
              const removed = current.filter((t) => drop.has(norm(t)));
              const tags = [...current.filter((t) => !drop.has(norm(t))), ...added];
              result = {tags, added, removed};
              return added.length || removed.length ? setTags(fm, tags, key !== undefined) : null;
            });
            return result;
            """,
            {"path": _clean_path(path), "add": to_add, "remove": to_remove},
            uses=_JS_FRONTMATTER,
            idempotent=True,
        )
        return TagChange.model_validate(result)

    # -- links ----------------------------------------------------------------------

    async def outgoing_links(self, path: str) -> list[Link]:
        """Links, embeds and frontmatter links of a note, in document order per kind."""
        result = await self._read(
            "const file = getFile(input.path); return linksOf((await readFresh(file)).cache, file.path);",
            {"path": _clean_path(path)},
        )
        return [Link.model_validate(link) for link in result]

    async def backlinks(self, path: str) -> list[str]:
        """Paths of the notes linking to `path` (a note may link to itself), sorted.

        Read from Obsidian's resolved-link index, so it costs one pass over the notes, not a
        resolution of every link in the vault.
        """
        result = await self._read(
            """
            const target = getFile(input.path);
            await settle();
            return Object.entries(mc.resolvedLinks).filter(([, links]) => links[target.path]).map(([source]) => source).sort();
            """,
            {"path": _clean_path(path)},
        )
        return [str(source) for source in result]

    async def resolve_link(self, link: str, source_path: str) -> str:
        """Resolve a wikilink-style name or path (`Note`, `Folder/Note`, `Note#Heading`) to a path.

        Resolution matches Obsidian's: case-insensitive, shortest-path, relative to `source_path`.
        Raises NoteNotFoundError when nothing matches.
        """
        if not link.strip() or _CONTROL_CHARS.search(link):
            raise InvalidArgumentError("Link target must be non-empty single-line text.")
        return str(
            await self._read(
                """
                const dest = resolve(input.link.split('|')[0], input.source);
                if (!dest) throw fail('NOT_FOUND', `No note matches the link: ${input.link}`);
                return dest;
                """,
                {
                    "link": unicodedata.normalize("NFC", link),
                    "source": _clean_path(source_path, folder=True),
                },
            )
        )

    async def link_text(self, target_path: str, source_path: str) -> str:
        """The shortest unambiguous wikilink text for `target_path`, as written from `source_path`."""
        return str(
            await self._read(
                "return mc.fileToLinktext(getFile(input.target), input.source, true);",
                {
                    "target": _clean_path(target_path),
                    "source": _clean_path(source_path, folder=True),
                },
            )
        )

    # -- tags -----------------------------------------------------------------------

    async def tags(self) -> dict[str, int]:
        """Every tag (no '#') with Obsidian's occurrence count, nested tags also counted in their parents.

        A note that uses a tag twice counts twice, exactly as Obsidian's own tag pane counts.
        """
        result = await self._read(
            "await settle(); return Object.fromEntries(Object.entries(mc.getTags()).map(([k, v]) => [k.replace(/^#/, ''), v]));"
        )
        return {str(tag): int(count) for tag, count in result.items()}

    async def notes_with_tag(self, tag: str, include_nested: bool = True) -> list[str]:
        """Paths of notes carrying `tag` (case-insensitive), including `tag/child` if `include_nested`."""
        (name,) = _clean_tags([tag])
        result = await self._read(
            """
            const want = input.tag.toLowerCase();
            const out = [];
            for (const f of await settle()) {
              const hit = tagsOf(mc.getFileCache(f)).some((t) => {
                const low = t.toLowerCase();
                return low === want || (input.nested && low.startsWith(want + '/'));
              });
              if (hit) out.push(f.path);
            }
            return out.sort();
            """,
            {"tag": name, "nested": include_nested},
        )
        return [str(p) for p in result]

    # -- search ---------------------------------------------------------------------

    async def search(self, query: str, folder: str | None = None, limit: int = 20) -> SearchResults:
        """Obsidian search (its query syntax) with matching lines, at most `limit` files.

        A matching line longer than ~300 characters is cut to a window around the first query
        word found in it, with '…' marking the cut.
        """
        if not query.strip():
            raise InvalidArgumentError("Search query must not be empty.")
        if _CONTROL_CHARS.search(query):
            raise InvalidArgumentError(
                "Search query must not contain control characters or line breaks."
            )
        if limit < 1:
            raise InvalidArgumentError("limit must be at least 1.")
        # Ask for one file more than `limit`: that is how truncation is known exactly.
        args = ["search:context", f"query={query}", "format=json", f"limit={limit + 1}"]
        if folder and (clean := _clean_path(folder, folder=True)):
            args.append(f"path={clean}")
        output = (await self.cli.run(*args, idempotent=True)).strip()
        if not output or output == "No matches found.":
            return SearchResults(hits=[], truncated=False)
        try:
            raw = json.loads(output)
            merged: dict[str, list[SearchMatch]] = {}
            for entry in raw:
                seen = merged.setdefault(entry["file"], [])
                for m in entry["matches"]:
                    match = SearchMatch(line=m["line"], text=_snippet(m["text"], query))
                    if match not in seen:
                        seen.append(match)
        except (ValueError, KeyError, TypeError):
            raise ObsidianCLIError("Unreadable search output from the Obsidian CLI.") from None
        hits = [SearchHit(path=path, matches=matches) for path, matches in merged.items()]
        return SearchResults(hits=hits[:limit], truncated=len(hits) > limit)

    # -- daily notes ----------------------------------------------------------------

    async def daily_path(self, day: date) -> str:
        """Where the daily note for `day` lives, per the daily-notes folder and date format."""
        return str(
            await self._read(
                "return dailyFor(input.day).path;", {"day": day.isoformat()}, uses=_JS_DAILY
            )
        )

    async def read_daily(self, day: date) -> Note | None:
        """The daily note for `day`, or None when it does not exist. Never creates it."""
        result = await self._read(
            """
            const file = app.vault.getFileByPath(dailyFor(input.day).path);
            return file ? await noteOf(file) : null;
            """,
            {"day": day.isoformat()},
            uses=_JS_DAILY,
        )
        return Note.model_validate(result) if result else None

    async def append_daily(self, content: str, day: date, heading: str | None = None) -> str:
        """Append to the daily note for `day`, creating it from the daily-notes template first.

        Works for any date. A `heading` that the note lacks is added at its end in the same atomic
        edit (`append` with `create_heading`). Returns the note's path.
        """
        return str(
            await self._eval(
                """
                const daily = dailyFor(input.day);
                await appendTo(await ensureDaily(daily), input.content, input.heading, input);
                return daily.path;
                """,
                {
                    "day": day.isoformat(),
                    "content": content,
                    "heading": heading or None,
                    "create": True,
                    "line": False,
                },
                uses=_JS_DAILY + _JS_APPEND,
            )
        )

    # -- whole-vault ----------------------------------------------------------------

    async def snapshot(self, folder: str = "") -> VaultSnapshot:
        """Every markdown note (metadata, no content) and folder, in one eval.

        `folder` limits both to paths under it (the folder itself is not listed).
        """
        result = await self._read(
            """
            const under = (p) => !input.folder || p.startsWith(input.folder + '/');
            await settle();
            const notes = [], folders = [];
            for (const f of app.vault.getAllLoadedFiles()) {
              if (f.path === '/' || !under(f.path)) continue;
              if ('children' in f) { folders.push(f.path); continue; }
              if (f.extension !== 'md') continue;
              const c = mc.getFileCache(f);
              notes.push({
                path: f.path, size: f.stat.size, modified: iso(f.stat.mtime), frontmatter: c?.frontmatter ?? {},
                tags: tagsOf(c), links: linksOf(c, f.path), headings: (c?.headings ?? []).map((h) => h.heading),
              });
            }
            const byPath = (a, b) => (a.path < b.path ? -1 : 1);
            return {notes: notes.sort(byPath), folders: folders.sort()};
            """,
            {"folder": _clean_path(folder, folder=True)},
        )
        return VaultSnapshot.model_validate(result)


@functools.cache
def get_vault() -> Vault:
    """The server's one Vault (it holds no state), shared by tools and resources."""
    return Vault()
