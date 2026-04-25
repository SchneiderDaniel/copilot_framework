from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cosk.config import CoskConfig, ExtractionSettings, SummarizerSettings
from cosk.extraction.parser import extract_skeleton_nodes


def test_extract_skeleton_nodes_directory_returns_nodes_per_file(
    tmp_path: Path, base_config: CoskConfig
) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("def a():\n    pass\n", encoding="utf-8")
    second.write_text("def b():\n    pass\n", encoding="utf-8")

    nodes = extract_skeleton_nodes(tmp_path, config=base_config)
    paths = {Path(node.file_path).name for node in nodes}
    assert {"a.py", "b.py"} <= paths


def test_extract_skeleton_nodes_skips_excluded_dirs(
    tmp_path: Path, base_config: CoskConfig
) -> None:
    excluded = tmp_path / "__pycache__"
    excluded.mkdir()
    (excluded / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    pass\n", encoding="utf-8")

    nodes = extract_skeleton_nodes(tmp_path, config=base_config)
    paths = {Path(node.file_path).name for node in nodes}
    assert "a.py" not in paths
    assert "b.py" in paths


def test_extract_skeleton_nodes_summarize_flag_calls_summarizer(
    tmp_path: Path, base_config: CoskConfig
) -> None:
    target = tmp_path / "a.py"
    target.write_text("def a():\n    pass\n", encoding="utf-8")
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=base_config.extraction.supported_languages,
            summarizer=SummarizerSettings(callable_path="cosk.tests.test_parser_dir:summarizer_stub"),
        )
    )
    nodes = extract_skeleton_nodes(tmp_path, summarize=True, config=config)
    assert nodes[0].docstring == "summary"


@pytest.mark.integration
def test_extract_skeleton_nodes_forestrag_backend_integration(base_config: CoskConfig) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "forestrag" / "backend"
    if not backend_dir.exists():
        pytest.skip("forestrag/backend not present")

    nodes = extract_skeleton_nodes(backend_dir, config=base_config)
    by_file: dict[str, int] = {}
    for node in nodes:
        by_file[node.file_path] = by_file.get(node.file_path, 0) + 1

    python_files_with_function = []
    for file_path in backend_dir.rglob("*.py"):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)):
            python_files_with_function.append(file_path.resolve().as_posix())

    assert python_files_with_function
    assert all(path in by_file for path in python_files_with_function)


def summarizer_stub(_: str, *, file_path: str, language: str, **__: object) -> str:
    return "summary"
