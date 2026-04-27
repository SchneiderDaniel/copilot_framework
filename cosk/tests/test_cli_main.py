from __future__ import annotations

import json
from pathlib import Path

import pytest

from cosk.cli import main as cli_main


def test_help_lists_new_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    for command in ("index", "search", "neighbors", "expand", "find-usage", "watch", "serve", "registry"):
        assert command in out


def test_missing_required_args_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["index"])
    assert exc_info.value.code != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_search_invalid_top_k_prints_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from importlib import import_module

    cli_module = import_module("cosk.cli.main")

    class _Context:
        class _Store:
            def search(self, query: str, top_k: int):  # noqa: ARG002
                return []

        vector_store = _Store()
        graph = None

    class _Manager:
        config = cli_module.get_cosk_config()

        def get_context(self, **kwargs):  # noqa: ANN003
            return _Context()

    monkeypatch.setattr(cli_module.server, "load_embedding_provider", lambda: object())
    monkeypatch.setattr(cli_module, "IndexManager", lambda **kwargs: _Manager())  # noqa: ARG005

    with pytest.raises(SystemExit) as exc:
        cli_main(["search", "hello", "--top-k", "0", "--db-dir", str(tmp_path / ".lancedb")])
    assert exc.value.code == 1
    assert "top_k" in capsys.readouterr().err


def test_registry_list_outputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    cli_main(["registry", "list"])
    payload = json.loads(capsys.readouterr().out)
    assert "indexes" in payload

