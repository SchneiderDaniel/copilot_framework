from __future__ import annotations

from pathlib import Path

from cosk.cli.setup_wizard import agent_instruction_snippet


ROOT = Path(__file__).resolve().parents[2]
COPILOT_INSTRUCTIONS = ROOT / ".github" / "copilot-instructions.md"


def _routing_block(text: str) -> str:
    start = text.index("### Task → tool routing (mandatory)")
    end = text.index("### Available tools")
    return text[start:end].strip()


def test_agent_instruction_snippet_contains_same_task_tool_table() -> None:
    snippet = agent_instruction_snippet("C:/repo/.lancedb")
    for row in (
        "| Symbol by name / substring / regex | `cosk_search_by_name` |",
        "| Concept / \"how does X work\" | `cosk_semantic_search` |",
        "| What calls or depends on X | `cosk_get_neighbors` |",
        "| Where is symbol X used | `cosk_find_usage` |",
        "| Show me the body of X | `cosk_get_symbol_source` |",
        "| Literal string in any file | `grep` |",
    ):
        assert row in snippet
    assert "Never use grep for code exploration. grep is only allowed for searching literal strings in file content." in snippet


def test_agent_instruction_snippet_matches_copilot_instructions_routing_block() -> None:
    instructions = COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")
    snippet = agent_instruction_snippet("C:/repo/.lancedb")
    assert _routing_block(snippet) == _routing_block(instructions)
