"""Tests for CLI JSON output parsers."""

import json

import pytest

from obsidian_brain.parsers import (
    parse_daily,
    parse_file_list,
    parse_note_read,
    parse_search_results,
    parse_tags,
)


class TestParseNoteRead:
    """Tests for parse_note_read parser."""

    def test_parses_full_note(self, sample_note_json):
        """Should parse a complete note JSON with all fields."""
        result = parse_note_read(sample_note_json)
        assert result["path"] == "Projects/MyProject.md"
        assert "My Project" in result["content"]
        assert result["tags"] == ["project", "active"]
        assert result["frontmatter"]["title"] == "My Project"
        assert result["modified"] == "2026-03-01T10:30:00Z"

    def test_handles_missing_fields(self):
        """Should return defaults for missing fields."""
        result = parse_note_read({"path": "test.md"})
        assert result["path"] == "test.md"
        assert result["content"] == ""
        assert result["tags"] == []
        assert result["frontmatter"] == {}
        assert result["modified"] is None

    def test_handles_empty_dict(self):
        """Should handle completely empty input."""
        result = parse_note_read({})
        assert result["path"] == ""
        assert result["content"] == ""
        assert result["tags"] == []

    def test_parses_from_json_string(self, sample_note_json):
        """Should accept a JSON string input."""
        json_str = json.dumps(sample_note_json)
        result = parse_note_read(json_str)
        assert result["path"] == "Projects/MyProject.md"


class TestParseFileList:
    """Tests for parse_file_list parser."""

    def test_parses_list_of_paths(self, sample_file_list_json):
        """Should return a list of file path strings."""
        result = parse_file_list(sample_file_list_json)
        assert len(result) == 4
        assert "Projects/MyProject.md" in result
        assert "README.md" in result

    def test_handles_empty_list(self):
        """Should return empty list for empty input."""
        result = parse_file_list([])
        assert result == []

    def test_handles_dict_entries(self):
        """Should extract paths from dict entries if needed."""
        data = [
            {"path": "file1.md"},
            {"path": "file2.md"},
        ]
        result = parse_file_list(data)
        assert len(result) == 2
        assert "file1.md" in result

    def test_parses_from_json_string(self, sample_file_list_json):
        """Should accept a JSON string input."""
        json_str = json.dumps(sample_file_list_json)
        result = parse_file_list(json_str)
        assert len(result) == 4


class TestParseSearchResults:
    """Tests for parse_search_results parser."""

    def test_parses_search_results(self, sample_search_json):
        """Should parse search results with path, matches, score."""
        result = parse_search_results(sample_search_json)
        assert len(result) == 2
        assert result[0]["path"] == "Projects/MyProject.md"
        assert len(result[0]["matches"]) > 0
        assert result[0]["score"] == 0.95

    def test_handles_empty_results(self):
        """Should return empty list for no results."""
        result = parse_search_results([])
        assert result == []

    def test_handles_missing_fields(self):
        """Should provide defaults for missing fields in results."""
        data = [{"path": "test.md"}]
        result = parse_search_results(data)
        assert result[0]["path"] == "test.md"
        assert result[0]["matches"] == []
        assert result[0]["score"] == 0.0

    def test_parses_from_json_string(self, sample_search_json):
        """Should accept a JSON string input."""
        json_str = json.dumps(sample_search_json)
        result = parse_search_results(json_str)
        assert len(result) == 2


class TestParseTags:
    """Tests for parse_tags parser."""

    def test_parses_tag_counts(self, sample_tags_json):
        """Should return {tag: count} dict."""
        result = parse_tags(sample_tags_json)
        assert result["project"] == 5
        assert result["active"] == 3
        assert result["daily"] == 15

    def test_handles_empty_dict(self):
        """Should return empty dict for no tags."""
        result = parse_tags({})
        assert result == {}

    def test_handles_list_format(self):
        """Should handle tags as a list of {tag, count} dicts."""
        data = [
            {"tag": "project", "count": 5},
            {"tag": "active", "count": 3},
        ]
        result = parse_tags(data)
        assert result["project"] == 5
        assert result["active"] == 3

    def test_parses_from_json_string(self, sample_tags_json):
        """Should accept a JSON string input."""
        json_str = json.dumps(sample_tags_json)
        result = parse_tags(json_str)
        assert result["project"] == 5


class TestParseDaily:
    """Tests for parse_daily parser."""

    def test_parses_daily_note(self, sample_daily_json):
        """Should parse daily note with content, tags, frontmatter."""
        result = parse_daily(sample_daily_json)
        assert "2026-03-08" in result["content"]
        assert result["tags"] == ["daily"]
        assert result["frontmatter"]["date"] == "2026-03-08"

    def test_handles_missing_fields(self):
        """Should return defaults for missing fields."""
        result = parse_daily({})
        assert result["content"] == ""
        assert result["tags"] == []
        assert result["frontmatter"] == {}

    def test_parses_from_json_string(self, sample_daily_json):
        """Should accept a JSON string input."""
        json_str = json.dumps(sample_daily_json)
        result = parse_daily(json_str)
        assert "2026-03-08" in result["content"]
