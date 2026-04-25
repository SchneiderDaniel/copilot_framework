from __future__ import annotations

from pathlib import Path
import tomllib


def test_pyproject_toml_declares_all_grammar_packages() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    dependency_names = {item.split(";", maxsplit=1)[0].split(">=", maxsplit=1)[0].strip() for item in dependencies}

    expected = {
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "tree-sitter-java",
        "tree-sitter-go",
        "tree-sitter-rust",
        "tree-sitter-c",
        "tree-sitter-cpp",
        "tree-sitter-ruby",
        "tree-sitter-bash",
        "tree-sitter-json",
        "tree-sitter-yaml",
        "tree-sitter-toml",
        "tree-sitter-css",
        "tree-sitter-html",
        "tree-sitter-kotlin",
        "tree-sitter-lua",
        "tree-sitter-markdown",
        "tree-sitter-php",
        "tree-sitter-scala",
        "tree-sitter-sql",
        "tree-sitter-swift",
        "tree-sitter-c-sharp",
    }
    assert expected.issubset(dependency_names)
