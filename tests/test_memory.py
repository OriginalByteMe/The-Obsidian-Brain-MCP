"""Memory naming and file-format helpers: pure, no Obsidian needed."""

import re

import pytest

from obsidian_brain.exceptions import InvalidArgumentError
from obsidian_brain.memory import (
    display_name,
    frontmatter_block,
    memory_name_of,
    memory_text,
    slugify,
    split_frontmatter,
    utc_now,
)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Project X", "project-x"),
        ("project_x", "project-x"),
        ("PROJECT-X.md", "project-x"),
        ("  spaced   out  ", "spaced-out"),
        ("Dots.in.name", "dots-in-name"),
        ("a.md.md", "a-md"),
        ("../escape", "escape"),
        ("A/B", "a-b"),
        ("日本語 メモ", "日本語-メモ"),
        ("Straße", "strasse"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_slash_and_nothing_stay_different() -> None:
    assert slugify("A/B") != slugify("AB")


def test_nfc_and_nfd_spellings_share_one_slug() -> None:
    assert slugify("Cafe\u0301 notes") == slugify("Caf\u00e9 notes") == "caf\u00e9-notes"
    assert display_name("Cafe\u0301") == "Caf\u00e9"


@pytest.mark.parametrize("name", ["", "   ", "..", "!!!", "💥", "-", ".md", "/"])
def test_names_without_letters_or_digits_are_rejected(name: str) -> None:
    with pytest.raises(InvalidArgumentError, match="no letters or digits"):
        slugify(name)


def test_overlong_names_are_rejected_not_truncated() -> None:
    with pytest.raises(InvalidArgumentError, match="too long"):
        slugify("x" * 300)
    assert slugify("x" * 200) == "x" * 200


def test_slug_is_stable() -> None:
    assert slugify(slugify("Weird  Name!! v2")) == slugify("Weird  Name!! v2")


def test_name_of_a_memory_file_is_its_path_in_the_folder() -> None:
    assert memory_name_of("Obsidian Brain/memories/Capital Name.md") == "Capital Name"
    assert memory_name_of("Obsidian Brain/memories/sub/deep.md") == "sub/deep"


def test_frontmatter_round_trip_with_dashes_in_values_and_body() -> None:
    frontmatter = {"name": "x", "title": "a --- b", "type": "---", "tags": ["a", "b"]}
    text = memory_text(frontmatter, "body\n---\nmore\n")
    block, body = split_frontmatter(text)
    assert block.startswith("---\n") and block.endswith("---\n")
    assert body == "body\n---\nmore\n"
    assert "title: a --- b" in block


def test_split_without_frontmatter_returns_text_untouched() -> None:
    text = "intro\n---\nnot frontmatter\n---\n"
    assert split_frontmatter(text) == ("", text)


@pytest.mark.parametrize(
    ("text", "block", "body"),
    [
        ("---\n---\nbody", "---\n---\n", "body"),
        ("---\na: 1\n---", "---\na: 1\n---", ""),
        ("---\r\na: 1\r\n---\r\n\r\nbody", "---\r\na: 1\r\n---\r\n", "body"),
        ("---\na: 1\n---\nbody", "---\na: 1\n---\n", "body"),
        ("---\na: 1\n--- \nbody", "---\na: 1\n--- \n", "body"),
        ("\ufeff---\na: 1\n---\nbody", "\ufeff---\na: 1\n---\n", "body"),
    ],
)
def test_split_frontmatter_by_lines(text: str, block: str, body: str) -> None:
    assert split_frontmatter(text) == (block, body)


def test_unterminated_frontmatter_is_not_frontmatter() -> None:
    text = "---\na: 1\nbody"
    assert split_frontmatter(text) == ("", text)


def test_frontmatter_block_keeps_order_and_quotes_ambiguous_values() -> None:
    block = frontmatter_block({"z": "NO", "a": "01234", "t": "10:30", "n": 5})
    assert block.splitlines()[1:-1] == ["z: 'NO'", "a: '01234'", "t: '10:30'", "n: 5"]


def test_utc_now_is_real_utc() -> None:
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", utc_now())
