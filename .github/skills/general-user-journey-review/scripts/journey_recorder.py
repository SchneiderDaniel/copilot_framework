#!/usr/bin/env python3
"""
journey_recorder.py — SQLite-backed user journey step and issue recorder.

CLI usage:
    python journey_recorder.py init    --db journey.db --persona "Alex" --target "onboarding"
    python journey_recorder.py step    --db journey.db --action "opened app" --tool playwright --url http://localhost --friction 0
    python journey_recorder.py issue   --db journey.db --step 1 --type unclear_label --severity 2 --desc "Button says 'Submit' but does nothing"
    python journey_recorder.py heuristic --db journey.db --name "H1: Visibility of system status" --score 6
    python journey_recorder.py finalize --db journey.db
    python journey_recorder.py summary  --db journey.db [--json]

Python API:
    from journey_recorder import JourneyDB
    db = JourneyDB(".ux-review/journey.db")
    db.init_journey(persona="Alex", target="onboarding flow")
    step_id = db.record_step(action="Opened homepage", tool_used="playwright", friction_score=0)
    db.record_issue(step_id=step_id, issue_type="unclear_label", severity=2, description="CTA is ambiguous")
    db.finalize()
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS journey_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    action           TEXT    NOT NULL,
    description      TEXT    DEFAULT '',
    tool_used        TEXT    DEFAULT '',
    url_or_command   TEXT    DEFAULT '',
    screenshot_path  TEXT    DEFAULT '',
    friction_score   INTEGER DEFAULT 0,
    time_seconds     REAL    DEFAULT 0,
    notes            TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS issues (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id             INTEGER REFERENCES steps(id),
    issue_type          TEXT    NOT NULL,
    severity            INTEGER NOT NULL,
    description         TEXT    NOT NULL,
    evidence            TEXT    DEFAULT '',
    heuristic_violated  TEXT    DEFAULT '',
    mitigation          TEXT    DEFAULT '',
    developer_ticket    TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS heuristic_scores (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    heuristic TEXT    NOT NULL,
    score     INTEGER NOT NULL,
    notes     TEXT    DEFAULT ''
);
"""

ISSUE_TYPES = [
    "cognitive_overload",      # Too much information at once
    "unclear_label",           # Button / label text is ambiguous
    "missing_feedback",        # No confirmation or progress after action
    "hidden_feature",          # Important feature is hard to discover
    "unnecessary_step",        # A step that adds no value and should be removed
    "error_without_guidance",  # Error with no recovery path
    "inconsistent_behavior",   # Same action behaves differently in different contexts
    "no_undo",                 # Destructive action with no undo option
    "jargon",                  # Technical term without explanation
    "slow_response",           # Delayed feedback without a progress indicator
    "layout_confusion",        # Visual layout makes it unclear what to do next
    "broken_flow",             # User cannot proceed; journey terminates unexpectedly
    "documentation_required",  # User must read docs to complete a basic action
    "accessibility_barrier",   # Difficulty for users with disabilities
    "other",
]

SEVERITY_LABELS = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
FRICTION_LABELS = {0: "🟢 smooth", 1: "🟡 minor", 2: "🟠 moderate", 3: "🔴 BLOCKER"}

NIELSEN_HEURISTICS = [
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


class JourneyDB:
    """Python API for recording user journey steps and UX issues into SQLite."""

    def __init__(self, db_path: str = "journey.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Journey lifecycle
    # ------------------------------------------------------------------
    def init_journey(
        self,
        persona: str,
        target: str,
        project_path: str = ".",
        app_type: str = "",
    ):
        meta = {
            "persona": persona,
            "target": target,
            "project_path": project_path,
            "app_type": app_type,
            "started_at": datetime.now().isoformat(),
            "status": "in_progress",
        }
        for k, v in meta.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO journey_meta (key, value) VALUES (?, ?)", (k, v)
            )
        self.conn.commit()
        print(f"[journey] Initialized  persona='{persona}'  target='{target}'")

    def finalize(self):
        self.conn.execute(
            "INSERT OR REPLACE INTO journey_meta (key, value) VALUES ('status', 'completed')"
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO journey_meta (key, value) VALUES ('completed_at', ?)",
            (datetime.now().isoformat(),),
        )
        self.conn.commit()
        s = self.summary()
        print(
            f"[journey] Finalized — steps:{s['step_count']}  issues:{s['issue_count']}"
            f"  friction:{s['total_friction']}  score:{s['apple_ux_score']}/100"
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record_step(
        self,
        action: str,
        description: str = "",
        tool_used: str = "",
        url_or_command: str = "",
        screenshot_path: str = "",
        friction_score: int = 0,
        time_seconds: float = 0.0,
        notes: str = "",
    ) -> int:
        cursor = self.conn.execute(
            """INSERT INTO steps
               (timestamp, action, description, tool_used, url_or_command,
                screenshot_path, friction_score, time_seconds, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(), action, description, tool_used,
                url_or_command, screenshot_path, friction_score, time_seconds, notes,
            ),
        )
        self.conn.commit()
        step_id = cursor.lastrowid
        label = FRICTION_LABELS.get(min(friction_score, 3), "")
        print(f"  [step {step_id:2d}] {label}  {action}")
        return step_id

    def record_issue(
        self,
        step_id: int,
        issue_type: str,
        severity: int,
        description: str,
        evidence: str = "",
        heuristic_violated: str = "",
        mitigation: str = "",
        developer_ticket: str = "",
    ) -> int:
        if issue_type not in ISSUE_TYPES:
            issue_type = "other"
        cursor = self.conn.execute(
            """INSERT INTO issues
               (step_id, issue_type, severity, description, evidence,
                heuristic_violated, mitigation, developer_ticket)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (step_id, issue_type, severity, description, evidence,
             heuristic_violated, mitigation, developer_ticket),
        )
        self.conn.commit()
        sev = SEVERITY_LABELS.get(min(severity, 4), "?")
        print(f"          ⚠ [{sev}] {issue_type}: {description[:70]}")
        return cursor.lastrowid

    def record_heuristic_score(self, heuristic: str, score: int, notes: str = ""):
        self.conn.execute(
            "INSERT INTO heuristic_scores (heuristic, score, notes) VALUES (?, ?, ?)",
            (heuristic, score, notes),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def summary(self) -> dict:
        meta = {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM journey_meta")}
        steps = self.conn.execute("SELECT * FROM steps ORDER BY id").fetchall()
        issues = self.conn.execute("SELECT * FROM issues ORDER BY severity DESC").fetchall()
        heuristics = self.conn.execute("SELECT * FROM heuristic_scores").fetchall()

        total_friction = sum(s["friction_score"] for s in steps)
        by_severity = {1: 0, 2: 0, 3: 0, 4: 0}
        for i in issues:
            by_severity[min(i["severity"], 4)] += 1

        # Compute Apple UX Score (0–100)
        h_scores = [h["score"] for h in heuristics]
        avg_heuristic = (sum(h_scores) / len(h_scores)) if h_scores else 5
        issue_penalty = by_severity[4] * 10 + by_severity[3] * 5 + by_severity[2] * 2 + by_severity[1]
        friction_penalty = total_friction * 3
        apple_ux_score = max(0, int(avg_heuristic * 10 - issue_penalty - friction_penalty))

        return {
            "meta": dict(meta),
            "step_count": len(steps),
            "total_friction": total_friction,
            "issue_count": len(issues),
            "critical": by_severity[4],
            "high": by_severity[3],
            "medium": by_severity[2],
            "low": by_severity[1],
            "apple_ux_score": apple_ux_score,
            "steps": [dict(s) for s in steps],
            "issues": [dict(i) for i in issues],
            "heuristic_scores": [dict(h) for h in heuristics],
        }

    def close(self):
        self.conn.close()


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Record user journey steps and UX issues.")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p = sub.add_parser("init", help="Start a new journey recording session")
    p.add_argument("--db", default="journey.db")
    p.add_argument("--persona", required=True)
    p.add_argument("--target", required=True, help="What journey/feature is being tested")
    p.add_argument("--project-path", default=".")
    p.add_argument("--app-type", default="")

    # step
    p = sub.add_parser("step", help="Record a journey step")
    p.add_argument("--db", default="journey.db")
    p.add_argument("--action", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tool", dest="tool_used", default="")
    p.add_argument("--url", dest="url_or_command", default="")
    p.add_argument("--screenshot", dest="screenshot_path", default="")
    p.add_argument("--friction", type=int, default=0, choices=[0, 1, 2, 3],
                   help="0=smooth 1=minor 2=moderate 3=blocker")
    p.add_argument("--time", dest="time_seconds", type=float, default=0.0)
    p.add_argument("--notes", default="")

    # issue
    p = sub.add_parser("issue", help="Record a UX issue observed during a step")
    p.add_argument("--db", default="journey.db")
    p.add_argument("--step", type=int, required=True, help="Step ID this issue belongs to")
    p.add_argument("--type", dest="issue_type", required=True, choices=ISSUE_TYPES)
    p.add_argument("--severity", type=int, required=True, choices=[1, 2, 3, 4],
                   help="1=low 2=medium 3=high 4=critical")
    p.add_argument("--desc", required=True, help="What the user experienced")
    p.add_argument("--evidence", default="", help="Screenshot path, URL, or quoted error text")
    p.add_argument("--heuristic", dest="heuristic_violated", default="")
    p.add_argument("--mitigation", default="", help="Concrete developer fix")
    p.add_argument("--ticket", dest="developer_ticket", default="")

    # heuristic
    p = sub.add_parser("heuristic", help="Record a Nielsen heuristic score (0–10)")
    p.add_argument("--db", default="journey.db")
    p.add_argument("--name", required=True, help="Heuristic name (e.g. 'H1: Visibility of system status')")
    p.add_argument("--score", type=int, required=True)
    p.add_argument("--notes", default="")

    # finalize
    p = sub.add_parser("finalize", help="Mark journey recording as complete")
    p.add_argument("--db", default="journey.db")

    # summary
    p = sub.add_parser("summary", help="Print a summary of the recorded journey")
    p.add_argument("--db", default="journey.db")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    db = JourneyDB(args.db)

    if args.command == "init":
        db.init_journey(args.persona, args.target, args.project_path, args.app_type)

    elif args.command == "step":
        db.record_step(
            args.action, args.description, args.tool_used, args.url_or_command,
            args.screenshot_path, args.friction, args.time_seconds, args.notes,
        )

    elif args.command == "issue":
        db.record_issue(
            args.step, args.issue_type, args.severity, args.desc,
            args.evidence, args.heuristic_violated, args.mitigation, args.developer_ticket,
        )

    elif args.command == "heuristic":
        db.record_heuristic_score(args.name, args.score, args.notes)

    elif args.command == "finalize":
        db.finalize()

    elif args.command == "summary":
        s = db.summary()
        if args.json:
            print(json.dumps(s, indent=2))
        else:
            print(f"\n{'='*50}")
            print(f"Journey Summary")
            print(f"{'='*50}")
            print(f"Persona : {s['meta'].get('persona', '?')}")
            print(f"Target  : {s['meta'].get('target', '?')}")
            print(f"Status  : {s['meta'].get('status', '?')}")
            print(f"Steps   : {s['step_count']}")
            print(f"Friction: {s['total_friction']}")
            print(f"Issues  : {s['issue_count']}  "
                  f"(Critical:{s['critical']} High:{s['high']} Med:{s['medium']} Low:{s['low']})")
            print(f"Apple UX Score: {s['apple_ux_score']}/100")

    db.close()


if __name__ == "__main__":
    main()
