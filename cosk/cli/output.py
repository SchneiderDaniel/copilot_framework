from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from cosk.index_service import IndexIssue, IndexProgressObserver, IndexSyncResult


def write_json(payload: object) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def write_error(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.write("\n")


def write_info(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.write("\n")


def format_issue_summary(issue_counts: dict[str, int]) -> str:
    if not issue_counts:
        return ""
    labels = {
        "parse_failure": "parse failures",
        "missing_grammar": "missing grammar packages",
        "missing_query_file": "missing query files",
    }
    parts = [f"{count} {labels.get(kind, kind.replace('_', ' '))}" for kind, count in sorted(issue_counts.items())]
    return ", ".join(parts)


class RichIndexProgressObserver(IndexProgressObserver):
    def __init__(self) -> None:
        self._console = Console(stderr=True)
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self._console,
            transient=True,
        )
        self._task_id: int | None = None

    def start(self, mode: str, total_files: int, deleted_files: int = 0) -> None:
        suffix = f", {deleted_files} files scheduled for deletion" if deleted_files else ""
        label = f"Step 1/3  Scanning ({mode}){suffix}"
        self._progress.start()
        self._task_id = self._progress.add_task(label, total=max(total_files, 1))

    def advance(self, file_path: Path, extracted_nodes: int, skipped: bool = False) -> None:  # noqa: ARG002
        if self._task_id is None:
            return
        description = f"Step 1/3  {'Skipping' if skipped else 'Scanning'}  {file_path.name}"
        self._progress.update(self._task_id, advance=1, description=description)

    def embed_start(self, total_nodes: int) -> None:
        if self._task_id is None:
            return
        self._progress.reset(self._task_id, total=total_nodes, description="Step 2/3  Embedding nodes…")

    def embed_advance(self, current: int, total: int) -> None:  # noqa: ARG002
        if self._task_id is None:
            return
        self._progress.update(self._task_id, completed=current)

    def record_issue(self, issue: IndexIssue) -> None:  # noqa: ARG002
        return

    def finish(self, result: IndexSyncResult, elapsed_seconds: float, issue_summary: dict[str, int]) -> None:
        if self._task_id is not None:
            self._progress.stop()
        write_info(
            f"  Step 3/3  Done — {result.processed_files} files, {result.indexed_nodes} nodes in {elapsed_seconds:.1f}s."
        )
        if result.skipped_files:
            summary = format_issue_summary(issue_summary)
            if summary:
                write_info(f"{result.skipped_files} files skipped ({summary}).")
            else:
                write_info(f"{result.skipped_files} files skipped.")

