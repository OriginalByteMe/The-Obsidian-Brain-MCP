"""
Frozen response shape snapshots for all kept tools.

These snapshots document the expected response structure of each tool
BEFORE the CLI migration begins. They form the migration contract:
post-migration tools must produce responses with identical shapes.

Each shape is a dict mapping key names to their expected types.
Nested structures are represented as dicts-of-types or lists-of-dicts-of-types.

REMOVED tools (not captured):
- search_advanced (Dataview DQL -- removed in migration)
- search_jsonlogic (JsonLogic query -- removed in migration)
- get_periodic_note (generic periodic -- removed in migration)
"""

import pytest


# ---------------------------------------------------------------------------
# Type markers for shape validation
# ---------------------------------------------------------------------------

# Sentinel for "any dict" (frontmatter, vault_stats_at_generation, etc.)
ANY_DICT = {"__any_dict__": True}

# Sentinel for "any value" (dynamic content we don't constrain)
ANY_VALUE = {"__any_value__": True}


# =========================================================================
# VAULT TOOLS (7 tools)
# =========================================================================

VAULT_LIST_VAULT_FILES_SHAPE = {
    "__is_list__": True,
    "item_shape": {
        "name": str,
        "type": str,  # "file" or "folder"
    },
}

VAULT_GET_NOTE_SHAPE = {
    "path": str,
    "content": str,
    "tags": [str],
    "outgoing_links": [str],
    "frontmatter": ANY_DICT,
    "modified": (str, type(None)),  # ISO datetime string or null
}

VAULT_GET_NOTE_ERROR_SHAPE = {
    "error": bool,
    "type": str,  # "NoteNotFoundError"
    "message": str,
}

VAULT_CREATE_NOTE_SHAPE = {
    "success": bool,
    "path": str,
    "message": str,
    "tags": [str],
    "backlinks": [str],
}

VAULT_CREATE_NOTE_ERROR_SHAPE = {
    "error": bool,
    "type": str,  # "InvalidBacklinkError"
    "message": str,
}

VAULT_UPDATE_NOTE_SHAPE = {
    "success": bool,
    "path": str,
    "message": str,
}

VAULT_APPEND_TO_NOTE_SHAPE = {
    "success": bool,
    "path": str,
    "message": str,
    "heading": (str, type(None)),
}

VAULT_REFRESH_VAULT_STRUCTURE_SHAPE = {
    "success": bool,
    "message": str,
    "stats": {
        "total_notes": int,
        "total_folders": int,
        "total_tags": int,
        "total_links": int,
        "orphan_notes": int,
    },
    "refreshed_at": str,  # ISO datetime
}

VAULT_DELETE_NOTE_SHAPE = {
    "success": bool,
    "path": str,
    "message": str,
}


# =========================================================================
# LINK TOOLS (4 tools)
# =========================================================================

LINKS_ADD_BACKLINK_SHAPE = {
    "success": bool,
    "source": str,
    "target": str,
    "message": str,
}

LINKS_ADD_BACKLINK_ERROR_SHAPE = {
    "error": bool,
    "type": str,  # "InvalidBacklinkError" | "NoteNotFoundError" | "LinkAlreadyExistsError"
    "message": str,
}

LINKS_GET_BACKLINKS_SHAPE = {
    "success": bool,
    "path": str,
    "backlinks": [str],
    "count": int,
}

LINKS_GET_OUTGOING_LINKS_SHAPE = {
    "success": bool,
    "path": str,
    "outgoing_links": [str],
    "count": int,
}

LINKS_GET_LINKED_NOTES_SHAPE = {
    "center": str,
    "nodes": [{
        "path": str,
        "depth": int,
    }],
    "edges": [{
        "source": str,
        "target": str,
    }],
}


# =========================================================================
# TAG TOOLS (4 tools)
# =========================================================================

TAGS_ADD_TAGS_SHAPE = {
    "success": bool,
    "path": str,
    "added_tags": [str],
    "all_tags": [str],
    "message": str,
}

TAGS_REMOVE_TAGS_SHAPE = {
    "success": bool,
    "path": str,
    "removed_tags": [str],
    "remaining_tags": [str],
    "message": str,
}

TAGS_LIST_ALL_TAGS_SHAPE = {
    "success": bool,
    "tags": ANY_DICT,  # {tag_name: count, ...}
    "total_unique_tags": int,
    "total_tag_usage": int,
}

TAGS_GET_NOTES_BY_TAG_SHAPE = {
    "success": bool,
    "tag": str,
    "notes": [str],
    "count": int,
}


# =========================================================================
# SEARCH TOOLS (1 kept tool)
# =========================================================================

SEARCH_SEARCH_CONTENT_SHAPE = {
    "success": bool,
    "query": str,
    "results": [{
        "path": str,
        "matches": [str],
        "score": float,
    }],
    "total_matches": int,
}


# =========================================================================
# DAILY TOOLS (3 kept tools)
# =========================================================================

DAILY_GET_DAILY_NOTE_SHAPE = {
    "success": bool,
    "date": str,
    "content": str,
    "tags": [str],
    "frontmatter": ANY_DICT,
}

DAILY_APPEND_TO_DAILY_SHAPE = {
    "success": bool,
    "date": str,
    "heading": (str, type(None)),
    "message": str,
}

DAILY_CREATE_DAILY_ENTRY_SHAPE = {
    "success": bool,
    "date": str,
    "entry": str,
    "timestamp": str,
    "tags": [str],
    "links": [str],
    "message": str,
}


# =========================================================================
# KNOWLEDGE TOOLS (2 tools)
# =========================================================================

KNOWLEDGE_CREATE_VAULT_KNOWLEDGE_BASE_SHAPE = {
    "success": bool,
    "path": str,
    "message": str,
    "stats": {
        "total_notes": int,
        "total_folders": int,
        "total_tags": int,
        "total_links": int,
        "orphan_notes": int,
    },
    "sections_included": {
        "orphans": bool,
        "link_patterns": bool,
    },
}

KNOWLEDGE_GET_KNOWLEDGE_BASE_STATUS_EXISTS_SHAPE = {
    "exists": bool,
    "path": str,
    "created": (str, type(None)),
    "updated": (str, type(None)),
    "generator": (str, type(None)),
    "vault_stats_at_generation": ANY_DICT,
    "recommendation": str,
}

KNOWLEDGE_GET_KNOWLEDGE_BASE_STATUS_MISSING_SHAPE = {
    "exists": bool,
    "path": str,
    "recommendation": str,
}


# =========================================================================
# MEMORY TOOLS (5 tools)
# =========================================================================

MEMORY_LIST_MEMORIES_SHAPE = {
    "count": int,
    "memories": [{
        "name": str,
        "path": str,
        "type": (str, type(None)),
        "created": (str, type(None)),
        "updated": (str, type(None)),
    }],
    "memories_path": str,
}

MEMORY_READ_MEMORY_SHAPE = {
    "name": str,
    "path": str,
    "content": str,
    "type": (str, type(None)),
    "created": (str, type(None)),
    "updated": (str, type(None)),
    "frontmatter": ANY_DICT,
}

MEMORY_WRITE_MEMORY_SHAPE = {
    "success": bool,
    "action": str,  # "created" or "updated"
    "name": str,
    "path": str,
    "message": str,
}

MEMORY_DELETE_MEMORY_SHAPE = {
    "success": bool,
    "name": str,
    "path": str,
    "message": str,
}

MEMORY_EDIT_MEMORY_SHAPE = {
    "success": bool,
    "name": str,
    "path": str,
    "replacements": int,
    "message": str,
}


# =========================================================================
# ONBOARDING TOOLS (3 tools)
# =========================================================================

ONBOARDING_CHECK_ONBOARDING_STATUS_SHAPE = {
    # Shape varies based on onboarding_manager.check_onboarding_status
    # but always includes these keys at minimum:
    "onboarded": bool,
    "message": str,
    "recommendation": str,
}

ONBOARDING_RUN_ONBOARDING_SHAPE = {
    "success": bool,
    "message": str,
    "analysis_summary": {
        "organizational_systems": [str],
        "folder_purposes": ANY_DICT,
        "tag_prefixes": [str],
        "tag_count": int,
        "templates_found": int,
        "naming_patterns": [str],
        "common_frontmatter_keys": [str],
    },
    "files_created": [str],
    "next_steps": [str],
}

ONBOARDING_GET_VAULT_CONFIG_EXISTS_SHAPE = {
    "exists": bool,
    "path": str,
    "content": str,
}

ONBOARDING_GET_VAULT_CONFIG_MISSING_SHAPE = {
    "exists": bool,
    "path": str,
    "message": str,
}


# =========================================================================
# REMOVED TOOLS -- explicitly excluded from migration contract
# =========================================================================

REMOVED_TOOLS = [
    "search_advanced",    # Dataview DQL queries -- removed
    "search_jsonlogic",   # JsonLogic queries -- removed
    "get_periodic_note",  # Generic periodic note retrieval -- removed
]


# =========================================================================
# Master registry: all kept tools and their shapes
# =========================================================================

FROZEN_SHAPES = {
    # Vault tools (7)
    "list_vault_files": VAULT_LIST_VAULT_FILES_SHAPE,
    "get_note": VAULT_GET_NOTE_SHAPE,
    "create_note": VAULT_CREATE_NOTE_SHAPE,
    "update_note": VAULT_UPDATE_NOTE_SHAPE,
    "append_to_note": VAULT_APPEND_TO_NOTE_SHAPE,
    "refresh_vault_structure": VAULT_REFRESH_VAULT_STRUCTURE_SHAPE,
    "delete_note": VAULT_DELETE_NOTE_SHAPE,
    # Link tools (4)
    "add_backlink": LINKS_ADD_BACKLINK_SHAPE,
    "get_backlinks": LINKS_GET_BACKLINKS_SHAPE,
    "get_outgoing_links": LINKS_GET_OUTGOING_LINKS_SHAPE,
    "get_linked_notes": LINKS_GET_LINKED_NOTES_SHAPE,
    # Tag tools (4)
    "add_tags": TAGS_ADD_TAGS_SHAPE,
    "remove_tags": TAGS_REMOVE_TAGS_SHAPE,
    "list_all_tags": TAGS_LIST_ALL_TAGS_SHAPE,
    "get_notes_by_tag": TAGS_GET_NOTES_BY_TAG_SHAPE,
    # Search tools (1 kept)
    "search_content": SEARCH_SEARCH_CONTENT_SHAPE,
    # Daily tools (3 kept)
    "get_daily_note": DAILY_GET_DAILY_NOTE_SHAPE,
    "append_to_daily": DAILY_APPEND_TO_DAILY_SHAPE,
    "create_daily_entry": DAILY_CREATE_DAILY_ENTRY_SHAPE,
    # Knowledge tools (2)
    "create_vault_knowledge_base": KNOWLEDGE_CREATE_VAULT_KNOWLEDGE_BASE_SHAPE,
    "get_knowledge_base_status": KNOWLEDGE_GET_KNOWLEDGE_BASE_STATUS_EXISTS_SHAPE,
    # Memory tools (5)
    "list_memories": MEMORY_LIST_MEMORIES_SHAPE,
    "read_memory": MEMORY_READ_MEMORY_SHAPE,
    "write_memory": MEMORY_WRITE_MEMORY_SHAPE,
    "delete_memory": MEMORY_DELETE_MEMORY_SHAPE,
    "edit_memory": MEMORY_EDIT_MEMORY_SHAPE,
    # Onboarding tools (3)
    "check_onboarding_status": ONBOARDING_CHECK_ONBOARDING_STATUS_SHAPE,
    "run_onboarding": ONBOARDING_RUN_ONBOARDING_SHAPE,
    "get_vault_config": ONBOARDING_GET_VAULT_CONFIG_EXISTS_SHAPE,
}


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture()
def frozen_shapes():
    """Return the complete frozen shapes registry."""
    return FROZEN_SHAPES


@pytest.fixture()
def removed_tools():
    """Return the list of tools explicitly removed in migration."""
    return REMOVED_TOOLS


# =========================================================================
# Snapshot integrity tests
# =========================================================================

class TestSnapshotIntegrity:
    """Verify the snapshot definitions themselves are well-formed."""

    def test_all_kept_tools_have_shapes(self):
        """Every kept tool has a frozen shape entry."""
        assert len(FROZEN_SHAPES) == 29, (
            f"Expected 29 kept tools, got {len(FROZEN_SHAPES)}: {list(FROZEN_SHAPES.keys())}"
        )

    def test_vault_tools_count(self):
        vault_tools = [k for k in FROZEN_SHAPES if k in (
            "list_vault_files", "get_note", "create_note", "update_note",
            "append_to_note", "refresh_vault_structure", "delete_note",
        )]
        assert len(vault_tools) == 7

    def test_link_tools_count(self):
        link_tools = [k for k in FROZEN_SHAPES if k in (
            "add_backlink", "get_backlinks", "get_outgoing_links", "get_linked_notes",
        )]
        assert len(link_tools) == 4

    def test_tag_tools_count(self):
        tag_tools = [k for k in FROZEN_SHAPES if k in (
            "add_tags", "remove_tags", "list_all_tags", "get_notes_by_tag",
        )]
        assert len(tag_tools) == 4

    def test_search_tools_count(self):
        search_tools = [k for k in FROZEN_SHAPES if k in ("search_content",)]
        assert len(search_tools) == 1

    def test_daily_tools_count(self):
        daily_tools = [k for k in FROZEN_SHAPES if k in (
            "get_daily_note", "append_to_daily", "create_daily_entry",
        )]
        assert len(daily_tools) == 3

    def test_knowledge_tools_count(self):
        knowledge_tools = [k for k in FROZEN_SHAPES if k in (
            "create_vault_knowledge_base", "get_knowledge_base_status",
        )]
        assert len(knowledge_tools) == 2

    def test_memory_tools_count(self):
        memory_tools = [k for k in FROZEN_SHAPES if k in (
            "list_memories", "read_memory", "write_memory", "delete_memory", "edit_memory",
        )]
        assert len(memory_tools) == 5

    def test_onboarding_tools_count(self):
        onboarding_tools = [k for k in FROZEN_SHAPES if k in (
            "check_onboarding_status", "run_onboarding", "get_vault_config",
        )]
        assert len(onboarding_tools) == 3

    def test_removed_tools_excluded(self):
        """Removed tools must NOT be in the frozen shapes."""
        for tool_name in REMOVED_TOOLS:
            assert tool_name not in FROZEN_SHAPES, (
                f"Removed tool '{tool_name}' should not be in FROZEN_SHAPES"
            )

    def test_shapes_are_non_empty(self):
        """Every shape has at least one key."""
        for tool_name, shape in FROZEN_SHAPES.items():
            assert isinstance(shape, dict), f"{tool_name} shape must be a dict"
            assert len(shape) > 0, f"{tool_name} shape must not be empty"

    @pytest.mark.parametrize("tool_name", list(FROZEN_SHAPES.keys()))
    def test_shape_keys_are_strings(self, tool_name):
        """All shape keys must be strings."""
        shape = FROZEN_SHAPES[tool_name]
        for key in shape:
            assert isinstance(key, str), (
                f"{tool_name}: shape key {key!r} must be a string"
            )
