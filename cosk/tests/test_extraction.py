from __future__ import annotations

import ast
from pathlib import Path

from cosk.config import CoskConfig
from cosk.extraction.parser import extract_skeleton_nodes


def _function_bearing_files(fixture_dir: Path) -> set[str]:
    files: set[str] = set()
    for file_path in fixture_dir.glob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)):
            files.add(file_path.resolve().as_posix())
    return files


def test_fixture_directory_contains_at_least_two_function_bearing_python_files(fixture_dir: Path) -> None:
    assert len(_function_bearing_files(fixture_dir)) >= 2


def test_extract_skeleton_nodes_returns_nodes_for_each_function_bearing_fixture_file(
    fixture_dir: Path, base_config: CoskConfig
) -> None:
    nodes = extract_skeleton_nodes(fixture_dir, config=base_config)
    assert nodes
    assert all(Path(node.file_path).is_absolute() for node in nodes)

    expected_files = _function_bearing_files(fixture_dir)
    extracted_files = {Path(node.file_path).resolve().as_posix() for node in nodes}
    assert expected_files <= extracted_files
