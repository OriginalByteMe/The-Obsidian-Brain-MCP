"""
Frontmatter manipulation utilities.

Handles YAML frontmatter parsing, modification, and creation
using the python-frontmatter library.
"""

from datetime import datetime

import frontmatter


def parse_note(content: str) -> tuple[dict, str]:
    """
    Parse note into frontmatter dict and body content.

    Args:
        content: Full note content including frontmatter

    Returns:
        Tuple of (frontmatter_dict, body_content)

    Example:
        >>> fm, body = parse_note("---\\ntags: [a, b]\\n---\\n# Title")
        >>> fm
        {'tags': ['a', 'b']}
        >>> body
        '# Title'
    """
    post = frontmatter.loads(content)
    return dict(post.metadata), post.content


def get_frontmatter(content: str) -> dict:
    """
    Extract frontmatter from note content.

    Args:
        content: Full note content

    Returns:
        Frontmatter as dict (empty if none)
    """
    post = frontmatter.loads(content)
    return dict(post.metadata)


def get_body(content: str) -> str:
    """
    Extract body content without frontmatter.

    Args:
        content: Full note content

    Returns:
        Body content only
    """
    post = frontmatter.loads(content)
    return post.content


def add_frontmatter_tags(content: str, new_tags: list[str]) -> str:
    """
    Add tags to note frontmatter, preserving existing tags.

    Args:
        content: Full note content
        new_tags: List of tags to add

    Returns:
        Modified content with updated frontmatter

    Example:
        >>> add_frontmatter_tags("---\\ntags: [a]\\n---\\nBody", ["b", "c"])
        '---\\ntags:\\n- a\\n- b\\n- c\\n---\\nBody'
    """
    post = frontmatter.loads(content)
    existing = post.get("tags", [])

    # Handle case where tags is a single string
    if isinstance(existing, str):
        existing = [existing]

    # Merge and dedupe, preserving order
    combined = list(existing)
    for tag in new_tags:
        if tag not in combined:
            combined.append(tag)

    post["tags"] = sorted(combined)
    return frontmatter.dumps(post)


def remove_frontmatter_tags(content: str, tags_to_remove: list[str]) -> str:
    """
    Remove tags from note frontmatter.

    Args:
        content: Full note content
        tags_to_remove: List of tags to remove

    Returns:
        Modified content with updated frontmatter

    Example:
        >>> remove_frontmatter_tags("---\\ntags: [a, b, c]\\n---\\nBody", ["b"])
        '---\\ntags:\\n- a\\n- c\\n---\\nBody'
    """
    post = frontmatter.loads(content)
    existing = post.get("tags", [])

    # Handle case where tags is a single string
    if isinstance(existing, str):
        existing = [existing]

    # Remove specified tags (case-insensitive)
    tags_lower = [t.lower() for t in tags_to_remove]
    post["tags"] = [t for t in existing if t.lower() not in tags_lower]

    # Remove tags key entirely if empty
    if not post["tags"]:
        del post["tags"]

    return frontmatter.dumps(post)


def set_frontmatter_value(content: str, key: str, value) -> str:
    """
    Set a specific frontmatter value.

    Args:
        content: Full note content
        key: Frontmatter key to set
        value: Value to set

    Returns:
        Modified content with updated frontmatter
    """
    post = frontmatter.loads(content)
    post[key] = value
    return frontmatter.dumps(post)


def remove_frontmatter_key(content: str, key: str) -> str:
    """
    Remove a specific frontmatter key.

    Args:
        content: Full note content
        key: Frontmatter key to remove

    Returns:
        Modified content with key removed
    """
    post = frontmatter.loads(content)
    if key in post.metadata:
        del post[key]
    return frontmatter.dumps(post)


def create_note_with_frontmatter(
    title: str,
    content: str,
    tags: list[str] | None = None,
    extra_frontmatter: dict | None = None,
) -> str:
    """
    Create a new note with proper frontmatter and title.

    Auto-generates a title heading and adds created date.

    Args:
        title: Note title (used for H1 heading)
        content: Main content body (without title)
        tags: Optional list of tags
        extra_frontmatter: Additional frontmatter fields

    Returns:
        Complete note content ready for saving

    Example:
        >>> create_note_with_frontmatter("My Note", "Some content", tags=["a", "b"])
        '---\\ncreated: 2024-01-15\\ntags:\\n- a\\n- b\\n---\\n\\n# My Note\\n\\nSome content'
    """
    fm: dict = {
        "created": datetime.now().strftime("%Y-%m-%d"),
    }

    if tags:
        fm["tags"] = sorted(tags)

    if extra_frontmatter:
        fm.update(extra_frontmatter)

    # Build body with title
    body = f"# {title}\n\n{content}"

    post = frontmatter.Post(body, **fm)
    return frontmatter.dumps(post)


def merge_frontmatter(content: str, new_frontmatter: dict) -> str:
    """
    Merge new frontmatter values into existing frontmatter.

    Existing values are preserved unless overwritten by new_frontmatter.

    Args:
        content: Full note content
        new_frontmatter: Dict of frontmatter values to merge

    Returns:
        Modified content with merged frontmatter
    """
    post = frontmatter.loads(content)

    for key, value in new_frontmatter.items():
        post[key] = value

    return frontmatter.dumps(post)


def has_frontmatter(content: str) -> bool:
    """
    Check if content has frontmatter.

    Args:
        content: Note content to check

    Returns:
        True if content starts with valid frontmatter
    """
    return content.strip().startswith("---")


def ensure_frontmatter(content: str) -> str:
    """
    Ensure content has frontmatter, adding empty block if missing.

    Args:
        content: Note content

    Returns:
        Content with frontmatter (may be empty)
    """
    if has_frontmatter(content):
        return content

    return f"---\n---\n\n{content}"
