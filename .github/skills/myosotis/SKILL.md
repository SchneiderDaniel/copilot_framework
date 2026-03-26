---
name: myosotis
description: Manage and search persistent agentic memory using the Myosotis MCP server. Use when you need to store architectural decisions, user preferences, or project-specific facts across sessions.
---

# Myosotis Skill

Expert procedural guidance for using the Myosotis Memory Management MCP server.

## Overview
Myosotis is the project's **Long-Term Memory**.

## 🧠 Debugging & Learning Protocol (Developer)
If you (Watson) encounter a bug or failing test and cannot resolve it on your first attempt, you MUST:
1.  **Search Memory**: Use `search_memory` to find past architectural decisions, error messages, or similar past issues.
2.  **Learn**: Once resolved, if the fix was tricky, use `add_memory` (or `finalize.py` with `--memory-file`) to store the solution in the `learnings` namespace.

## Usage Guidelines
- **Project is Boundary**: Always use `flask_blogs` (or sub-project) scope.
- **Role is Perspective**: Use your persona (e.g., `architect`, `developer`).
- **Namespace is Category**:
  - `requirements`: User stories and AC.
  - `technical_design`: Architecture and design patterns.
  - `quality_assurance`: Testing strategies and QA results.
  - `learnings`: Key takeaways and resolved blockers.

## MCP Tools
- `search_memory(query, project, role, limit, filter_by_role)`
- `add_memory(project, role, namespace, text, file_path, line_number)`
- `update_memory(...)`, `delete_memory(...)`, `get_stats(...)`

"Code is ephemeral; Myosotis is eternal."
