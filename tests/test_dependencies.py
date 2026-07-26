"""
Dependency hygiene tests.

Verifies that removed REST dependencies (httpx, mcp-use, pytest-httpx) are not
present in the codebase, and that the correct MCP SDK is importable.
"""

import pathlib

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


# --- Import checks ---


def test_mcp_server_fastmcp_importable():
    """The official MCP SDK FastMCP should be importable."""
    from mcp.server.fastmcp import FastMCP  # noqa: F401


def test_mcp_use_not_in_project_deps():
    """mcp-use should not be in project dependencies."""
    content = PYPROJECT.read_text()
    assert "mcp-use" not in content, "mcp-use should not be a project dependency"


# --- Source code checks ---


def _collect_python_files(*dirs: pathlib.Path) -> list[pathlib.Path]:
    """Collect all .py files under the given directories."""
    files = []
    for d in dirs:
        if d.exists():
            files.extend(d.rglob("*.py"))
    return files


FORBIDDEN_IMPORTS = [
    "mcp_use",
    "mcp-use",
    "import httpx",
    "from httpx",
    "pytest_httpx",
    "pytest-httpx",
]


def test_no_forbidden_imports_in_source_or_root():
    """No source or repository-root Python file should import removed dependencies."""
    violations = []
    for py_file in [*_collect_python_files(SRC_DIR), *PROJECT_ROOT.glob("*.py")]:
        content = py_file.read_text()
        for pattern in FORBIDDEN_IMPORTS:
            if pattern in content:
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}: contains '{pattern}'")

    assert violations == [], "Forbidden dependency references found:\n" + "\n".join(violations)


# --- pyproject.toml checks ---


def test_pyproject_no_mcp_use():
    """pyproject.toml should not reference mcp-use."""
    content = PYPROJECT.read_text()
    assert "mcp-use" not in content, "pyproject.toml still contains mcp-use"


def test_pyproject_no_httpx():
    """pyproject.toml should not reference httpx."""
    content = PYPROJECT.read_text()
    assert "httpx" not in content, "pyproject.toml still contains httpx"


def test_pyproject_no_pytest_httpx():
    """pyproject.toml should not reference pytest-httpx."""
    content = PYPROJECT.read_text()
    assert "pytest-httpx" not in content, "pyproject.toml still contains pytest-httpx"


def test_pyproject_pins_mcp_v1():
    """pyproject.toml should stay on the stable MCP SDK v1 line."""
    content = PYPROJECT.read_text()
    assert '"mcp>=1.26.0,<2"' in content, "pyproject.toml must pin mcp>=1.26.0,<2"


# --- Deleted file checks ---


def test_old_client_deleted():
    """The old REST client (client.py) should be deleted."""
    old_client = SRC_DIR / "obsidian_brain" / "client.py"
    assert not old_client.exists(), "src/obsidian_brain/client.py should be deleted"


def test_dockerfile_deleted():
    """Dockerfile should be deleted (CLI is incompatible with Docker)."""
    assert not (PROJECT_ROOT / "Dockerfile").exists(), "Dockerfile should be deleted"


def test_docker_compose_deleted():
    """docker-compose.yml should be deleted."""
    assert not (PROJECT_ROOT / "docker-compose.yml").exists(), (
        "docker-compose.yml should be deleted"
    )


# --- No stale imports of old client ---


def test_no_old_client_imports():
    """No source file should import from .client (the old REST client module)."""
    violations = []
    old_patterns = [
        "from .client import",
        "from ..client import",
        "from obsidian_brain.client import",
    ]
    for py_file in _collect_python_files(SRC_DIR):
        content = py_file.read_text()
        for pattern in old_patterns:
            if pattern in content:
                violations.append(f"{py_file.relative_to(PROJECT_ROOT)}: contains '{pattern}'")

    assert violations == [], "Old client.py imports found:\n" + "\n".join(violations)
