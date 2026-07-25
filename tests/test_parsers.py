"""Tests for Obsidian CLI text parsers."""

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

    def test_without_frontmatter_keeps_the_return_shape(self):
        assert parse_daily("# Today") == {
            "content": "# Today",
            "tags": [],
            "frontmatter": {},
        }
