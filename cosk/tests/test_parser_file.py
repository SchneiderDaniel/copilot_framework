from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cosk.config import CoskConfig, ExtractionSettings, SummarizerSettings
from cosk.extraction.parser import extract_file_skeleton_nodes


def test_extract_file_skeleton_nodes_python_function_signature_and_docstring(
    python_file: Path, base_config: CoskConfig
) -> None:
    nodes = extract_file_skeleton_nodes(python_file, config=base_config)
    assert nodes
    assert nodes[0].raw_signature.startswith("def hello(")
    assert nodes[0].docstring == '"""Say hello."""'


def test_extract_file_skeleton_nodes_prunes_function_body_and_locals(
    python_file: Path, base_config: CoskConfig
) -> None:
    nodes = extract_file_skeleton_nodes(python_file, config=base_config)
    signature = nodes[0].raw_signature
    assert "for _ in range" not in signature
    assert "value =" not in signature


def test_extract_file_skeleton_nodes_returns_empty_for_unsupported_extension(
    tmp_path: Path, base_config: CoskConfig
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("def hello():\n    pass\n", encoding="utf-8")
    assert extract_file_skeleton_nodes(target, config=base_config) == []


def test_extract_file_skeleton_nodes_strict_raises_on_parse_failure(
    tmp_path: Path, base_config: CoskConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "broken.py"
    target.write_text("def x(:\n", encoding="utf-8")

    strict_config = replace(
        base_config,
        extraction=replace(base_config.extraction, strict=True),
    )

    def _raise(*_: object, **__: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("cosk.extraction.parser._build_parser", lambda *_: object())
    monkeypatch.setattr("cosk.extraction.parser._parse_tree", _raise)
    with pytest.raises(RuntimeError):
        extract_file_skeleton_nodes(target, config=strict_config)
