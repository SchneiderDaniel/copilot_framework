---
name: general-issue-cutter
description: Splits a large GitHub issue (epic) into smaller, ordered, independently testable sub-issues and creates them on GitHub as sub-issues of the parent epic. Use this skill whenever a user mentions a GitHub issue that is too big, needs to be broken down, split into stories, cut into pieces, or when an issue covers multiple topics (UI, backend, database, infrastructure, etc.). Trigger also when users say things like "break this issue down", "split issue #X", "cut the epic", "decompose this ticket", or "create issues from #X". Always invoke this skill before attempting to analyze or decompose any GitHub issue manually.
---

# Skill: Issue Cutter

Expert procedural guidance for decomposing large GitHub epics into small, ordered, independently testable sub-issues and creating them directly on GitHub as **sub-issues (children) of the parent epic**.

## 🛠️ Prerequisites
- **GitHub CLI (`gh`)**: Must be installed and authenticated (`gh auth status`).
- **Target Repository**: `SchneiderDaniel/copilot_framework` (default). Override if the user specifies another repo.

---

## 🧠 Core Principle: The Vertical Slice

Each sub-issue produced by this skill must be a **vertical slice** — a self-contained unit of work that:
- Has a clear, singular purpose
- Can be implemented and verified in isolation
- Has at least one concrete acceptance criterion that a developer can write a test for
- Does **not** depend on unfinished work from another sub-issue (unless that dependency is explicitly declared)
- Includes **step-by-step human validation instructions** so a reviewer can confirm the slice works without reading code

Avoid horizontal slices (e.g., "do all database changes first"). Prefer vertical slices that touch multiple layers if needed to produce a working, testable outcome. If a slice cannot be tested independently by a human, it is too thin or too abstract — merge it or redesign it.

---

## 🕵️ Decomposition Workflow

### Step 1 — Fetch the Epic

Retrieve the full issue body, labels, and comments:

```powershell
gh issue view <number> --repo SchneiderDaniel/copilot_framework --json title,body,comments,labels
```

Read the entire output carefully before proceeding.

### Step 2 — Explore the Codebase First

⚠️ **MANDATORY before analyzing any epic**: explore the relevant codebase area to understand what already exists. Cutting issues without knowing the current state leads to incorrect sub-issues (e.g., creating a task to "add entity tables" when they already exist).

For each project area touched by the epic:

```powershell
# List top-level structure of the relevant project
Get-ChildItem -Recurse -Depth 2 <project_dir>

# Read key existing files that the epic will extend or depend on
# e.g., db schemas, config models, service modules, existing tests
```

Record what **already exists** vs. what is **genuinely missing**. Sub-issues must only describe work that is not yet done. If a feature is partially implemented, the sub-issue must acknowledge the existing code and describe only the delta.

### Step 3 — Analyze & Categorize

Mentally map the epic across these dimensions:

| Layer | Examples |
|---|---|
| **Data / Database** | Schema changes, migrations, seed data |
| **Backend / API** | Service logic, routes, validation, business rules |
| **Frontend / UI** | Templates, forms, JS interactions, CSS |
| **Infrastructure** | Nginx config, Docker, environment variables |
| **i18n / Content** | Translation strings, locale JSON, Babel pipeline |
| **Testing** | Dedicated test-only work (integration, E2E) |
| **Documentation** | README, inline docs, changelogs |

Not every epic touches all layers. Only create sub-issues for layers that are actually needed.

### Step 4 — Derive Ordered Sub-Issues

Apply these ordering rules:

1. **Foundation first**: data model / schema changes always come before services that use them.
2. **Backend before frontend**: a UI form should not be built before the endpoint it calls exists.
3. **Infrastructure before services**: env vars, feature flags, or config changes needed by code come first.
4. **i18n strings before they are referenced in templates**.
5. **Testing sub-issues** go last if they are standalone, or are embedded into the slice they verify.

For each issue, define:
- **Order number** (1, 2, 3 …) — used only for sequencing; included in the issue body, NOT in the title
- **Title**: short, imperative, descriptive on its own — e.g. `Add recipe_tag column to the database schema`
- **Body**: written as a User Story with Acceptance Criteria (see template below)
- **Layer label** (optional: `database`, `backend`, `frontend`, `infra`, `i18n`, `testing`)

### Step 5 — Confirm with the User (if uncertain)

If the epic is ambiguous or very large (>8 sub-issues), present the proposed decomposition as a numbered list and ask the user to confirm before creating issues:

```
Here is the proposed breakdown for issue #<N>:
1. [database] Add recipe_tag column to the database schema
2. [backend] Implement tag service and API endpoint
3. [frontend] Build tag filter UI component
…
Shall I create these as GitHub issues?
```
…
Shall I create these as GitHub issues?
```

For clear-cut epics (≤8 sub-issues), proceed directly to creation.

### Step 6 — Create Sub-Issues on GitHub

**6a — Create each issue** in order using:

```powershell
gh issue create `
  --repo SchneiderDaniel/copilot_framework `
  --title "<descriptive title>" `
  --body "<body>" `
  --label "<layer-label>"
```

Capture the number returned for each newly created issue.

**6b — Link each new issue as a sub-issue of the epic** using the GitHub GraphQL API.

First, resolve the node IDs:

```powershell
# Get epic node ID
$epicId = (gh api graphql -f query="{ repository(owner: `"SchneiderDaniel`", name: `"copilot_framework`") { issue(number: <EPIC_NUMBER>) { id } } }" | ConvertFrom-Json).data.repository.issue.id

# Get child node ID (use backtick-escaped quotes inside the double-quoted string)
$childId = (gh api graphql -f query="{ repository(owner: `"SchneiderDaniel`", name: `"copilot_framework`") { issue(number: <CHILD_NUMBER>) { id } } }" | ConvertFrom-Json).data.repository.issue.id
```

Then add the sub-issue relationship:

```powershell
gh api graphql -f query="mutation { addSubIssue(input: { issueId: `"$epicId`", subIssueId: `"$childId`" }) { issue { number } subIssue { number } } }"
```

Repeat 6b for every sub-issue created. Titles must stand alone — a developer reading the issue list should understand what needs to be done without any numeric prefix or parent reference. The implementation order is conveyed exclusively through the issue body.

After creating and linking all sub-issues, print a summary table:

```
✅ Sub-issues created under Epic #<original>:
  #101  (1) Add recipe_tag column to the database schema
  #102  (2) Implement tag service and API endpoint
  #103  (3) Build tag filter UI component
  …
```

---

## 📝 Sub-Issue Body Template

Use this template for every sub-issue body. Keep it concise but complete:

```markdown
## Context
_Why this piece of work exists and how it relates to the parent epic._
Parent epic: #<original_issue_number>
Implementation order: <N> of <total> — implement this after issue #<previous_issue_number> (if applicable).

## User Story
As a [role], I want [feature], so that [benefit].

## Acceptance Criteria
- [ ] AC1: <specific, testable condition>
- [ ] AC2: <specific, testable condition>
- [ ] AC3: (add as many as needed)

## How to Validate (Human Tester)
_Step-by-step instructions for a human reviewer to verify this sub-issue is complete and working. Must be executable without reading any code._

1. <setup step — e.g. "Start the app with `docker compose up`">
2. <navigation step — e.g. "Open browser at `http://localhost/feature-page`">
3. <action step — e.g. "Click X / submit form Y / call endpoint Z">
4. <expected result — e.g. "Verify that … appears / returns … / database contains …">
5. <edge case / negative test — e.g. "Submit with empty field → expect error message …">

_Each AC above must map to at least one step here._

## Technical Notes
_Optional: key files, services, or patterns to touch. Keep brief._

## Dependencies
_Optional: list any sub-issues that must be completed before this one._
```

---

## 🛑 Safety & Constraints

- **Never close the original epic** — only the human reviewer may close issues.
- **No artificial cap on sub-issues** — use as many sub-issues as needed to produce well-defined, independently implementable coding tasks. The primary goal is manageability, not brevity. If the epic requires 15–20 slices for clarity, create them all.
- **Each sub-issue must have at least 2 Acceptance Criteria** — if you cannot define them, the slice is too vague; merge it with an adjacent issue.
- **Labels**: only use labels that already exist in the repository. Check with `gh label list --repo SchneiderDaniel/copilot_framework` if unsure.
- **Volume control**: fetch the original issue once; do not re-fetch in a loop.

---

## 💡 Quality Checklist (run mentally before creating)

Before creating any sub-issue, verify:
- [ ] The work it describes is **not already implemented** in the codebase (verified in Step 2)
- [ ] It describes **one** coherent unit of work
- [ ] It has at least **2** concrete, testable acceptance criteria
- [ ] A developer could start on it **today** without waiting for unclear decisions
- [ ] It does not duplicate work in another sub-issue
- [ ] The order number reflects a valid implementation sequence
- [ ] The **How to Validate** section has step-by-step instructions a human can follow **without reading code** to confirm the slice is complete

"A story too big to hold is a story waiting to be told in chapters."
