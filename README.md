# copilot_framework

An agentic automation framework that orchestrates specialized AI agents to manage software projects. It currently tracks two sub-projects as Git submodules:

- **`flask_blogs/`** — A hosted Python/Flask mono-repo (Hippocooking, Planhead, Sudoku). Actively maintained.
- **`lorest/`** — "Local Forest": a privacy-first, fully local desktop application for AI-empowered personal knowledge management. **Early concept stage** — no implementation yet. Planned stack: Tauri + React frontend, FastAPI backend, local LLM inference (Ollama/llama.cpp), SQLite + graph/vector store (Graphiti + LanceDB).

All GitHub Issues for both projects are tracked in this repository: `https://github.com/SchneiderDaniel/copilot_framework/issues`

---

To prevent a "Three Pipe Problem" with submodules, we recommend these global or project-local configurations:

```bash
# Automatically update submodules after a pull—no manual labor required.
git config submodule.recurse true

# Ensure no clues (submodule commits) are left behind before pushing the main case.
git config push.recurseSubmodules check

# View the actual history of changes in submodules during a 'git diff'.
git config diff.submodule log

# Keep a summary of submodule status in your 'git status' reports.
git config status.submoduleSummary true
```