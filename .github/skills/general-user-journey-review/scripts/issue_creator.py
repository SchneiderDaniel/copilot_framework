#!/usr/bin/env python3
"""
issue_creator.py — Creates a GitHub issue from a UX review report.

Usage:
    python issue_creator.py \
        --report .ux-review/ux-review-report.md \
        --title "UX Review: Onboarding — 5 issues (Score: 62/100)" \
        --repo SchneiderDaniel/agentradio \
        --labels "ux,needs-review"
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_LABELS = "ux,needs-review"


def check_gh_available() -> bool:
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def get_current_repo() -> str | None:
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def create_issue(report_path: str, title: str, repo: str | None, labels: str) -> bool:
    if not check_gh_available():
        print("[issue_creator] ERROR: `gh` CLI not found. Install it from https://cli.github.com/", file=sys.stderr)
        return False

    report_text = Path(report_path).read_text(encoding="utf-8")

    # Write to a temp file to avoid shell escaping issues with large bodies
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tf:
        tf.write(report_text)
        tmp_path = tf.name

    cmd = ["gh", "issue", "create", "--title", title, "--body-file", tmp_path]

    if repo:
        cmd += ["--repo", repo]

    if labels:
        for label in labels.split(","):
            cmd += ["--label", label.strip()]

    print(f"[issue_creator] Creating issue: {title}", file=sys.stderr)
    print(f"[issue_creator] Command: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"[issue_creator] ✅ Issue created: {issue_url}")
            return True
        else:
            print(f"[issue_creator] ERROR creating issue:\n{result.stderr}", file=sys.stderr)
            # Labels might not exist — try without labels
            if "label" in result.stderr.lower() or "not found" in result.stderr.lower():
                print("[issue_creator] Retrying without labels...", file=sys.stderr)
                cmd_no_labels = ["gh", "issue", "create", "--title", title, "--body-file", tmp_path]
                if repo:
                    cmd_no_labels += ["--repo", repo]
                result2 = subprocess.run(cmd_no_labels, capture_output=True, text=True, timeout=30)
                if result2.returncode == 0:
                    print(f"[issue_creator] ✅ Issue created (no labels): {result2.stdout.strip()}")
                    return True
                print(f"[issue_creator] ERROR: {result2.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        print(f"[issue_creator] Exception: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Create a GitHub issue from a UX review report.")
    parser.add_argument("--report", required=True, help="Path to the Markdown report file")
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--repo", default=None, help="GitHub repo (owner/name). Defaults to current repo.")
    parser.add_argument("--labels", default=DEFAULT_LABELS, help="Comma-separated labels (default: ux,needs-review)")
    args = parser.parse_args()

    if not Path(args.report).exists():
        print(f"[issue_creator] ERROR: Report not found: {args.report}", file=sys.stderr)
        sys.exit(1)

    repo = args.repo or get_current_repo()
    if not repo:
        print("[issue_creator] WARNING: Could not detect repo. Issue will be created in current repo context.", file=sys.stderr)

    success = create_issue(args.report, args.title, repo, args.labels)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
