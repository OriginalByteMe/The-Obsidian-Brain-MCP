"""
Wikilink parsing and manipulation utilities.

Handles extraction, injection, and resolution of Obsidian [[wikilinks]].
"""

import re

# Pattern to match [[wikilinks]] with optional aliases [[note|alias]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def extract_wikilinks(content: str) -> list[str]:
    """
    Extract all [[wikilink]] targets from content.

    Handles aliases: [[note|display text]] extracts "note"

    Args:
        content: Markdown content to parse

    Returns:
        List of link targets (note names/paths)

    Example:
        >>> extract_wikilinks("See [[Note A]] and [[Folder/Note B|alias]]")
        ['Note A', 'Folder/Note B']
    """
    return WIKILINK_PATTERN.findall(content)


def contains_wikilink(content: str, target: str) -> bool:
    """
    Check if content contains a wikilink to the specified target.

    Args:
        content: Markdown content to search
        target: Note name/path to look for

    Returns:
        True if a wikilink to target exists

    Example:
        >>> contains_wikilink("See [[Note A]]", "Note A")
        True
        >>> contains_wikilink("See [[Note A|alias]]", "Note A")
        True
    """
    links = extract_wikilinks(content)
    # Case-insensitive comparison
    target_lower = target.lower()
    return any(link.lower() == target_lower for link in links)


def inject_wikilink(
    content: str,
    target: str,
    context: str = "",
    section: str = "See Also",
) -> str:
    """
    Inject a [[wikilink]] into content.

    Adds to existing section or creates a new "See Also" section at the end.

    Args:
        content: Original markdown content
        target: Note name/path to link to
        context: Optional context text before the link
        section: Section heading to add under (default: "See Also")

    Returns:
        Modified content with injected link

    Example:
        >>> inject_wikilink("# Title\\n\\nContent", "Related Note")
        '# Title\\n\\nContent\\n\\n## See Also\\n\\n- [[Related Note]]\\n'

        >>> inject_wikilink("# Title", "Note", context="Related to")
        '# Title\\n\\n## See Also\\n\\n- Related to [[Note]]\\n'
    """
    # Build the link line
    link = f"[[{target}]]"
    link_line = f"- {context} {link}" if context else f"- {link}"

    # Check for existing section (case-insensitive)
    section_pattern = re.compile(
        rf"^(#{{1,6}})\s*{re.escape(section)}\s*$", re.MULTILINE | re.IGNORECASE
    )
    match = section_pattern.search(content)

    if match:
        # Found existing section - insert after it
        # Find where the section content ends (next heading or EOF)
        section_start = match.end()
        heading_level = len(match.group(1))

        # Find next heading of same or higher level
        next_heading_pattern = re.compile(rf"^#{{{1},{heading_level}}}\s+", re.MULTILINE)
        next_match = next_heading_pattern.search(content, section_start)

        if next_match:
            # Insert before next heading
            insert_pos = next_match.start()
            # Find last non-whitespace before next heading
            before = content[:insert_pos].rstrip()
            after = content[insert_pos:]
            return f"{before}\n{link_line}\n\n{after}"
        else:
            # No next heading, append to end
            return f"{content.rstrip()}\n{link_line}\n"
    else:
        # Create new section at end
        return f"{content.rstrip()}\n\n## {section}\n\n{link_line}\n"


def create_wikilink(target: str, alias: str | None = None) -> str:
    """
    Create a wikilink string.

    Args:
        target: Note name/path to link to
        alias: Optional display text

    Returns:
        Formatted wikilink string

    Example:
        >>> create_wikilink("Folder/Note")
        '[[Folder/Note]]'
        >>> create_wikilink("Folder/Note", "My Note")
        '[[Folder/Note|My Note]]'
    """
    if alias:
        return f"[[{target}|{alias}]]"
    return f"[[{target}]]"
