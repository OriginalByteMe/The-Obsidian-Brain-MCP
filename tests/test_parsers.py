"""Tests for Obsidian CLI text parsers."""

import pytest

from obsidian_brain.parsers import parse_daily, parse_note_read, parse_search_results


class TestParseNoteRead:
    def test_parses_yaml_frontmatter_and_list_tags(self):
        raw = (
            "---\n"
            "tags:\n"
            "  - project\n"
            "  - active\n"
            "title: My Project\n"
            "status: active\n"
            "---\n"
            "# My Project\n\nBody\n"
        )

        result = parse_note_read(raw, path="Projects/MyProject.md")

        assert result == {
            "path": "Projects/MyProject.md",
            "raw": raw,
            "content": "# My Project\n\nBody\n",
            "tags": ["project", "active"],
            "frontmatter": {"title": "My Project", "status": "active"},
            "modified": None,
        }

    def test_normalizes_comma_separated_tags(self):
        result = parse_note_read(
            "\n---\ntags: project, active\n---\nBody",
            path="Note.md",
        )

        assert result["tags"] == ["project", "active"]

    def test_malformed_frontmatter_falls_back_to_raw_content(self):
        raw = "---\ntags: [broken\n---\n# Readable\n"

        assert parse_note_read(raw, path="Broken.md") == {
            "path": "Broken.md",
            "raw": raw,
            "content": raw,
            "tags": [],
            "frontmatter": {},
            "modified": None,
        }

    def test_unterminated_frontmatter_falls_back_to_raw_content(self):
        raw = "---\ntags: project\n# Never closed\n"

        assert parse_note_read(raw, path="Unterminated.md") == {
            "path": "Unterminated.md",
            "raw": raw,
            "content": raw,
            "tags": [],
            "frontmatter": {},
            "modified": None,
        }

    def test_without_frontmatter_keeps_the_return_shape(self):
        result = parse_note_read("# Plain note", path="Plain.md")

        assert result == {
            "path": "Plain.md",
            "raw": "# Plain note",
            "content": "# Plain note",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        }

    def test_rejects_known_cli_preamble_before_frontmatter(self):
        raw = "Your Obsidian installer is out of date.\n---\ntags: existing\n---\nBody"

        with pytest.raises(ValueError, match="preamble"):
            parse_note_read(raw, path="Note.md")

    def test_preserves_horizontal_rule_without_known_preamble(self):
        result = parse_note_read("# Plain note\n\n---\n\nBody", path="Plain.md")

        assert result["content"] == "# Plain note\n\n---\n\nBody"


class TestParseSearchResults:
    def test_groups_grep_style_matches_by_path(self):
        output = (
            "Projects/MyProject.md:7: first matching line\n"
            "Projects/MyProject.md:11: second matching line\n"
            "Archive/Old.md:2: archived match\n"
        )

        assert parse_search_results(output) == [
            {
                "path": "Projects/MyProject.md",
                "matches": ["first matching line", "second matching line"],
                "score": 0.0,
            },
            {
                "path": "Archive/Old.md",
                "matches": ["archived match"],
                "score": 0.0,
            },
        ]

    def test_keeps_colons_in_paths(self):
        assert parse_search_results("Notes/release:2026.md:7: hit") == [
            {
                "path": "Notes/release:2026.md",
                "matches": ["hit"],
                "score": 0.0,
            }
        ]

    def test_keeps_colons_in_paths_and_match_text(self):
        assert parse_search_results("Notes/release:2026:plan.md:7: status:2027: ready") == [
            {
                "path": "Notes/release:2026:plan.md",
                "matches": ["status:2027: ready"],
                "score": 0.0,
            }
        ]

    def test_includes_non_markdown_search_hits(self):
        output = "Board.canvas:1: needle\nQueries/Tasks.base:3: needle too\n"

        assert parse_search_results(output) == [
            {"path": "Board.canvas", "matches": ["needle"], "score": 0.0},
            {"path": "Queries/Tasks.base", "matches": ["needle too"], "score": 0.0},
        ]

    def test_keeps_an_empty_match_line(self):
        assert parse_search_results("Note.md:7:") == [
            {"path": "Note.md", "matches": [""], "score": 0.0}
        ]

    def test_ignores_non_grep_text_including_legacy_json(self):
        assert parse_search_results("") == []
        assert parse_search_results('[{"path": "Legacy.md"}]') == []


class TestParseDaily:
    def test_parses_yaml_frontmatter_and_list_tags(self):
        result = parse_daily(
            "---\ntags:\n  - daily\n  - journal\nmood: focused\n---\n# Today",
        )

        assert result == {
            "content": "# Today",
            "tags": ["daily", "journal"],
            "frontmatter": {"mood": "focused"},
        }

    def test_normalizes_comma_separated_tags(self):
        result = parse_daily("---\ntags: daily, journal\n---\n# Today")

        assert result["tags"] == ["daily", "journal"]

    def test_malformed_frontmatter_falls_back_to_raw_content(self):
        raw = "---\ntags: [broken\n---\n# Today\n"

        assert parse_daily(raw) == {
            "content": raw,
            "tags": [],
            "frontmatter": {},
        }

    def test_without_frontmatter_keeps_the_return_shape(self):
        assert parse_daily("# Today") == {
            "content": "# Today",
            "tags": [],
            "frontmatter": {},
        }
