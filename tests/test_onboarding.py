"""Onboarding heuristics and rendering: pure, no Obsidian needed."""

import random

import yaml

from obsidian_brain.memory import split_frontmatter
from obsidian_brain.onboarding import (
    VaultAnalysis,
    analyze_vault,
    extract_yaml_body,
    render_config,
    render_conventions,
    render_overview,
)

from .fake_vault import FakeVault

NOW = "2026-11-23T03:24:12Z"
REAL_VAULT_FOLDERS = [
    "0 - Maps of Content",
    "1- Projects",
    "2 - Areas",
    "3 - Resources",
    "4 - Permanent",
    "5 - Fleeting",
    "6 - Daily",
    "7 - Archives",
    "Assets",
]


async def analyse(
    files: dict[str, str] | None = None, folders: list[str] | None = None
) -> VaultAnalysis:
    return analyze_vault(await FakeVault(files, folders).snapshot())


async def test_numbered_plural_folders_are_detected_as_para_and_zettelkasten() -> None:
    a = await analyse(folders=REAL_VAULT_FOLDERS)
    assert a.folder_patterns == ["PARA Method", "Zettelkasten"]
    assert a.folder_purposes["1- Projects"] == "Active projects with deadlines"
    assert a.folder_purposes["7 - Archives"] == "Inactive items from other categories"
    assert a.folder_purposes["6 - Daily"] == "Daily notes"
    assert a.folder_purposes["Assets"] == "Images and media"
    assert a.folder_purposes["0 - Maps of Content"] == "Maps of content (index notes)"


async def test_para_survives_emoji_prefixes_and_any_case() -> None:
    a = await analyse(folders=["📁 PROJECTS", "areas", "02_Resources", "Archive"])
    assert a.folder_patterns == ["PARA Method"]


async def test_incomplete_para_is_not_para() -> None:
    assert (await analyse(folders=["Projects", "Areas", "Resources"])).folder_patterns == [
        "Custom/Flat Structure"
    ]


async def test_systems_are_read_from_top_level_folders_only() -> None:
    a = await analyse(folders=["Work/Projects", "Work/Areas", "Work/Resources", "Work/Archive"])
    assert a.folder_patterns == ["Custom/Flat Structure"]


async def test_johnny_decimal_and_ace() -> None:
    assert "Johnny.Decimal" in (await analyse(folders=["10-19 Life", "20-29 Work"])).folder_patterns
    assert (await analyse(folders=["Atlas", "Calendar", "Efforts"])).folder_patterns == [
        "ACE Method"
    ]


async def test_depth_counts_folder_levels() -> None:
    assert (await analyse()).depth_levels == 0
    assert (await analyse(folders=["a"])).depth_levels == 1
    assert (await analyse(folders=["a/b/c/d", "x"])).depth_levels == 4


async def test_empty_vault_is_analysable() -> None:
    a = await analyse()
    assert a.naming_patterns == ["Standard naming"]
    assert a.top_tags == [] and a.common_frontmatter_keys == []


async def test_inline_tags_are_counted() -> None:
    a = await analyse({"a.md": "# A\n\nWorked on #daily and #project/alpha", "b.md": "#daily"})
    assert {t.tag: t.count for t in a.top_tags} == {"daily": 2, "project/alpha": 1}
    assert a.tag_hierarchies == ["project"]


async def test_tags_merge_case_insensitively_and_rank_stably() -> None:
    a = await analyse({"a.md": "#Zed #alpha", "b.md": "#zed #beta"})
    assert [(t.tag, t.count) for t in a.top_tags] == [("Zed", 2), ("alpha", 1), ("beta", 1)]


async def test_tag_prefixes_need_three_uses() -> None:
    files = {f"n{i}.md": f"#status/open #topic/x{i}" for i in range(3)}
    a = await analyse(files)
    assert a.tag_prefixes == ["status", "topic"]
    assert (await analyse({"n.md": "#status/open"})).tag_prefixes == []


async def test_results_do_not_depend_on_file_order() -> None:
    files = {
        f"{folder}/{i}.md": f"---\nstatus: x\nkind: y\n---\n#t{i % 3}/a #u{i % 2}/b"
        for i, folder in enumerate(["B", "A", "C", "A", "B", "C", "A"])
    }
    first = (await analyse(files)).model_dump()
    items = list(files.items())
    for seed in range(5):
        random.Random(seed).shuffle(items)
        assert (await analyse(dict(items))).model_dump() == first


async def test_generated_files_do_not_change_the_analysis() -> None:
    files = {"Home.md": "---\nstatus: a\n---\n#home", "Notes/x.md": "plain"}
    before = await analyse(files)
    generated = {
        "Obsidian Brain/config.md": "```yaml\nversion: 1\n```",
        "Obsidian Brain/memories/conventions.md": "---\ncreated: x\nauto_generated: true\n---\n#tag",
    }
    after = await analyse({**files, **generated})
    assert after == before


async def test_template_folder_must_be_a_folder_named_templates() -> None:
    files = {
        "Notes/old-templates/x.md": "x",
        "Work/Meeting templates/y.md": "y",
        "Resources/Templates/daily.md": "d",
        "Resources/Templates/meeting.md": "m",
    }
    a = await analyse(files)
    assert (a.template_folder, a.template_count) == ("Resources/Templates", 2)
    assert (await analyse({"Notes/old-templates/x.md": "x"})).template_folder is None


async def test_date_named_notes_and_readme_are_not_prefix_naming() -> None:
    files = {f"Daily/2026-11-{day:02d}.md": "x" for day in range(1, 11)} | {"README.md": "r"}
    a = await analyse(files)
    assert not a.uses_prefixes
    assert a.date_format == "YYYY-MM-DD"
    assert "Prefix-based naming" not in a.naming_patterns
    assert "Date-prefixed notes" in a.naming_patterns


async def test_real_prefixes_are_detected() -> None:
    a = await analyse({"MOC - Fiction.md": "x", "01 - Intro.md": "x", "Plain.md": "x"})
    assert a.uses_prefixes


async def test_frontmatter_keys_include_tags_and_respect_the_threshold() -> None:
    files = {f"n{i}.md": "---\ntags: [a]\nstatus: open\n---\nx" for i in range(10)}
    files["odd.md"] = "---\nrare: 1\n---\nx"
    a = await analyse(files)
    assert a.common_frontmatter_keys == ["status", "tags"]
    assert a.frontmatter_patterns == {"status_tracking": "Notes use status/stage tracking"}


def test_extract_yaml_body_finds_the_fence_after_other_text() -> None:
    content = "# My Config\n\nnotes above\n\n```yaml\nversion: 1\nname: x\n```\nnotes below\n"
    assert extract_yaml_body(content) == "version: 1\nname: x"


def test_extract_yaml_body_without_fence_returns_the_text() -> None:
    assert extract_yaml_body("version: 1\n") == "version: 1\n"
    assert extract_yaml_body("```yml\na: 1\n```") == "a: 1"


async def test_config_round_trips_through_its_fence() -> None:
    a = await analyse({"Home.md": "#a"}, REAL_VAULT_FOLDERS)
    config = yaml.safe_load(extract_yaml_body(render_config(a, NOW)))
    assert config["created"] == NOW
    assert config["vault_profile"]["organizational_systems"] == ["PARA Method", "Zettelkasten"]
    assert config["vault_profile"]["depth_levels"] == 1
    assert config["conventions"]["naming_patterns"] == a.naming_patterns


async def test_memories_name_real_folders_and_carry_frontmatter() -> None:
    a = await analyse({"Home.md": "#a"}, REAL_VAULT_FOLDERS)
    overview, conventions = render_overview(a, NOW), render_conventions(a, NOW)
    assert "`6 - Daily/`: Daily notes" in overview
    assert "Place daily notes in `6 - Daily/`" in conventions
    for text, kind in ((overview, "vault-overview"), (conventions, "conventions")):
        block, body = split_frontmatter(text)
        meta = yaml.safe_load(block.strip().strip("-"))
        assert meta["name"] == meta["type"] == kind
        assert meta["created"] == meta["updated"] == NOW
        assert meta["auto_generated"] is True
        assert body.startswith("# ")
