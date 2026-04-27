---
name: general-user-journey-review
description: >
  Conducts a hands-on "Apple-like" UX audit of any project, product, CLI tool, or web app.
  Defines a realistic user persona, then physically navigates the product via playwright-cli
  (web apps) or subprocess (CLI tools), recording every step, confusion point, and friction in
  a SQLite journal. Identifies UX anti-patterns (cognitive overload, hidden features, missing
  feedback, unnecessary steps), scores against Nielsen's 10 heuristics, and produces a
  developer-ready remediation report with concrete mitigations. Optionally creates a GitHub
  issue from the findings.

  Use this skill whenever someone asks to: "review the UX", "user journey review", "walk through
  the app as a user", "is this intuitive?", "find friction points", "make it Apple-like",
  "usability audit", "test the onboarding", "UX check", "what would a new user think?", or
  wants any first-person, experience-based product review. Also invoke when someone says
  "is this easy to use?", "too many steps", "users are confused", or shares a product and
  asks for honest UX feedback. This skill does REAL interaction — not just code reading.
---

# Skill: general-user-journey-review

> **Source**: Inspired by [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (18.5k ⭐) — `categories/04-quality-security/ui-ux-tester.md` + `categories/08-business-product/ux-researcher.md`

The goal of this skill is brutally simple: **become the user**. Not a developer reading code, not a QA
engineer running test scripts — an actual human discovering the product for the first time, trying to
get something done, getting frustrated, succeeding, or giving up.

The north star: **Apple-like UX**. The best products require zero documentation. One path forward is
always obvious. Errors explain themselves. The next step is never in doubt. Use this standard to
evaluate everything.

---

## 🎯 Trigger Conditions

Invoke this skill when the user asks to:
- "Review the UX" / "User journey review" / "Walk through this as a user"
- "Is this intuitive?" / "Make it Apple-like" / "Find friction points"
- "Usability audit" / "What would a new user think?"
- "Test the onboarding" / "Is this easy to use?"
- Any first-person experience-based product review

---

## 📋 Phases

### Phase 0 — Identify the Target

Ask the user (or infer from context) what to test:
- What is the **product/feature/flow** to review? (e.g., "the sudoku app onboarding", "the caveman skill install experience", "the planhead homepage")
- What **entry point** should be used? (URL, CLI command, file path)
- Is there a **specific persona** in mind, or should one be generated?

Run `persona_builder.py` to auto-generate candidate personas from the project:
```bash
python .github/skills/general-user-journey-review/scripts/persona_builder.py \
  --project-path <path> \
  --output .ux-review/personas.json
```

Present the personas to the user. Confirm which persona to embody before proceeding.

---

### Phase 1 — Persona Embodiment

Read the confirmed persona carefully. Internalize:
- Their **technical level** (novice, intermediate, expert)
- Their **goals** — what are they trying to accomplish?
- Their **frustrations** — what would make them give up?
- Their **apple_ux_bar** — do they expect zero docs? Minimal docs? Or are docs acceptable?

From this point forward, **think and act as that persona**. Do not use developer knowledge of the
codebase. If the user wouldn't know it, you don't know it either.

Initialize the journey recorder:
```bash
python .github/skills/general-user-journey-review/scripts/journey_recorder.py init \
  --db .ux-review/journey.db \
  --persona "<persona name>" \
  --target "<what is being tested>" \
  --project-path <path> \
  --app-type <web_app|cli_tool|api|library>
```

---

### Phase 2 — Journey Simulation (The Real Work)

This is the most important phase. **Actually use the product.** Do not theorize — interact.

#### For web apps → use `playwright-cli`

```bash
playwright-cli open <url>
playwright-cli snapshot        # observe what the user sees first
playwright-cli screenshot      # capture the first impression
```

Navigate as the persona would:
- What do you notice first? What draws your eye?
- What do you click first? (Don't overthink — be the user)
- Can you complete the core task without reading documentation?
- Where do you hesitate, get confused, or need to backtrack?

#### For CLI tools → use subprocess / PowerShell

```bash
# What a new user actually does:
<tool> --help                  # Does this explain things clearly?
<tool>                         # What happens with no args?
<tool> <most obvious command>  # Try the intuitive path first
```

Record after **each step** using:
```bash
python .github/skills/general-user-journey-review/scripts/journey_recorder.py step \
  --db .ux-review/journey.db \
  --action "<what you just did>" \
  --description "<what happened>" \
  --tool "playwright|subprocess" \
  --url "<url or command>" \
  --screenshot "<path if any>" \
  --friction 0   # 0=smooth, 1=minor friction, 2=moderate, 3=BLOCKER \
  --time <seconds>
```

Record **every UX issue immediately** when you notice it:
```bash
python .github/skills/general-user-journey-review/scripts/journey_recorder.py issue \
  --db .ux-review/journey.db \
  --step <step_id> \
  --type <issue_type> \
  --severity <1-4> \
  --desc "<what went wrong for the user>" \
  --heuristic "<which Nielsen heuristic is violated>" \
  --mitigation "<concrete fix the developer can implement>" \
  --evidence "<screenshot path, error text, or URL>"
```

**Issue types** (pick the most specific):
`cognitive_overload` | `unclear_label` | `missing_feedback` | `hidden_feature` |
`unnecessary_step` | `error_without_guidance` | `inconsistent_behavior` | `no_undo` |
`jargon` | `slow_response` | `layout_confusion` | `broken_flow` | `documentation_required`

**Severity scale**:
- `1` = Low: minor annoyance, workaround exists
- `2` = Medium: noticeably hurts experience, some users will struggle
- `3` = High: many users will fail or abandon
- `4` = Critical: journey is blocked, task cannot be completed

#### Core journey checklist (go through ALL that apply):

- [ ] **First impression** — What is the product? Is it obvious in 3 seconds?
- [ ] **Zero-to-result** — How many steps from first open to first success?
- [ ] **Error recovery** — Deliberately do something wrong. Is the error helpful?
- [ ] **Hidden features** — Are important features easy to discover?
- [ ] **Labels & copy** — Is every button, label, and message unambiguous?
- [ ] **Feedback loops** — Does every action produce a visible response?
- [ ] **Dead ends** — Can the user always get back or move forward?
- [ ] **Cognitive load** — How much does the user need to hold in their head?
- [ ] **Documentation dependency** — How often would a real user need to read docs?

---

### Phase 3 — Heuristic Scoring

After the journey, score the product against Nielsen's 10 heuristics (0–10 each):

```bash
python .github/skills/general-user-journey-review/scripts/journey_recorder.py heuristic \
  --db .ux-review/journey.db \
  --name "H1: Visibility of system status" \
  --score <0-10> \
  --notes "<evidence>"
```

Score all 10 heuristics (H1–H10). The `ux_analyzer.py` script will use these to compute the
**Apple UX Score** (0–100).

Finalize the journey:
```bash
python .github/skills/general-user-journey-review/scripts/journey_recorder.py finalize \
  --db .ux-review/journey.db
```

---

### Phase 4 — Analysis

Run the analyzer to detect patterns across all recorded issues:

```bash
python .github/skills/general-user-journey-review/scripts/ux_analyzer.py \
  --db .ux-review/journey.db \
  --output .ux-review/analysis.json
```

This computes:
- **Apple UX Score** (0–100): weighted composite of heuristic scores + friction + issues
- **Top anti-patterns**: which issue types recur most
- **Critical path friction**: steps with the highest friction scores
- **Documentation dependency index**: how many steps required docs/help

---

### Phase 5 — Report Generation

Generate the developer-ready report:

```bash
python .github/skills/general-user-journey-review/scripts/report_generator.py \
  --db .ux-review/journey.db \
  --analysis .ux-review/analysis.json \
  --personas .ux-review/personas.json \
  --output .ux-review/ux-review-report.md
```

The report includes:
- Executive summary with Apple UX Score
- Persona used
- Step-by-step journey map with friction indicators
- UX anti-patterns table (severity, heuristic violated, mitigation)
- Heuristic scorecard
- Developer tickets (one per critical/high issue, ready to implement)
- Recommendations roadmap (immediate / short-term / long-term)

Present the report summary to the user in the conversation.

---

### Phase 6 — GitHub Issue (Optional)

Ask the user:
> "Would you like me to create a GitHub issue with these findings so a developer can track and implement the fixes?"

If yes:
```bash
python .github/skills/general-user-journey-review/scripts/issue_creator.py \
  --report .ux-review/ux-review-report.md \
  --title "UX Review: <product/feature> — <N> issues found (Score: X/100)" \
  --repo <owner/repo> \
  --labels "ux,needs-review"
```

---

## 📋 Output Report Format

```markdown
# 🧭 User Journey Review — <Product/Feature>

**Persona**: <name> (<technical level>)  |  **Date**: YYYY-MM-DD
**Apple UX Score**: X/100  |  **Steps**: N  |  **Issues**: N (Critical:N High:N Med:N Low:N)

## Executive Summary
<2-3 sentences: verdict + most impactful finding>

## 👤 Persona
| Field | Value |
|-------|-------|
| Name  | ...   |
| Goals | ...   |
| Frustrations | ... |
| UX Bar | expects_zero_docs |

## 🗺️ Journey Map
| # | Action | Tool | Time | Friction | Notes |
|---|--------|------|------|----------|-------|
| 1 | Opened app | playwright | 2s | 🟢 smooth | ... |
| 2 | Clicked "Start" | playwright | 4s | 🟡 minor | Button label unclear |

## 🚨 UX Anti-Patterns
| # | Severity | Type | Step | Description | Heuristic | Mitigation |
|---|----------|------|------|-------------|-----------|------------|
| 1 | 🔴 Critical | broken_flow | 3 | ... | H3 | ... |

## 📊 Heuristic Scorecard
| Heuristic | Score | Status |
|-----------|-------|--------|
| H1: Visibility of system status | 7/10 | 🟡 |

## 🛠️ Developer Tickets

### [UX-01] <Issue title>
**Severity**: High  |  **Type**: unclear_label  |  **Step**: 2
**Problem**: <what the user experienced>
**Mitigation**: <concrete implementation recommendation>
**Effort**: Small / Medium / Large

## 🎯 Recommendations Roadmap
- **Immediate**: <top 1-2 quick wins>
- **Short-term**: <structural improvements>
- **Long-term**: <deeper redesign items>
```

---

## 📁 Resources

- `scripts/persona_builder.py` — Scans project, generates user personas
- `scripts/journey_recorder.py` — SQLite-backed step & issue recorder (CLI + Python API)
- `scripts/ux_analyzer.py` — Heuristic analysis, Apple UX Score computation
- `scripts/report_generator.py` — Generates full Markdown remediation report
- `scripts/issue_creator.py` — Creates GitHub issue from the report

All output is written to `.ux-review/` in the project root. Add `.ux-review/` to `.gitignore`.

---

## 🍎 The Apple Standard

When writing mitigations, always ask: *"Would Apple ship this?"*

Apple's HIG principles that matter most here:
1. **One obvious path** — never make the user choose between two unclear options
2. **Immediate feedback** — every action has a visible response within 100ms or a progress indicator
3. **Forgiveness** — users can undo, cancel, or back out of anything
4. **Zero jargon** — if a plumber wouldn't understand it, rewrite it
5. **Minimal steps** — if a task takes 5 steps, ask if it can be done in 2
6. **Self-evident UI** — tooltips and docs are a last resort, not a first line of defense
