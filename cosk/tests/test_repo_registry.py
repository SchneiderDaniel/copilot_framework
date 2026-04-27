from __future__ import annotations

import pytest

from cosk.repo_registry import RegistryError, load_registry, resolve_index, set_default_index, upsert_index


def test_registry_save_and_resolve(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    upsert_index("default", tmp_path, tmp_path / ".lancedb")
    name, entry = resolve_index()
    assert name == "default"
    assert entry.db_dir.endswith(".lancedb")


def test_registry_set_default_unknown_raises(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RegistryError):
        set_default_index("missing")


def test_registry_corrupt_fails_closed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    reg = tmp_path / ".cosk" / "registry.yaml"
    reg.parent.mkdir()
    reg.write_text(": bad", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry()

