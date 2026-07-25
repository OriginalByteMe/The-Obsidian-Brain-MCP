"""Tests for frontmatter tag normalization."""

import frontmatter
import pytest

from obsidian_brain.utils.frontmatter import add_frontmatter_tags, remove_frontmatter_tags


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("---\ntags:\n  - alpha\n  - beta\n---\nBody", ["alpha", "beta", "gamma"]),
        ("---\ntags: alpha, beta\n---\nBody", ["alpha", "beta", "gamma"]),
        ("---\ntags: alpha\n---\nBody", ["alpha", "gamma"]),
        ("---\ntitle: Note\n---\nBody", ["gamma"]),
    ],
)
def test_add_frontmatter_tags_normalizes_supported_tag_shapes(content: str, expected: list[str]):
    post = frontmatter.loads(add_frontmatter_tags(content, ["gamma"]))

    assert post["tags"] == expected
    assert isinstance(post["tags"], list)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("---\ntags:\n  - alpha\n  - beta\n---\nBody", ["alpha"]),
        ("---\ntags: alpha, beta\n---\nBody", ["alpha"]),
        ("---\ntags: beta\n---\nBody", None),
        ("---\ntitle: Note\n---\nBody", None),
    ],
)
def test_remove_frontmatter_tags_normalizes_supported_tag_shapes(
    content: str, expected: list[str] | None
):
    post = frontmatter.loads(remove_frontmatter_tags(content, ["beta"]))

    if expected is None:
        assert "tags" not in post
    else:
        assert post["tags"] == expected
