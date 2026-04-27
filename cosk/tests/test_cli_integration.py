from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig

import pytest

from cosk.config import get_cosk_config

COSK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COSK_DIR.parent
FAKE_PROVIDER_FACTORY = "cosk.tests.test_cli_integration:make_fake_provider"


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


def _run_module_cli(args: list[str], *, cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cosk.cli.main", *args],
        cwd=cwd,
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_python_module_entrypoint_commands_show_help() -> None:
    for subcommand in ("index", "search", "neighbors", "expand", "find-usage", "watch", "serve", "registry"):
        result = _run_module_cli([subcommand, "--help"], cwd=COSK_DIR)
        assert result.returncode == 0, result.stderr


def test_installed_console_script_registry_list_outputs_json() -> None:
    scripts_dir = Path(sysconfig.get_path("scripts"))
    candidates = [scripts_dir / "cosk", scripts_dir / "cosk.exe", scripts_dir / "cosk-script.py"]
    executable = next((candidate for candidate in candidates if candidate.exists()), None)
    if executable is None:
        pytest.skip("cosk console script is not installed in this environment")
    command = [str(executable), "registry", "list"] if executable.suffix.lower() != ".py" else [sys.executable, str(executable), "registry", "list"]
    result = subprocess.run(command, cwd=COSK_DIR, env=_cli_env(), capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "indexes" in payload


def test_cli_json_outputs_and_top_k_fields(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    db_dir = tmp_path / ".lancedb"
    target.mkdir()
    source_file = target / "app.py"
    source_file.write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")
    assert _run_module_cli(["index", "--target-dir", str(target), "--db-dir", str(db_dir), "--name", "default"], cwd=tmp_path).returncode == 0

    search = _run_module_cli(
        ["search", "--query", "alpha", "--db-dir", str(db_dir), "--top-k", "999"],
        cwd=tmp_path,
    )
    assert search.returncode == 0, search.stderr
    search_payload = json.loads(search.stdout)
    assert "top_k_requested" in search_payload
    assert "top_k_applied" in search_payload
    assert search_payload["top_k_requested"] == 999
    assert search_payload["top_k_applied"] == get_cosk_config().retrieval.max_top_k

    first_result = search_payload["results"][0]
    node_id = first_result["graph_node_id"]
    neighbors = _run_module_cli(["neighbors", "--node-id", node_id, "--db-dir", str(db_dir)], cwd=tmp_path)
    assert neighbors.returncode == 0, neighbors.stderr
    assert {"inbound", "outbound"} <= set(json.loads(neighbors.stdout))

    expanded = _run_module_cli(
        ["expand", "--file-path", str(source_file), "--start-line", "1", "--end-line", "1", "--db-dir", str(db_dir)],
        cwd=tmp_path,
    )
    assert expanded.returncode == 0, expanded.stderr
    assert "content" in json.loads(expanded.stdout)

    usage = _run_module_cli(["find-usage", "--entity-name", "alpha", "--db-dir", str(db_dir)], cwd=tmp_path)
    assert usage.returncode == 0, usage.stderr
    assert isinstance(json.loads(usage.stdout), list)


def test_cli_invalid_subcommand_and_invalid_top_k_return_nonzero(tmp_path: Path) -> None:
    invalid_subcommand = _run_module_cli(["does-not-exist"], cwd=tmp_path)
    assert invalid_subcommand.returncode != 0
    assert invalid_subcommand.stderr.strip()

    invalid_top_k = _run_module_cli(["search", "--query", "alpha", "--top-k", "0"], cwd=tmp_path)
    assert invalid_top_k.returncode != 0
    assert "top_k" in invalid_top_k.stderr
