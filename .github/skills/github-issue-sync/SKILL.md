---
name: github-issue-sync
description: Fetch and analyze GitHub issues to pull user stories, bug reports, and requirements. Use when the agent needs to synchronize the local development lifecycle with GitHub's source of truth.
---

# Skill: GitHub Issue Sync

Expert procedural guidance for fetching, analyzing, and syncing GitHub issues into the local development lifecycle. This skill enables agents to pull user stories, bug reports, and requirements directly from the source of truth.

## 🛠️ Prerequisites
- **GitHub CLI (`gh`)**: Must be installed and authenticated (`gh auth status`).
- **Repository Context**: 
  - For the main repository: `yet_another_agentic_framework`.
  - For the submodule: `flask_blogs`.
  - **Mandate**: When the user says "git issue" or "git project", they refer to the **flask_blogs** repository. Use `--repo SchneiderDaniel/flask_blogs` for all `gh` commands.

## 🧠 Myosotis Mapping
- **Sherlock (PO)**: Primary user of this skill. Fetches issues to define the "Definition of Ready".
- **Lestrade (QA)**: Uses issue descriptions to build reproduction scripts.

## 🕵️ Sync Workflow

### 1. Fetch Issues
Use the GitHub CLI to list open issues. Always limit the output to prevent context bloat.
```powershell
gh issue list --repo SchneiderDaniel/flask_blogs --limit 10 --json number,title,labels
```

### 2. Inspect a Specific Issue
Once an issue number is identified, fetch the full body and comments.
```powershell
gh issue view <number> --repo SchneiderDaniel/flask_blogs --json title,body,comments,labels,projectItems
```

### 3. Requirements Ingestion (Sherlock)
- **Analyze**: Extract User Stories and Acceptance Criteria (AC) from the issue body.
- **Clarify**: If the issue is underspecified, use `ask_user` to bridge the gap before proceeding.
- **Sync**: Once the requirement is clear, Sherlock MUST store the analyzed requirement in Myosotis using the `add_memory` MCP tool.
  `add_memory(project="flask_blogs", role="sherlock", namespace="requirements", text="Requirement from GH Issue #<number>: [Analyzed Text]")`

### 4. Bug Reproduction (Lestrade)
- **Extract**: Identify the "Steps to Reproduce" from the issue body.
- **Verify**: Create a failing test case based on the issue's description.

### 5. Update Project Status
To change the status of an issue in the GitHub project, use the provided helper script. This script handles the retrieval of internal IDs (Project ID, Item ID, Field ID, Option ID).
```powershell
python .gemini/skills/github-issue-sync/scripts/update_issue_status.py <issue_number> "<target_status>"
```
Example statuses: "Backlog", "Technical Design", "Test Design", "Implementation", "Review", "Done".

## 🛑 Safety & Constraints
- **Read-Only (mostly)**: This skill is primarily for *fetching* context. However, updating project status via the provided script is authorized at the end of a successful agent phase.
- **Volume Control**: Never fetch more than 10 issues at a time.
- **Privacy**: Ensure no sensitive data from the issue body is logged or committed.

"The case begins with a thread, and GitHub is the weaver."
