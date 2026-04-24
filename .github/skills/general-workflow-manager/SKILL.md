---
name: general-general-workflow-manager
description: Expert procedural guidance for deterministic agent orchestration using GitHub Project statuses as gates.
---

# Skill: Workflow Manager

Expert procedural guidance for deterministic agent orchestration using GitHub Project statuses as gates. This skill ensures that agents only run when authorized, fetch context correctly, and advance the project state reliably.

## 🛠️ Prerequisites
- **GitHub CLI (`gh`)**: Must be installed and authenticated.
- **Project Context**: Issues must be assigned to the configured GitHub Project.

## 🧠 Workflow Gates & Transitions

The agentic lifecycle is defined as follows:
1. **Backlog** (Analyst) → Technical Design
2. **Technical Design** (Architect) → Test Design
3. **Test Design** (QA Lead) → Implementation
4. **Implementation** (Developer) → Review
5. **Review** (Auditor) → Done *(if passed)* or **Revision Required** *(if code issues found)*
6. **Revision Required** (Developer) → Review *(loop repeats until Auditor passes)*

> ⚠️ **GitHub Project Setup**: The project board must have a **"Revision Required"** status column for the loop to function. Add it between "Review" and "Done" if it does not exist.

## 🕵️ Workflow Protocols

### 1. Mission Control (Orchestrator Tool)
Run this tool to see the current status and get the command for the next agent.
- **Tool**: `python .github/skills/general-workflow-manager/scripts/mission_control.py <issue_number>`
- **Output**: Returns the current status, authorized agents, and recommended next command.

### 2. The Bootstrap Protocol
Agents MUST call this protocol as their **FIRST** action to verify authorization and ingest mission context.
- **Tool**: `python .github/skills/general-workflow-manager/scripts/bootstrap.py <issue_number> <persona_name>`
- **Behavior**: Verifies the issue status against the persona's "Gate". If successful, it prints the full issue body and comments.

### 3. The Finalization Protocol
Agents MUST call this protocol as their **LAST** action to synchronize results to GitHub and advance the project status.
- **Tool**: `python .github/skills/general-workflow-manager/scripts/finalize.py <issue_number> <outcome> [options]`
- **Options**:
  - `--comment-file <path>`: Path to a file containing the summary to post on GitHub.
  - `--memory-file <path>` *(optional)*: Path to a file containing memory text for optional Myosotis sync if available.
  - `--memory-role <role>` *(optional)*: The agent's role (e.g., `product_owner`, `architect`, `developer`).
  - `--memory-namespace <ns>` *(optional)*: The memory namespace (e.g., `requirements`, `technical_design`).
- **Behavior**: Posts the comment and updates the project status. Optional memory sync can be enabled when Myosotis is available.

## 🛑 Rules of Engagement
- **No Manual Transitions**: Never use `gh project item-edit` manually. Always use the Finalization Protocol.
- **No Manual Context Fetching**: Always use the Bootstrap Protocol to ensure you are working on the correct state.
- **Comment Required**: Always include `--comment-file` in finalization calls.
- **Agent Invocation**: When Mission Control recommends an agent, the Commissioner invokes it directly via the `task` tool (e.g., `agent_type: "analyst"`).

"Order is the foundation of progress."


