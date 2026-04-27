#!/usr/bin/env python3
"""
report_generator.py — Generates a developer-ready Markdown UX review report.

Usage:
    python report_generator.py \
        --db .ux-review/journey.db \
        --analysis .ux-review/analysis.json \
        --personas .ux-review/personas.json \
        --output .ux-review/ux-review-report.md
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


SEVERITY_EMOJI = {1: "🔵 Low", 2: "🟡 Medium", 3: "🟠 High", 4: "🔴 Critical"}
FRICTION_EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_db_summary(db_path: str) -> dict:
    """Pull raw steps and issues from DB via JourneyDB."""
    sys.path.insert(0, str(Path(__file__).parent))
    from journey_recorder import JourneyDB
    db = JourneyDB(db_path)
    s = db.summary()
    db.close()
    return s


def find_persona(personas_data: dict, persona_name: str) -> dict | None:
    for p in personas_data.get("personas", []):
        if persona_name.lower() in p["name"].lower() or persona_name.lower() in p["id"].lower():
            return p
    return personas_data.get("personas", [None])[0]


def render_journey_map(steps: list) -> str:
    if not steps:
        return "_No steps recorded._\n"
    lines = ["| # | Action | Tool | Time | Friction | Notes |",
             "|---|--------|------|------|----------|-------|"]
    for s in steps:
        f = int(s.get("friction_score", 0))
        emoji = FRICTION_EMOJI.get(min(f, 3), "⚪")
        tool = s.get("tool_used", "") or "—"
        time_s = s.get("time_seconds", 0)
        time_str = f"{time_s:.0f}s" if time_s else "—"
        notes = s.get("notes", "") or s.get("description", "") or "—"
        notes = notes[:80] + "…" if len(notes) > 80 else notes
        action = s.get("action", "")[:80]
        lines.append(f"| {s['id']} | {action} | {tool} | {time_str} | {emoji} | {notes} |")
    return "\n".join(lines) + "\n"


def render_anti_patterns(anti_patterns: list) -> str:
    if not anti_patterns:
        return "_No anti-patterns detected. 🍎 Apple-level UX!_\n"
    lines = ["| # | Pattern | Occurrences | Max Severity | Apple Principle |",
             "|---|---------|-------------|-------------|-----------------|"]
    for i, p in enumerate(anti_patterns, 1):
        sev = SEVERITY_EMOJI.get(p["max_severity"], "?")
        principle = p["apple_principle"][:70] + "…" if len(p["apple_principle"]) > 70 else p["apple_principle"]
        lines.append(f"| {i} | **{p['pattern']}** | {p['occurrence_count']} | {sev} | _{principle}_ |")
    return "\n".join(lines) + "\n"


def render_issues_table(issues: list) -> str:
    if not issues:
        return "_No UX issues recorded._\n"
    lines = ["| # | Severity | Type | Step | Description | Heuristic | Mitigation |",
             "|---|----------|------|------|-------------|-----------|------------|"]
    for i, iss in enumerate(issues, 1):
        sev = SEVERITY_EMOJI.get(min(iss["severity"], 4), "?")
        itype = iss.get("issue_type", "?").replace("_", " ")
        desc = iss.get("description", "")[:80] + "…" if len(iss.get("description", "")) > 80 else iss.get("description", "")
        heuristic = iss.get("heuristic_violated", "—")[:30]
        mitigation = iss.get("mitigation", "—")[:80] + "…" if len(iss.get("mitigation", "")) > 80 else iss.get("mitigation", "—")
        lines.append(f"| {i} | {sev} | {itype} | {iss.get('step_id','?')} | {desc} | {heuristic} | {mitigation} |")
    return "\n".join(lines) + "\n"


def render_heuristic_scorecard(scorecard: list) -> str:
    lines = ["| Heuristic | Score | Bar | Status |",
             "|-----------|-------|-----|--------|"]
    for h in scorecard:
        score = f"{h['score']}/10" if h['score'] is not None else "—"
        bar = h.get("bar", "")
        lines.append(f"| {h['heuristic']} | {score} | `{bar}` | {h['status']} |")
    return "\n".join(lines) + "\n"


def render_developer_tickets(tickets: list) -> str:
    if not tickets:
        return "_No actionable tickets generated._\n"
    sections = []
    for t in tickets:
        sev_label = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}.get(t["severity"], "?")
        evidence = f"\n**Evidence**: {t['evidence']}" if t.get("evidence") else ""
        heuristic = f"\n**Heuristic**: {t['heuristic']}" if t.get("heuristic") else ""
        sections.append(
            f"### [{t['id']}] {t['title']}\n"
            f"**Severity**: {sev_label}  |  **Type**: `{t['issue_type']}`  |  "
            f"**Effort**: {t['effort']}  |  **Step**: {t['step_id']}\n\n"
            f"**Problem**: {t['problem']}{evidence}{heuristic}\n\n"
            f"**Mitigation**: {t['mitigation']}\n"
        )
    return "\n---\n\n".join(sections)


def render_persona(persona: dict | None) -> str:
    if not persona:
        return "_Persona not available._\n"
    goals = "\n".join(f"  - {g}" for g in persona.get("goals", []))
    frustrations = "\n".join(f"  - {f}" for f in persona.get("frustrations", []))
    return (
        f"| Field | Value |\n|-------|-------|\n"
        f"| **Name** | {persona.get('name', '?')} |\n"
        f"| **Role** | {persona.get('role', '?')} |\n"
        f"| **Technical Level** | {persona.get('technical_level', '?')} |\n"
        f"| **UX Bar** | `{persona.get('apple_ux_bar', '?')}` |\n"
        f"| **Context** | {persona.get('context', '?')} |\n"
        f"| **Device** | {persona.get('device', '?')} |\n\n"
        f"**Goals:**\n{goals}\n\n**Frustrations:**\n{frustrations}\n"
    )


def build_executive_summary(score_data: dict, anti_patterns: list, issue_count: int, step_count: int) -> str:
    score = score_data["score"]
    grade = score_data["grade"]
    emoji = score_data["emoji"]
    breakdown = score_data["breakdown"]
    critical = breakdown["critical_issues"]
    high = breakdown["high_issues"]

    top_issue = anti_patterns[0]["pattern"] if anti_patterns else "none"
    doc_dep = score_data.get("doc_dependency", {})

    lines = [
        f"**Apple UX Score: {score}/100 {emoji} — {grade}**\n",
        f"The review covered **{step_count} steps** and identified **{issue_count} UX issues** "
        f"({critical} critical, {high} high-priority).",
    ]
    if critical > 0:
        lines.append(f"⚠️ **{critical} critical issue(s) block the core journey** and must be fixed immediately.")
    if anti_patterns:
        lines.append(
            f"The most impactful anti-pattern is **{top_issue}** — "
            f"see the Anti-patterns section for details and mitigations."
        )
    if score >= 85:
        lines.append("Overall the product is near Apple-level intuitiveness. Minor polish is all that's needed.")
    elif score >= 70:
        lines.append("The product is functional and largely intuitive, but a few recurring friction points hurt the experience.")
    elif score >= 55:
        lines.append("Noticeable friction throughout. Addressing the high-priority issues will significantly improve the experience.")
    else:
        lines.append("The user journey has fundamental UX problems that will cause abandonment. A targeted redesign of the critical path is recommended.")
    return "\n".join(lines) + "\n"


def build_recommendations(anti_patterns: list, tickets: list) -> str:
    immediate = [t for t in tickets if t["severity"] >= 4]
    short_term = [t for t in tickets if t["severity"] == 3]
    long_term = [t for t in tickets if t["severity"] <= 2]

    def fmt(items):
        if not items:
            return "  - _None identified_"
        return "\n".join(f"  - [{t['id']}] {t['title']} _{t['effort']}_" for t in items)

    return (
        f"- **Immediate** (this sprint — critical blockers):\n{fmt(immediate)}\n\n"
        f"- **Short-term** (next 1-2 sprints — high friction):\n{fmt(short_term)}\n\n"
        f"- **Long-term** (strategic improvements):\n{fmt(long_term)}\n"
    )


def generate_report(
    db_summary: dict,
    analysis: dict,
    personas_data: dict,
    output_path: str | None = None,
) -> str:
    meta = db_summary["meta"]
    persona_name = meta.get("persona", "Unknown")
    persona = find_persona(personas_data, persona_name)
    score_data = analysis["apple_ux_score"]
    anti_patterns = analysis.get("anti_patterns", [])
    scorecard = analysis.get("heuristic_scorecard", [])
    tickets = analysis.get("developer_tickets", [])
    doc_dep = analysis.get("doc_dependency", {})
    friction_hotspots = analysis.get("friction_hotspots", [])

    steps = db_summary["steps"]
    issues = db_summary["issues"]

    date = datetime.now().strftime("%Y-%m-%d")
    target = meta.get("target", "Unknown")
    app_type = meta.get("app_type", "?")

    report = f"""# 🧭 User Journey Review — {target}

**Persona**: {persona_name}  |  **App Type**: {app_type}  |  **Date**: {date}
**Apple UX Score**: {score_data['score']}/100 {score_data['emoji']} ({score_data['grade']})
**Steps**: {len(steps)}  |  **Issues**: {len(issues)} (Critical:{score_data['breakdown']['critical_issues']} High:{score_data['breakdown']['high_issues']} Med:{score_data['breakdown']['medium_issues']} Low:{score_data['breakdown']['low_issues']})
**Doc Dependency**: {doc_dep.get('verdict', '—')}

---

## Executive Summary

{build_executive_summary(score_data, anti_patterns, len(issues), len(steps))}

---

## 👤 Persona Embodied

{render_persona(persona)}

---

## 🗺️ Journey Map

{render_journey_map(steps)}

**Friction hotspots** (steps with highest friction):
"""
    for hs in friction_hotspots[:3]:
        report += f"- Step {hs['id']}: **{hs['action']}** — {FRICTION_EMOJI.get(min(hs['friction_score'], 3), '?')} friction={hs['friction_score']}  _{hs.get('notes', '')}_\n"

    report += f"""
---

## 🚨 UX Anti-Patterns

{render_anti_patterns(anti_patterns)}

---

## 📋 All Issues

{render_issues_table(issues)}

---

## 📊 Heuristic Scorecard (Nielsen's 10)

{render_heuristic_scorecard(scorecard)}

**Score composition**: base={score_data['base_heuristic']}/100  issue_penalty=-{score_data['issue_penalty']}  friction_penalty=-{score_data['friction_penalty']} → **{score_data['score']}/100**

---

## 🛠️ Developer Tickets

{render_developer_tickets(tickets)}

---

## 🎯 Recommendations Roadmap

{build_recommendations(anti_patterns, tickets)}

---

## 🍎 Apple UX Standard Checklist

| Check | Status |
|-------|--------|
| Zero-docs: user completes core task without reading docs | {doc_dep.get('verdict', '—')} |
| First impression: product purpose clear in < 3 seconds | {"✅" if score_data['score'] >= 70 else "❌ Needs work"} |
| Every action produces visible feedback | {"✅" if score_data['breakdown']['medium_issues'] == 0 else "⚠️ Issues found"} |
| User can always go back / undo | {"✅" if not any(i["issue_type"] == "no_undo" for i in issues) else "❌ Undo missing"} |
| No jargon without explanation | {"✅" if not any(i["issue_type"] == "jargon" for i in issues) else "❌ Jargon detected"} |
| Core task completable in ≤ 5 steps | {"✅" if len(steps) <= 5 else f"⚠️ {len(steps)} steps — consider reducing"} |

---

_Report generated by `general-user-journey-review` skill_
_Baseline: [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) ui-ux-tester + ux-researcher (18.5k ⭐)_
"""

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"[report_generator] Report written to {output_path}", file=sys.stderr)
    return report


def main():
    parser = argparse.ArgumentParser(description="Generate a UX review report from journey data.")
    parser.add_argument("--db", required=True, help="Path to journey SQLite DB")
    parser.add_argument("--analysis", required=True, help="Path to analysis JSON (from ux_analyzer.py)")
    parser.add_argument("--personas", required=True, help="Path to personas JSON (from persona_builder.py)")
    parser.add_argument("--output", default=None, help="Output Markdown path")
    args = parser.parse_args()

    for p in [args.db, args.analysis, args.personas]:
        if not Path(p).exists():
            print(f"[report_generator] ERROR: File not found: {p}", file=sys.stderr)
            sys.exit(1)

    db_summary = load_db_summary(args.db)
    analysis = load_json(args.analysis)
    personas_data = load_json(args.personas)

    report = generate_report(db_summary, analysis, personas_data, args.output)
    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
