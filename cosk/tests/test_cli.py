from __future__ import annotations

from pathlib import Path

import pytest

from cosk.config import CoskConfig


def test_cosk_help_lists_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from cosk import cli

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "index" in output
    assert "serve" in output
    assert "inspect" in output


@pytest.mark.parametrize("subcommand", ["index", "serve", "inspect"])
def test_subcommand_help_outputs_useful_text(
    subcommand: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from cosk import cli

    with pytest.raises(SystemExit) as exc_info:
        cli.main([subcommand, "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    if subcommand == "index":
        assert "--target-dir" in output
        assert "--db-dir" in output
        assert "--no-gitignore" in output
    else:
        assert "--db-dir" in output


def test_index_dispatch_calls_build_index_from_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base_config: CoskConfig
) -> None:
    from cosk import cli

    calls: dict[str, object] = {}

    monkeypatch.setattr(cli, "get_cosk_config", lambda: base_config)
    monkeypatch.setattr(cli.server, "load_embedding_provider", lambda: "provider")

    def _build(target_dir: Path, db_dir: Path, embedding_provider: object, *, config: CoskConfig | None = None) -> object:
        calls["target_dir"] = target_dir
        calls["db_dir"] = db_dir
        calls["embedding_provider"] = embedding_provider
        calls["config"] = config
        return object()

    monkeypatch.setattr(cli.server, "build_index_from_target", _build)
    cli.main(["index", "--target-dir", str(tmp_path), "--db-dir", str(tmp_path / "custom.lancedb")])

    assert calls["target_dir"] == tmp_path
    assert calls["db_dir"] == tmp_path / "custom.lancedb"
    assert calls["embedding_provider"] == "provider"
    assert calls["config"] is base_config


def test_index_no_gitignore_passes_config_override_without_mutating_cached_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base_config: CoskConfig
) -> None:
    from cosk import cli

    passed_config: dict[str, CoskConfig] = {}
    monkeypatch.setattr(cli, "get_cosk_config", lambda: base_config)
    monkeypatch.setattr(cli.server, "load_embedding_provider", lambda: "provider")

    def _build(
        target_dir: Path, db_dir: Path, embedding_provider: object, *, config: CoskConfig | None = None
    ) -> object:
        assert target_dir == tmp_path
        assert embedding_provider == "provider"
        assert isinstance(config, CoskConfig)
        passed_config["value"] = config
        return object()

    monkeypatch.setattr(cli.server, "build_index_from_target", _build)
    cli.main(["index", "--target-dir", str(tmp_path), "--no-gitignore"])

    override = passed_config["value"]
    assert override is not base_config
    assert base_config.extraction.respect_gitignore is True
    assert override.extraction.respect_gitignore is False


def test_serve_dispatch_delegates_to_server_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from cosk import cli

    forwarded: dict[str, list[str] | None] = {}

    def _server_main(argv: list[str] | None = None) -> None:
        forwarded["argv"] = argv

    monkeypatch.setattr(cli.server, "main", _server_main)
    cli.main(["serve", "--db-dir", str(tmp_path / "index.lancedb")])

    assert forwarded["argv"] == ["--db-dir", str(tmp_path / "index.lancedb")]


def test_inspect_dispatch_delegates_to_inspect_run_and_forwards_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cosk import cli

    forwarded: dict[str, list[str] | None] = {}

    def _inspect_run(argv: list[str] | None = None) -> int:
        forwarded["argv"] = argv
        return 3

    monkeypatch.setattr(cli.inspect, "run", _inspect_run)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["inspect", "--db-dir", str(tmp_path / "index.lancedb")])
    assert exc_info.value.code == 3
    assert forwarded["argv"] == ["--db-dir", str(tmp_path / "index.lancedb")]


def test_main_without_subcommand_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    from cosk import cli

    with pytest.raises(SystemExit) as exc_info:
        cli.main([])
    assert exc_info.value.code == 2
    assert "usage:" in capsys.readouterr().err.lower()
