from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

COSK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COSK_DIR.parent
FAKE_PROVIDER_FACTORY = "cosk.tests.test_index_service_integration:make_fake_provider"


class DeterministicFakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(8)]


def make_fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider()


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COSK_EMBEDDING_PROVIDER_FACTORY"] = FAKE_PROVIDER_FACTORY
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cosk.cli.main", *args],
        cwd=cwd,
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.integration
def test_cli_incremental_index_outputs_summary_json(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    db_dir = tmp_path / ".lancedb"
    target.mkdir()
    (target / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    full = _run_cli(["index", "--target-dir", str(target), "--db-dir", str(db_dir), "--name", "default"], cwd=tmp_path)
    assert full.returncode == 0, full.stderr

    (target / "a.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    incremental = _run_cli(
        ["index", "--target-dir", str(target), "--db-dir", str(db_dir), "--name", "default", "--incremental"],
        cwd=tmp_path,
    )
    assert incremental.returncode == 0, incremental.stderr
    payload = json.loads(incremental.stdout)
    assert payload["mode"] in {"incremental", "incremental_fallback_full"}
    assert {"added_files", "updated_files", "deleted_files", "indexed_nodes"} <= set(payload)


@pytest.mark.integration
def test_incremental_counts_reflect_add_update_delete(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    db_dir = tmp_path / ".lancedb"
    target.mkdir()
    (target / "keep.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    (target / "gone.py").write_text("def gone():\n    return 1\n", encoding="utf-8")
    _run_cli(["index", "--target-dir", str(target), "--db-dir", str(db_dir), "--name", "default"], cwd=tmp_path)

    (target / "keep.py").write_text("def keep():\n    return 2\n", encoding="utf-8")
    (target / "new.py").write_text("def new():\n    return 3\n", encoding="utf-8")
    (target / "gone.py").unlink()
    incremental = _run_cli(
        ["index", "--target-dir", str(target), "--db-dir", str(db_dir), "--name", "default", "--incremental"],
        cwd=tmp_path,
    )
    assert incremental.returncode == 0, incremental.stderr
    payload = json.loads(incremental.stdout)
    assert payload["added_files"] >= 1
    assert payload["updated_files"] >= 1
    assert payload["deleted_files"] >= 1
