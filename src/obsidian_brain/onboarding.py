"""
Onboarding manager for Obsidian Brain MCP.

Handles vault initialization, configuration, and vault analysis to learn
structure and practices for intelligent vault interactions.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

import yaml

from .models import NoteMetadata, VaultStructure

# Configuration paths within the vault
# Note: Using visible folder (not dot-prefixed) because Obsidian's REST API
# doesn't return hidden folders in directory listings
CONFIG_PATH = "Obsidian Brain/config.yml"
MEMORIES_PATH = "Obsidian Brain/memories"


@dataclass
class VaultAnalysis:
    """Results from analyzing vault structure and practices."""

    # Folder structure analysis
    folder_patterns: list[str] = field(default_factory=list)
    folder_purposes: dict[str, str] = field(default_factory=dict)
    depth_levels: int = 0

    # Tag conventions
    tag_prefixes: list[str] = field(default_factory=list)
    tag_hierarchies: dict[str, list[str]] = field(default_factory=dict)
    top_tags: list[tuple[str, int]] = field(default_factory=list)

    # Template patterns
    templates_found: list[str] = field(default_factory=list)
    template_folder: str | None = None

    # Frontmatter conventions
    common_frontmatter_keys: list[str] = field(default_factory=list)
    frontmatter_patterns: dict[str, str] = field(default_factory=dict)

    # Naming conventions
    naming_patterns: list[str] = field(default_factory=list)
    date_format: str | None = None
    uses_prefixes: bool = False
    uses_ids: bool = False


class OnboardingManager:
    """
    Manages vault onboarding and configuration.

    The onboarding process:
    1. Check if .obsidian-brain/ folder exists
    2. If not, analyze the vault to learn patterns
    3. Create config.yml with vault profile
    4. Generate initial memories about vault structure
    """

    def __init__(self):
        self.config_path = CONFIG_PATH
        self.memories_path = MEMORIES_PATH

    def check_onboarding_status(self, file_list: list[str]) -> dict:
        """
        Check if onboarding has been performed.

        Args:
            file_list: List of file paths in vault root

        Returns:
            Dict with status and recommendations
        """
        has_config = any(f.startswith(".obsidian-brain/") for f in file_list)
        config_exists = CONFIG_PATH in file_list

        if config_exists:
            return {
                "onboarded": True,
                "config_path": CONFIG_PATH,
                "memories_path": MEMORIES_PATH,
                "message": "Vault is already onboarded. Ready to use.",
            }
        elif has_config:
            return {
                "onboarded": False,
                "partial": True,
                "message": (
                    ".obsidian-brain folder exists but config.yml not found. "
                    "Run onboarding to complete setup."
                ),
            }
        else:
            return {
                "onboarded": False,
                "partial": False,
                "message": (
                    "Vault has not been onboarded. Run onboarding to analyze "
                    "vault structure and create configuration."
                ),
                "recommendation": "Call run_onboarding to initialize",
            }

    def analyze_vault(self, structure: VaultStructure) -> VaultAnalysis:
        """
        Analyze vault to learn patterns and conventions.

        Args:
            structure: Cached vault structure with folders and notes

        Returns:
            VaultAnalysis with discovered patterns
        """
        analysis = VaultAnalysis()

        # Analyze folder structure
        analysis = self._analyze_folders(structure, analysis)

        # Analyze tags
        analysis = self._analyze_tags(structure.notes, analysis)

        # Analyze templates
        analysis = self._analyze_templates(structure.notes, analysis)

        # Analyze frontmatter
        analysis = self._analyze_frontmatter(structure.notes, analysis)

        # Analyze naming conventions
        analysis = self._analyze_naming(structure.notes, analysis)

        return analysis

    def _analyze_folders(
        self, structure: VaultStructure, analysis: VaultAnalysis
    ) -> VaultAnalysis:
        """Analyze folder structure for patterns like PARA, Zettelkasten, etc."""
        # Extract folder names at each level
        folder_names: list[str] = []

        def collect_folders(folders, depth=0):
            max_depth = depth
            for folder in folders:
                folder_names.append(folder.name.lower())
                if folder.children:
                    child_depth = collect_folders(folder.children, depth + 1)
                    max_depth = max(max_depth, child_depth)
            return max_depth

        analysis.depth_levels = collect_folders(structure.folders)

        # Detect known patterns
        patterns: list[str] = []

        # PARA method detection
        para_folders = {"projects", "areas", "resources", "archive"}
        if para_folders.issubset(set(folder_names)):
            patterns.append("PARA Method")
            analysis.folder_purposes = {
                "projects": "Active projects with deadlines",
                "areas": "Ongoing areas of responsibility",
                "resources": "Reference materials and topics of interest",
                "archive": "Inactive items from other categories",
            }

        # Zettelkasten detection
        zettel_indicators = {"permanent", "literature", "fleeting", "inbox"}
        if len(zettel_indicators & set(folder_names)) >= 2:
            patterns.append("Zettelkasten")

        # Johnny.Decimal detection (numbered folders like 10-19, 20-29)
        numbered = [f for f in folder_names if re.match(r"^\d{2}-\d{2}$", f)]
        if numbered:
            patterns.append("Johnny.Decimal")

        # ACE method detection
        ace_folders = {"atlas", "calendar", "efforts"}
        if ace_folders.issubset(set(folder_names)):
            patterns.append("ACE Method")

        # Common special folders
        special_folders = {
            "templates": "Note templates",
            "daily": "Daily notes",
            "journal": "Journal entries",
            "attachments": "File attachments",
            "assets": "Images and media",
            "inbox": "Unsorted/new notes",
        }
        for folder, purpose in special_folders.items():
            if folder in folder_names:
                analysis.folder_purposes[folder] = purpose

        analysis.folder_patterns = patterns if patterns else ["Custom/Flat Structure"]
        return analysis

    def _analyze_tags(
        self, notes: list[NoteMetadata], analysis: VaultAnalysis
    ) -> VaultAnalysis:
        """Analyze tag usage patterns."""
        all_tags: list[str] = []
        for note in notes:
            all_tags.extend(note.tags)

        if not all_tags:
            return analysis

        # Count tags
        tag_counts = Counter(all_tags)
        analysis.top_tags = tag_counts.most_common(20)

        # Find hierarchical tags (using /)
        hierarchical = [t for t in all_tags if "/" in t]
        if hierarchical:
            roots: dict[str, list[str]] = {}
            for tag in set(hierarchical):
                root = tag.split("/")[0]
                if root not in roots:
                    roots[root] = []
                roots[root].append(tag)
            analysis.tag_hierarchies = roots

        # Common prefixes (e.g., status/, type/, project/)
        prefix_counts = Counter(t.split("/")[0] for t in hierarchical)
        analysis.tag_prefixes = [p for p, c in prefix_counts.most_common(10) if c >= 3]

        return analysis

    def _analyze_templates(
        self, notes: list[NoteMetadata], analysis: VaultAnalysis
    ) -> VaultAnalysis:
        """Find template patterns in the vault."""
        template_patterns = ["templates/", "template/", "_templates/"]

        for note in notes:
            path_lower = note.path.lower()
            for pattern in template_patterns:
                if pattern in path_lower:
                    analysis.templates_found.append(note.path)
                    # Extract template folder
                    if not analysis.template_folder:
                        idx = path_lower.find(pattern)
                        analysis.template_folder = note.path[: idx + len(pattern) - 1]
                    break

        return analysis

    def _analyze_frontmatter(
        self, notes: list[NoteMetadata], analysis: VaultAnalysis
    ) -> VaultAnalysis:
        """Analyze common frontmatter keys and patterns."""
        key_counts: Counter[str] = Counter()

        for note in notes:
            if note.frontmatter:
                key_counts.update(note.frontmatter.keys())

        # Keys used in at least 10% of notes
        threshold = len(notes) * 0.1 if notes else 0
        common_keys = [k for k, c in key_counts.most_common(20) if c >= threshold]

        analysis.common_frontmatter_keys = common_keys

        # Detect specific patterns
        patterns: dict[str, str] = {}
        if "date" in common_keys or "created" in common_keys:
            patterns["date_tracking"] = "Notes include creation/modification dates"
        if "status" in common_keys or "stage" in common_keys:
            patterns["status_tracking"] = "Notes use status/stage tracking"
        if "project" in common_keys:
            patterns["project_linking"] = "Notes are linked to projects"
        if "author" in common_keys:
            patterns["authorship"] = "Notes track authorship"
        if "aliases" in common_keys:
            patterns["aliases"] = "Notes use aliases for alternate names"

        analysis.frontmatter_patterns = patterns
        return analysis

    def _analyze_naming(
        self, notes: list[NoteMetadata], analysis: VaultAnalysis
    ) -> VaultAnalysis:
        """Analyze note naming conventions."""
        patterns: list[str] = []
        filenames = [note.path.split("/")[-1].replace(".md", "") for note in notes]

        # Date prefixes (YYYY-MM-DD, YYYYMMDD)
        iso_date = re.compile(r"^\d{4}-\d{2}-\d{2}")
        compact_date = re.compile(r"^\d{8}")

        date_prefixed = sum(1 for f in filenames if iso_date.match(f) or compact_date.match(f))
        if date_prefixed > len(filenames) * 0.1:
            patterns.append("Date-prefixed notes")
            if sum(1 for f in filenames if iso_date.match(f)) > date_prefixed / 2:
                analysis.date_format = "YYYY-MM-DD"
            else:
                analysis.date_format = "YYYYMMDD"

        # Zettelkasten IDs (12-14 digit timestamps)
        zettel_id = re.compile(r"^\d{12,14}")
        if sum(1 for f in filenames if zettel_id.match(f)) > len(filenames) * 0.1:
            patterns.append("Zettelkasten IDs")
            analysis.uses_ids = True

        # Prefix patterns (e.g., "MOC -", "[[", numbers)
        prefix_pattern = re.compile(r"^([A-Z]{2,4}|[\[\d]+)")
        if sum(1 for f in filenames if prefix_pattern.match(f)) > len(filenames) * 0.1:
            patterns.append("Prefix-based naming")
            analysis.uses_prefixes = True

        # Title case vs lowercase
        title_case = sum(1 for f in filenames if f[0:1].isupper())
        if title_case > len(filenames) * 0.8:
            patterns.append("Title Case naming")
        elif title_case < len(filenames) * 0.2:
            patterns.append("lowercase naming")

        analysis.naming_patterns = patterns if patterns else ["Standard naming"]
        return analysis

    def generate_config(self, analysis: VaultAnalysis) -> str:
        """
        Generate config.yml content from vault analysis.

        Args:
            analysis: Completed vault analysis

        Returns:
            YAML content for config file
        """
        config = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "vault_profile": {
                "organizational_systems": analysis.folder_patterns,
                "folder_purposes": analysis.folder_purposes,
                "depth_levels": analysis.depth_levels,
            },
            "conventions": {
                "tag_prefixes": analysis.tag_prefixes,
                "tag_hierarchies": list(analysis.tag_hierarchies.keys()),
                "naming_patterns": analysis.naming_patterns,
                "date_format": analysis.date_format,
                "uses_ids": analysis.uses_ids,
                "uses_prefixes": analysis.uses_prefixes,
            },
            "templates": {
                "folder": analysis.template_folder,
                "count": len(analysis.templates_found),
            },
            "frontmatter": {
                "common_keys": analysis.common_frontmatter_keys,
                "patterns": analysis.frontmatter_patterns,
            },
            "autonomy": {
                "session_start_context": "silent",
                "session_end_learning_capture": "prompt",
                "session_end_daily_log": "silent",
                "brag_doc_update": "prompt",
                "periodic_checkin": "prompt",
            },
            "plugin": {
                "checkin_interval_minutes": 30,
                "daily_note_heading": "## Claude Code Sessions",
                "brag_doc_path": None,
                "brag_doc_categories": [
                    "Features Built",
                    "Bugs Fixed",
                    "Improvements",
                    "Key Learnings",
                ],
                "learning_note_folder": None,
                "session_log_format": "summary",
            },
        }

        return yaml.dump(config, default_flow_style=False, sort_keys=False)

    def generate_vault_overview_memory(self, analysis: VaultAnalysis) -> str:
        """
        Generate initial memory about vault structure.

        Args:
            analysis: Completed vault analysis

        Returns:
            Markdown content for vault overview memory
        """
        lines = [
            "---",
            "type: vault-overview",
            f"created: {datetime.now().isoformat()}",
            "auto_generated: true",
            "---",
            "",
            "# Vault Overview",
            "",
            "This vault has been analyzed and the following patterns were discovered.",
            "",
            "## Organizational System",
            "",
        ]

        if analysis.folder_patterns:
            lines.append(f"**Detected Pattern(s)**: {', '.join(analysis.folder_patterns)}")
            lines.append("")

        if analysis.folder_purposes:
            lines.append("**Key Folders**:")
            for folder, purpose in analysis.folder_purposes.items():
                lines.append(f"- `{folder}/`: {purpose}")
            lines.append("")

        lines.append(f"**Folder Depth**: {analysis.depth_levels} levels")
        lines.append("")

        # Tags section
        lines.extend([
            "## Tag Conventions",
            "",
        ])

        if analysis.tag_prefixes:
            lines.append(f"**Tag Prefixes**: {', '.join(f'#{p}/' for p in analysis.tag_prefixes)}")
            lines.append("")

        if analysis.top_tags:
            lines.append("**Top 10 Tags**:")
            for tag, count in analysis.top_tags[:10]:
                lines.append(f"- #{tag} ({count} uses)")
            lines.append("")

        # Naming section
        lines.extend([
            "## Naming Conventions",
            "",
        ])

        if analysis.naming_patterns:
            for pattern in analysis.naming_patterns:
                lines.append(f"- {pattern}")
        if analysis.date_format:
            lines.append(f"- Date format: `{analysis.date_format}`")
        lines.append("")

        # Frontmatter section
        if analysis.common_frontmatter_keys:
            lines.extend([
                "## Frontmatter Conventions",
                "",
                "**Common Keys**: " + ", ".join(f"`{k}`" for k in analysis.common_frontmatter_keys[:10]),
                "",
            ])

            if analysis.frontmatter_patterns:
                for pattern, desc in analysis.frontmatter_patterns.items():
                    lines.append(f"- **{pattern}**: {desc}")
                lines.append("")

        # Templates section
        if analysis.templates_found:
            lines.extend([
                "## Templates",
                "",
                f"**Template Folder**: `{analysis.template_folder}`",
                f"**Templates Found**: {len(analysis.templates_found)}",
                "",
            ])

        lines.extend([
            "---",
            "",
            "*This memory was auto-generated during onboarding. Update as your vault evolves.*",
        ])

        return "\n".join(lines)

    def generate_conventions_memory(self, analysis: VaultAnalysis) -> str:
        """
        Generate memory about vault conventions and best practices.

        Args:
            analysis: Completed vault analysis

        Returns:
            Markdown content for conventions memory
        """
        lines = [
            "---",
            "type: conventions",
            f"created: {datetime.now().isoformat()}",
            "auto_generated: true",
            "---",
            "",
            "# Vault Conventions",
            "",
            "Guidelines for maintaining consistency in this vault.",
            "",
            "## Note Creation",
            "",
        ]

        # Naming guidance
        if analysis.date_format:
            lines.append(f"- Use `{analysis.date_format}` date format for date-prefixed notes")
        if analysis.uses_ids:
            lines.append("- Include Zettelkasten-style timestamp IDs for permanent notes")
        if "Title Case naming" in analysis.naming_patterns:
            lines.append("- Use Title Case for note names")

        lines.append("")

        # Tag guidance
        lines.extend([
            "## Tagging",
            "",
        ])

        if analysis.tag_prefixes:
            lines.append("Use hierarchical tags with these root prefixes:")
            for prefix in analysis.tag_prefixes:
                lines.append(f"- `#{prefix}/...`")
            lines.append("")

        # Frontmatter guidance
        if analysis.common_frontmatter_keys:
            lines.extend([
                "## Frontmatter",
                "",
                "Include these standard frontmatter keys:",
                "",
            ])
            for key in analysis.common_frontmatter_keys[:8]:
                lines.append(f"- `{key}`")
            lines.append("")

        # Folder guidance
        if analysis.folder_purposes:
            lines.extend([
                "## File Organization",
                "",
            ])
            for folder, purpose in analysis.folder_purposes.items():
                lines.append(f"- Place {purpose.lower()} in `{folder}/`")
            lines.append("")

        lines.extend([
            "---",
            "",
            "*Update this memory as conventions evolve.*",
        ])

        return "\n".join(lines)


# Global singleton instance
onboarding_manager = OnboardingManager()
