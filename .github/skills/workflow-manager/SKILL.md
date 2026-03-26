---
name: workflow-manager
description: Expert procedural guidance for deterministic agent orchestration using GitHub Project statuses as gates and Myosotis as persistent memory.
---

# Skill: Workflow Manager

Expert procedural guidance for deterministic agent orchestration using GitHub Project statuses as gates and Myosotis as persistent memory. This skill ensures that agents only run when authorized, fetch context correctly, and advance the project state with atomic synchronization.

## 🛠️ Prerequisites
- **GitHub CLI (`gh`)**: Must be installed and authenticated.
- **Myosotis CLI**: Must be accessible via the project's Python environment.
- **Project Context**: Issues must be assigned to the `flask_blogs` GitHub Project.

## 🧠 Workflow Gates & Transitions

The agentic lifecycle is defined as follows:
1. **Refinement** (Sherlock) -> Technical Design
2. **Technical Design** (Mycroft) -> Test Design
3. **Test Design** (Lestrade) -> Implementation
4. **Implementation** (Watson) -> Audit
5. **Audit** (Hounds) -> Done

## 🕵️ Workflow Protocols

### 1. Mission Control (Orchestrator Tool)
Run this tool to see the current status and get the command for the next agent.
- **Tool**: `python .gemini/skills/workflow-manager/scripts/mission_control.py <issue_number>`
- **Output**: Returns the current status, authorized agents, and recommended next command.

### 2. The Bootstrap Protocol
Agents MUST call this protocol as their **FIRST** action to verify authorization and ingest mission context.
- **Tool**: `python .gemini/skills/workflow-manager/scripts/bootstrap.py <issue_number> <persona_name>`
- **Behavior**: Verifies the issue status against the persona's "Gate". If successful, it prints the full issue body and comments.

### 3. The Finalization Protocol
Agents MUST call this protocol as their **LAST** action to synchronize results to GitHub and Myosotis and advance the project status.
- **Tool**: `python .gemini/skills/workflow-manager/scripts/finalize.py <issue_number> <outcome> [options]`
- **Options**:
  - `--comment-file <path>`: Path to a file containing the summary to post on GitHub.
  - `--memory-file <path>`: Path to a file containing the content to store in Myosotis.
  - `--memory-role <role>`: The agent's role (e.g., `product_owner`, `architect`, `developer`).
  - `--memory-namespace <ns>`: The memory namespace (e.g., `requirements`, `technical_design`).
- **Behavior**: Posts the comment, adds the memory, and updates the project status. Returns success only if ALL steps succeed.

## 🛑 Rules of Engagement
- **No Manual Transitions**: Never use `gh project item-edit` manually. Always use the Finalization Protocol.
- **No Manual Context Fetching**: Always use the Bootstrap Protocol to ensure you are working on the correct state.
- **Atomic Sync**: Always include both the `--comment-file` and `--memory-file` in the finalization call to ensure GitHub and Myosotis are in sync.

"Order is the foundation of progress."
