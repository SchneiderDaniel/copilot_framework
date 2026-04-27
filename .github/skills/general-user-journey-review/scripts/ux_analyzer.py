#!/usr/bin/env python3
"""
ux_analyzer.py — Analyzes a recorded journey DB and computes UX health scores.

Usage:
    python ux_analyzer.py --db .ux-review/journey.db [--output .ux-review/analysis.json]
"""
import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path


# Apple HIG-derived anti-pattern rules mapped to issue types
ANTI_PATTERN_RULES = {
    "Zero-docs Standard Violated": {
        "issue_types": ["documentation_required", "jargon"],
        "description": "User needed to consult documentation or encountered unexplained jargon",
        "apple_principle": "Self-evident UI — tooltips and docs are a last resort",
        "severity_weight": 2.0,
    },
    "Missing Feedback Loops": {
        "issue_types": ["missing_feedback", "slow_response"],
        "description": "Actions did not produce visible, timely feedback",
        "apple_principle": "Every action has a response within 100ms or a progress indicator",
        "severity_weight": 1.5,
    },
    "Flow Breakage": {
        "issue_types": ["broken_flow", "error_without_guidance"],
        "description": "User encountered dead ends or errors with no recovery path",
        "apple_principle": "Forgiveness — users can always go back or get unstuck",
        "severity_weight": 3.0,
    },
    "Unnecessary Complexity": {
        "issue_types": ["unnecessary_step", "cognitive_overload"],
        "description": "Journey had steps or information that added friction without value",
        "apple_principle": "Minimal steps — if 5 steps, ask if it can be done in 2",
        "severity_weight": 1.5,
    },
    "Ambiguous Interface": {
        "issue_types": ["unclear_label", "layout_confusion", "inconsistent_behavior"],
        "description": "Labels, layout, or behavior created uncertainty about what to do next",
        "apple_principle": "One obvious path — never make the user choose between unclear options",
        "severity_weight": 2.0,
    },
    "Power User Lock-out": {
        "issue_types": ["no_undo", "hidden_feature"],
        "description": "Advanced usage is blocked or features are hard to discover",
        "apple_principle": "Flexibility and efficiency — support both novice and expert paths",
        "severity_weight": 1.0,
    },
    "Accessibility Gaps": {
        "issue_types": ["accessibility_barrier"],
        "description": "Barriers for users with different abilities or contexts",
        "apple_principle": "Inclusive design — works for everyone by default",
        "severity_weight": 1.5,
    },
}

FRICTION_SCORE_LABELS = {
    0: "🟢 Smooth (Apple-level)",
    1: "🟡 Some friction (good)",
    2: "🟠 Noticeable friction (needs work)",
    3: "🔴 High friction (users will abandon)",
    4: "💀 Critical friction (product fails)",
}


def load_journey(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM journey_meta")}
    steps = [dict(r) for r in conn.execute("SELECT * FROM steps ORDER BY id")]
    issues = [dict(r) for r in conn.execute("SELECT * FROM issues ORDER BY severity DESC")]
    heuristics = [dict(r) for r in conn.execute("SELECT * FROM heuristic_scores")]
    conn.close()
    return {"meta": meta, "steps": steps, "issues": issues, "heuristics": heuristics}


def compute_apple_ux_score(issues: list, heuristics: list, steps: list) -> dict:
    """
    Apple UX Score (0–100):
      - Base: average heuristic score * 10 (0–100)
      - Penalties:
          critical issue: -10 pts each
          high issue: -5 pts each
          medium issue: -2 pts each
          low issue: -1 pt each
          per-step friction: -2 pts per unit of friction
    """
    sev_count = Counter(i["severity"] for i in issues)
    total_friction = sum(s["friction_score"] for s in steps)
    h_scores = [h["score"] for h in heuristics] if heuristics else [5]
    avg_heuristic = sum(h_scores) / len(h_scores)

    base = avg_heuristic * 10
    issue_penalty = (
        sev_count.get(4, 0) * 10
        + sev_count.get(3, 0) * 5
        + sev_count.get(2, 0) * 2
        + sev_count.get(1, 0) * 1
    )
    friction_penalty = total_friction * 2
    score = max(0, min(100, int(base - issue_penalty - friction_penalty)))

    if score >= 85:
        grade, emoji = "A — Apple-level", "🍎"
    elif score >= 70:
        grade, emoji = "B — Good", "🟢"
    elif score >= 55:
        grade, emoji = "C — Needs Work", "🟡"
    elif score >= 35:
        grade, emoji = "D — Poor", "🟠"
    else:
        grade, emoji = "F — Critical", "🔴"

    return {
        "score": score,
        "grade": grade,
        "emoji": emoji,
        "base_heuristic": round(avg_heuristic * 10, 1),
        "issue_penalty": issue_penalty,
        "friction_penalty": friction_penalty,
        "breakdown": {
            "critical_issues": sev_count.get(4, 0),
            "high_issues": sev_count.get(3, 0),
            "medium_issues": sev_count.get(2, 0),
            "low_issues": sev_count.get(1, 0),
            "total_friction": total_friction,
        },
    }


def detect_anti_patterns(issues: list) -> list[dict]:
    """Map issues to Apple/Nielsen anti-patterns."""
    issue_type_count = Counter(i["issue_type"] for i in issues)
    issue_type_max_sev = defaultdict(int)
    for i in issues:
        issue_type_max_sev[i["issue_type"]] = max(issue_type_max_sev[i["issue_type"]], i["severity"])

    detected = []
    for pattern_name, rule in ANTI_PATTERN_RULES.items():
        matched_types = [t for t in rule["issue_types"] if issue_type_count.get(t, 0) > 0]
        if not matched_types:
            continue
        count = sum(issue_type_count[t] for t in matched_types)
        max_sev = max(issue_type_max_sev[t] for t in matched_types)
        detected.append({
            "pattern": pattern_name,
            "description": rule["description"],
            "apple_principle": rule["apple_principle"],
            "matched_issue_types": matched_types,
            "occurrence_count": count,
            "max_severity": max_sev,
            "weighted_score": round(count * rule["severity_weight"] * max_sev, 1),
        })

    detected.sort(key=lambda x: x["weighted_score"], reverse=True)
    return detected


def analyze_friction_hotspots(steps: list) -> list[dict]:
    """Identify the steps with the most friction."""
    return sorted(
        [s for s in steps if s["friction_score"] > 0],
        key=lambda s: s["friction_score"],
        reverse=True,
    )[:5]


def compute_documentation_dependency(steps: list, issues: list) -> dict:
    """How often did the user need to consult docs?"""
    doc_issues = [i for i in issues if i["issue_type"] == "documentation_required"]
    doc_steps = set(i["step_id"] for i in doc_issues)
    total_steps = len(steps) or 1
    rate = round(len(doc_steps) / total_steps * 100, 1)
    return {
        "steps_requiring_docs": len(doc_steps),
        "total_steps": total_steps,
        "rate_percent": rate,
        "verdict": (
            "✅ Zero-docs" if rate == 0
            else "🟡 Minimal docs needed" if rate <= 15
            else "🟠 Docs required for key steps" if rate <= 35
            else "🔴 Heavily doc-dependent"
        ),
    }


def build_heuristic_scorecard(heuristics: list) -> list[dict]:
    scored = []
    for h in heuristics:
        s = h["score"]
        scored.append({
            "heuristic": h["heuristic"],
            "score": s,
            "max": 10,
            "bar": "█" * s + "░" * (10 - s),
            "status": "🟢" if s >= 7 else "🟡" if s >= 5 else "🔴",
            "notes": h.get("notes", ""),
        })
    # Fill in unscored heuristics
    scored_names = {h["heuristic"] for h in heuristics}
    all_heuristics = [
        "H1: Visibility of system status",
        "H2: Match between system and real world",
        "H3: User control and freedom",
        "H4: Consistency and standards",
        "H5: Error prevention",
        "H6: Recognition rather than recall",
        "H7: Flexibility and efficiency of use",
        "H8: Aesthetic and minimalist design",
        "H9: Help users recognize, diagnose, and recover from errors",
        "H10: Help and documentation",
    ]
    for h in all_heuristics:
        if h not in scored_names:
            scored.append({
                "heuristic": h, "score": None, "max": 10,
                "bar": "─" * 10, "status": "⚪ Not scored", "notes": "",
            })
    return scored


def generate_developer_tickets(issues: list) -> list[dict]:
    """Create developer-ready tickets from high/critical issues."""
    tickets = []
    ticket_num = 1
    for issue in sorted(issues, key=lambda i: -i["severity"]):
        if issue["severity"] < 2:
            continue
        tickets.append({
            "id": f"UX-{ticket_num:02d}",
            "title": f"Fix: {issue['issue_type'].replace('_', ' ').title()} in step {issue['step_id']}",
            "severity": issue["severity"],
            "severity_label": {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}.get(issue["severity"], "?"),
            "issue_type": issue["issue_type"],
            "step_id": issue["step_id"],
            "problem": issue["description"],
            "evidence": issue.get("evidence", ""),
            "heuristic": issue.get("heuristic_violated", ""),
            "mitigation": issue.get("mitigation", "No mitigation specified — agent should fill this in"),
            "effort": _estimate_effort(issue["issue_type"], issue["severity"]),
        })
        ticket_num += 1
    return tickets


def _estimate_effort(issue_type: str, severity: int) -> str:
    small_types = {"unclear_label", "jargon", "missing_feedback"}
    large_types = {"broken_flow", "inconsistent_behavior", "accessibility_barrier"}
    if issue_type in small_types:
        return "Small (< 1 day)"
    if issue_type in large_types:
        return "Large (> 3 days)"
    return "Medium (1–3 days)"


def main():
    parser = argparse.ArgumentParser(description="Analyze a journey DB for UX health.")
    parser.add_argument("--db", required=True, help="Path to the journey SQLite database")
    parser.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"[ux_analyzer] ERROR: DB not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    print(f"[ux_analyzer] Analyzing: {args.db}", file=sys.stderr)
    data = load_journey(args.db)

    apple_score = compute_apple_ux_score(data["issues"], data["heuristics"], data["steps"])
    anti_patterns = detect_anti_patterns(data["issues"])
    friction_hotspots = analyze_friction_hotspots(data["steps"])
    doc_dependency = compute_documentation_dependency(data["steps"], data["issues"])
    heuristic_scorecard = build_heuristic_scorecard(data["heuristics"])
    developer_tickets = generate_developer_tickets(data["issues"])

    result = {
        "meta": data["meta"],
        "apple_ux_score": apple_score,
        "doc_dependency": doc_dependency,
        "anti_patterns": anti_patterns,
        "friction_hotspots": friction_hotspots,
        "heuristic_scorecard": heuristic_scorecard,
        "developer_tickets": developer_tickets,
        "raw_step_count": len(data["steps"]),
        "raw_issue_count": len(data["issues"]),
    }

    output = json.dumps(result, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        print(
            f"[ux_analyzer] Score: {apple_score['score']}/100 ({apple_score['grade']})  "
            f"Anti-patterns: {len(anti_patterns)}  Tickets: {len(developer_tickets)}",
            file=sys.stderr,
        )
        print(f"[ux_analyzer] Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
