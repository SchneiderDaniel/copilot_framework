from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from cosk.config import CoskConfig
from cosk.extraction.parser import extract_skeleton_nodes


def _write_python(path: Path, name: str) -> None:
    path.write_text(f"def {name}():\n    return 1\n", encoding="utf-8")


def _relative_files(root: Path, config: CoskConfig) -> set[str]:
    return {
        Path(node.file_path).resolve().relative_to(root.resolve()).as_posix()
        for node in extract_skeleton_nodes(root, config=config)
    }


def test_root_gitignore_excludes_matching_files(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / ".gitignore").write_text("*.generated.py\n", encoding="utf-8")
    _write_python(tmp_path / "keep.py", "keep")
    _write_python(tmp_path / "skip.generated.py", "skip")

    assert _relative_files(tmp_path, base_config) == {"keep.py"}


def test_root_gitignore_excludes_directory_and_prunes_descent(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    _write_python(tmp_path / "build" / "skip.py", "skip")
    _write_python(tmp_path / "keep.py", "keep")

    assert _relative_files(tmp_path, base_config) == {"keep.py"}


def test_nested_gitignore_applies_only_within_subtree(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "pkg" / ".gitignore").write_text("*.tmp.py\n", encoding="utf-8")
    _write_python(tmp_path / "pkg" / "skip.tmp.py", "skip")
    _write_python(tmp_path / "other" / "keep.tmp.py", "keep")

    assert _relative_files(tmp_path, base_config) == {"other/keep.tmp.py"}


def test_nested_gitignore_negation_reincludes_child_file(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / ".gitignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    _write_python(tmp_path / "pkg" / "keep.py", "keep")
    _write_python(tmp_path / "pkg" / "skip.py", "skip")

    assert _relative_files(tmp_path, base_config) == {"pkg/keep.py"}


def test_exclude_dirs_and_gitignore_filters_both_apply(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / ".gitignore").write_text("!__pycache__/keep.py\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    _write_python(tmp_path / "__pycache__" / "keep.py", "keep")
    _write_python(tmp_path / "ok.py", "ok")

    assert _relative_files(tmp_path, base_config) == {"ok.py"}


def test_respect_gitignore_false_disables_gitignore_filtering(tmp_path: Path, base_config: CoskConfig) -> None:
    (tmp_path / ".gitignore").write_text("*.generated.py\n", encoding="utf-8")
    _write_python(tmp_path / "skip.generated.py", "skip")
    without_gitignore = replace(
        base_config,
        extraction=replace(base_config.extraction, respect_gitignore=False),
    )

    assert _relative_files(tmp_path, without_gitignore) == {"skip.generated.py"}


def test_no_gitignore_produces_same_result_when_toggle_changes(tmp_path: Path, base_config: CoskConfig) -> None:
    _write_python(tmp_path / "a.py", "a")
    _write_python(tmp_path / "b.py", "b")
    without_gitignore = replace(
        base_config,
        extraction=replace(base_config.extraction, respect_gitignore=False),
    )

    assert _relative_files(tmp_path, base_config) == _relative_files(tmp_path, without_gitignore)
