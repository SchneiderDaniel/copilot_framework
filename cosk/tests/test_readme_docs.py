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
        "## Quick Start",
        "## Configuration",
        "## Indexing options",
        "## Starting the MCP server manually",
        "## Manual client configuration",
        "## MCP Tool Reference",
        "## Safety & Guardrails",
        "## Inspecting the index",
        "## Troubleshooting",
    ]
    for section in required:
        assert section in text


def test_readme_documents_all_tools_with_input_output_example_and_errors() -> None:
    text = _readme()
    for tool_name in (
        "cosk_search_by_name",
        "cosk_semantic_search",
        "cosk_get_neighbors",
        "cosk_get_symbol_source",
        "cosk_find_usage",
    ):
        assert tool_name in text
    assert text.lower().count("- input:") >= 5
    assert text.lower().count("- output:") >= 5
    assert text.lower().count("errors:") >= 5


def test_readme_accuracy_for_error_behavior_and_top_k() -> None:
    text = _readme()
    assert "INVALID_PARAMS" in text
    assert "INTERNAL_ERROR" in text
    assert "Notice: You have already traversed this node." in text
    assert "Notice: Depth limit reached." in text


def test_guardrails_section_is_present() -> None:
    text = _readme()
    assert "## Safety & Guardrails" in text
    assert "cycle" in text.lower()
    assert "depth limit" in text.lower()
    assert "record_source_retrieval" in text


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


def test_readme_documents_cosk_cli_subcommands() -> None:
    text = _readme()
    assert "cosk index" in text
    assert "cosk serve" in text
    assert "cosk inspect" in text


def test_readme_documents_gitignore_behavior_and_cli_opt_out() -> None:
    text = _readme().lower()
    assert ".gitignore" in text
    assert "--no-gitignore" in text


def test_readme_mentions_backward_compatible_python_module_entrypoints() -> None:
    text = _readme()
    assert "python -m cosk.mcp.server" in text
    assert "python -m cosk.inspect" in text


def test_walkthrough_documents_gitignore_layering_and_new_cli() -> None:
    text = (COSK_DIR / "WALKTHROUGH.md").read_text(encoding="utf-8").lower()
    assert ".gitignore" in text
    assert "exclude_dirs" in text
    assert "cosk index" in text
    assert "cosk serve" in text
    assert "cosk inspect" in text


def test_client_setup_includes_generic_mcp_stdio_section() -> None:
    text = _client_setup()
    assert "## Generic MCP stdio setup" in text
    assert "mcp client" in text.lower()


def test_readme_starts_with_plain_language_elevator_pitch() -> None:
    lines = [line for line in _readme().splitlines() if line.strip()]
    assert "stdio transport" not in lines[1].lower()
    assert "helps" in lines[1].lower()


def test_readme_includes_verify_install_with_version_command() -> None:
    text = _readme()
    assert "cosk --version" in text
    assert "Verify installation" in text


def test_readme_documents_cross_platform_venv_steps() -> None:
    text = _readme()
    assert "python -m venv .venv" in text
    assert ".venv\\Scripts\\activate" in text
    assert "source .venv/bin/activate" in text


def test_readme_when_to_use_cosk_vs_grep_references_cosk_search_by_name() -> None:
    text = _readme()
    assert "## When to use cosk vs grep" in text
    assert "| Symbol by name / substring / regex | `cosk_search_by_name` |" in text


def test_readme_keeps_grep_limited_to_literal_file_content_search() -> None:
    text = _readme()
    assert "| Literal string in any file | `grep` |" in text
    assert "Never use grep for code exploration. grep is only allowed for searching literal strings in file content." in text
