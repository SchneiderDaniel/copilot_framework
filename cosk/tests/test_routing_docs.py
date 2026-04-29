from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COPILOT_INSTRUCTIONS = ROOT / ".github" / "copilot-instructions.md"


def _instructions_text() -> str:
    return COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")


def test_copilot_instructions_contains_mandatory_task_tool_table() -> None:
    text = _instructions_text()
    expected_rows = [
        "| Symbol by name / substring / regex | `cosk_search_by_name` |",
        "| Concept / \"how does X work\" | `cosk_semantic_search` |",
        "| What calls or depends on X | `cosk_get_neighbors` |",
        "| Where is symbol X used | `cosk_find_usage` |",
        "| Show me the body of X | `cosk_get_symbol_source` |",
        "| Literal string in any file | `grep` |",
    ]
    assert "| Task | Tool |" in text
    for row in expected_rows:
        assert row in text


def test_copilot_instructions_contains_hard_grep_prohibition() -> None:
    text = _instructions_text()
    assert "Never use grep for code exploration. grep is only allowed for searching literal strings in file content." in text


def test_copilot_instructions_removes_old_vague_routing_prose() -> None:
    text = _instructions_text()
    old_phrases = [
        "### Tool preference (mandatory)",
        "Choose the right tool based on query type",
        "do **not** default to grep for everything",
        "Do not use `cosk_semantic_search` for exact name lookups",
    ]
    for phrase in old_phrases:
        assert phrase not in text
