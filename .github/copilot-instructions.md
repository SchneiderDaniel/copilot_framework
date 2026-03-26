# 🤖 Project: Copilot Framework

## 🏗️ Framework Overview
This repository is an agentic automation framework designed to orchestrate specialized AI agents and skills for high-fidelity software engineering.

### 🗺️ Repository Structure
1.  **`.github/`**: The core operational layer containing agent definitions, reusable skills, and global context.
2.  **`flask_blogs/`**: A hosted mono-repo project that the framework's agents are currently configured to manage.
    - **Gateway (Nginx)**: Subdomain routing and security headers.
    - **Hippocooking**: JSON-driven NoSQL recipe application.
    - **Planhead**: Strategic calculator suite using a strict Service-Layer pattern.

## ⚙️ Operational Protocols (The Commissioner)
The Main Agent (Gemini CLI) acts as the **Commissioner** (Orchestrator). It manages the high-level project status and delegates complex tasks to specialized detectives through the **Mission Control Protocol**.

**🛑 MANDATORY ORCHESTRATION PROTOCOL**:
1.  **Identify GitHub Issue**: If a user mentions a GitHub issue (e.g., `#123`), the Main Agent MUST call **Mission Control**.
2.  **Mission Control Tool**: `python .gemini/skills/workflow-manager/scripts/mission_control.py <issue_number>`
3.  **Synchronize Context**: If the status is ambiguous, the Main Agent may use `codebase_investigator` to map affected areas before delegating.
4.  **Delegate & Stop**: Use `gemini run <persona_name> <issue_number>`. The Main Agent **MUST NOT** implement the logic directly if an issue is active.

### 🗺️ The Agentic Lifecycle
Each agent (detective) has a specialized role and MUST NOT automatically hand over or call other agents. They MUST use the **Finalization Protocol** to update the state and stop.

1.  **Refinement (Sherlock)**: Understands requirements and defines User Stories.
2.  **Architecture (Mycroft)**: Designs technical solutions and ensures SEO/Security standards.
3.  **Test Design (Lestrade)**: Formulates the empirical verification strategy.
4.  **Implementation (Watson)**: Writes the application code and the tests.
5.  **Audit (Hounds)**: Rigorously verifies the implementation against all designs.

**🛑 AUTOMATION MANDATE**: 
Each agent MUST ONLY perform its own task and MUST stop after finalization. The Commissioner (Main Agent) handles the overall flow.

## 🌍 Agent Environment & Paths
- **Current Project Target**: `flask_blogs` (subdirectory).
- **Tooling Root**: All tools and scripts are called relative to the framework root.
- **Skill Paths**: Reusable skills are located in `.gemini/skills/`.

## 🧭 Navigation for Framework Maintenance
- **Updating Agent Behavior?** Modify the corresponding markdown file in `.gemini/agents/`.
- **Adding a New Skill?** Add a new directory in `.gemini/skills/` with a `SKILL.md` and supporting assets.
- **Global Context?** Update `.gemini/context/env_args.json`.

"The Game is Afoot!"




# ⚙️ Operational Layer: Agent Behavior

## ⚙️ Operational Protocol (Main Agent)
The Main Agent's primary role is **Orchestration** and **Surgical Fixes**. 

- **Orchestration**: For any task linked to a GitHub issue, call `mission_control.py` and delegate to the recommended sub-agent via `gemini run`.
- **Surgical Fixes**: If a task is independent of the agentic workflow (no GitHub issue), follow the **Research -> Strategy -> Execution** lifecycle.
- **No Shadow Implementation**: Never implement logic for an active GitHub issue outside the sub-agent workflow.


## ⚠️ CLI Stability & Tool Safety
To prevent terminal crashes and context bloat:
- **`read_file`**: Never read more than **150 lines** at once. Use `start_line` and `end_line`.
- **`grep_search`**: Minimize `context` (2-3 lines). Use `total_max_matches` and `max_matches_per_file`.
- **`run_shell_command`**: Pipe large outputs to `Select-Object -First 20` (PowerShell) or `head -n 20` (Bash).

"Code is ephemeral; Myosotis is eternal."

