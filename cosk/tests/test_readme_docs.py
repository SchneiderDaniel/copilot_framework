from __future__ import annotations

from pathlib import Path
import re
import tomllib


COSK_DIR = Path(__file__).resolve().parents[1]


def _readme() -> str:
    return (COSK_DIR / "README.md").read_text(encoding="utf-8")


def _client_setup() -> str:
    return (COSK_DIR / "docs" / "client_setup.md").read_text(encoding="utf-8")


def test_readme_contains_required_sections() -> None:
    text = _readme()
    required = [
        "# Cosk",
        "## Installation",
        "## Configuration",
        "## Indexing a target directory",
        "## Starting the MCP server",
        "## Client connection overview",
        "## MCP Tool Reference",
        "## Safety & Guardrails",
        "## Inspecting Cosk locally",
        "## Troubleshooting",
    ]
    for section in required:
        assert section in text


def test_readme_documents_all_tools_with_input_output_example_and_errors() -> None:
    text = _readme()
    for tool_name in (
        "cosk_semantic_search",
        "cosk_get_neighbors",
        "cosk_expand_definition",
        "cosk_find_usage",
    ):
        assert tool_name in text
    assert text.lower().count("input schema") >= 4
    assert text.lower().count("output schema") >= 4
    assert text.lower().count("example request") >= 4
    assert text.lower().count("example response") >= 4
    assert text.lower().count("error behavior") >= 4


def test_readme_accuracy_for_error_behavior_and_top_k() -> None:
    text = _readme()
    assert "top_k=5" in text
    assert "INVALID_PARAMS" in text
    assert "INTERNAL_ERROR" in text
    assert "Notice: You have already traversed this node." in text
    assert "Notice: Depth limit reached." in text
    assert "Unable to read" in text
    assert "Requested line range" in text


def test_guardrails_section_is_present() -> None:
    text = _readme()
    assert "## Safety & Guardrails" in text
    assert "cycle rejection" in text.lower()
    assert "depth-limit" in text.lower()
    assert "record_expand_definition" in text


def test_client_setup_doc_exists_and_contains_steps_and_troubleshooting() -> None:
    text = _client_setup()
    assert "## Prerequisites" in text
    assert "## Step-by-step setup" in text
    assert "mcpServers" in text
    assert "## Troubleshooting" in text


def test_cli_and_json_examples_are_in_fenced_code_blocks() -> None:
    readme = _readme()
    client_setup = _client_setup()
    fenced_blocks = re.findall(r"```(?:bash|json|text)?[\s\S]*?```", readme + "\n" + client_setup)
    assert fenced_blocks
    assert any("python -m cosk.mcp.server" in block for block in fenced_blocks)
    assert any('"mcpServers"' in block for block in fenced_blocks)


def test_readme_does_not_document_daemon_mode() -> None:
    text = _readme().lower()
    assert "daemon mode" not in text
    assert "background daemon" not in text


def test_pyproject_contains_rich_dependency() -> None:
    pyproject = tomllib.loads((COSK_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    assert any(dep.startswith("rich>=13.0,<14.0") for dep in dependencies)
