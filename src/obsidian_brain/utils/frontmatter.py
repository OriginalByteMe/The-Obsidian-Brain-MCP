"""
Frontmatter manipulation utilities.

Handles YAML frontmatter parsing, modification, and creation
using the python-frontmatter library.
"""

from datetime import datetime

import frontmatter


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
