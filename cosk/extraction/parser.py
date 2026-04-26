from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import ast
from dataclasses import asdict, dataclass
from importlib import import_module
import os
from pathlib import Path
import warnings

import pathspec
from tree_sitter import Language, Parser

from cosk.config import CoskConfig, LanguageSettings, get_cosk_config
from cosk.extraction.models import SkeletonNode
from cosk.extraction.query_loader import load_query_text
from cosk.extraction.registry import build_extension_registry
from cosk.extraction.summarizers import load_summarizer


def extract_skeleton_nodes(
    directory: str | Path | None = None,
    *,
    summarize: bool = False,
    config: CoskConfig | None = None,
) -> list[SkeletonNode]:
    resolved_config = config or get_cosk_config()
    root = Path(directory) if directory is not None else Path(resolved_config.extraction.source_directory)
    results: list[SkeletonNode] = []
    for file_path in _iter_supported_files(root, resolved_config):
        results.extend(extract_file_skeleton_nodes(file_path, summarize=summarize, config=resolved_config))
    return results


def extract_file_skeleton_nodes(
    file_path: str | Path,
    *,
    summarize: bool = False,
    config: CoskConfig | None = None,
) -> list[SkeletonNode]:
    resolved_config = config or get_cosk_config()
    path = Path(file_path)
    registry = build_extension_registry(resolved_config)
    language_setting = registry.get(path.suffix)
    if language_setting is None:
        return []

    query_text = load_query_text(language_setting.query_file, strict=resolved_config.extraction.strict)
    if query_text is None:
        return []

    source = path.read_bytes()
    summarizer_settings = resolved_config.extraction.summarizer
    summarizer = load_summarizer(summarizer_settings.callable_path) if summarize else None

    try:
        parser = _build_parser(language_setting)
    except Exception as exc:
        if language_setting.name == "python":
            return _extract_python_nodes_with_ast(
                source=source,
                path=path,
                summarize=summarize,
                summarizer=summarizer,
                summarizer_kwargs=summarizer_settings.kwargs,
                language_name=language_setting.name,
            )
        if resolved_config.extraction.strict:
            raise
        warnings.warn(f"Skipping file due to unavailable grammar package: {path} ({exc})", RuntimeWarning, stacklevel=2)
        return []

    try:
        tree = _parse_tree(parser, source)
    except Exception as exc:
        if resolved_config.extraction.strict:
            raise
        warnings.warn(f"Skipping file due to parse failure: {path} ({exc})", RuntimeWarning, stacklevel=2)
        return []

    query = parser.language.query(query_text)
    captures_by_name = _collect_captures(query.captures(tree.root_node))
    definitions = sorted(captures_by_name.get("definition", []), key=lambda node: node.start_byte)
    signature_nodes = captures_by_name.get("signature", [])
    docstring_nodes = captures_by_name.get("docstring", [])

    nodes: list[SkeletonNode] = []
    for definition in definitions:
        start_line = definition.start_point[0] + 1
        end_line = definition.end_point[0] + 1
        signature = _extract_signature(source, definition, signature_nodes)
        docstring = _extract_docstring(source, definition, docstring_nodes)
        if summarize and summarizer and not docstring:
            docstring = summarizer(
                signature,
                file_path=path.resolve().as_posix(),
                language=language_setting.name,
                **summarizer_settings.kwargs,
            )
        nodes.append(
            SkeletonNode(
                file_path=path.resolve().as_posix(),
                start_line=start_line,
                end_line=end_line,
                raw_signature=signature,
                docstring=docstring,
            )
        )
    return nodes


def skeleton_nodes_to_json(nodes: Sequence[SkeletonNode]) -> list[dict[str, object]]:
    return [asdict(node) for node in nodes]


@dataclass(frozen=True, slots=True)
class _GitIgnoreScope:
    directory: Path
    raw_lines: tuple[str, ...]


def _load_gitignore_lines(directory: Path) -> tuple[str, ...]:
    gitignore_path = directory / ".gitignore"
    if not gitignore_path.is_file():
        return ()
    return tuple(gitignore_path.read_text(encoding="utf-8").splitlines())


def _scoped_patterns(root: Path, scope_dir: Path, raw_lines: tuple[str, ...]) -> list[str]:
    prefix = scope_dir.relative_to(root).as_posix() if scope_dir != root else ""
    scoped: list[str] = []
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        negated = stripped.startswith("!")
        pattern = stripped[1:] if negated else stripped
        anchored = pattern.startswith("/")
        pattern_body = pattern[1:] if anchored else pattern
        if not pattern_body:
            continue

        has_slash = "/" in pattern_body
        if anchored or has_slash:
            transformed_patterns = [f"{prefix}/{pattern_body}" if prefix else pattern_body]
        else:
            if prefix:
                transformed_patterns = [f"{prefix}/{pattern_body}", f"{prefix}/**/{pattern_body}"]
            else:
                transformed_patterns = [pattern_body, f"**/{pattern_body}"]

        for transformed in transformed_patterns:
            scoped.append(f"!{transformed}" if negated else transformed)
    return scoped


def _compile_scoped_gitignore(
    root: Path, scopes: tuple[_GitIgnoreScope, ...]
) -> pathspec.GitIgnoreSpec | None:
    patterns: list[str] = []
    for scope in scopes:
        patterns.extend(_scoped_patterns(root, scope.directory, scope.raw_lines))
    if not patterns:
        return None
    return pathspec.GitIgnoreSpec.from_lines(patterns)


def _matches_gitignore(spec: pathspec.GitIgnoreSpec | None, relative_path: str, *, is_dir: bool) -> bool:
    if spec is None:
        return False
    normalized = relative_path.replace("\\", "/")
    candidate = f"{normalized}/" if is_dir and not normalized.endswith("/") else normalized
    return spec.match_file(candidate)


def _iter_supported_files(root: Path, config: CoskConfig) -> list[Path]:
    files: list[Path] = []
    extension_registry = build_extension_registry(config)
    respect_gitignore = config.extraction.respect_gitignore
    scope_cache: dict[Path, tuple[_GitIgnoreScope, ...]] = {}
    spec_cache: dict[Path, pathspec.GitIgnoreSpec | None] = {}

    if respect_gitignore:
        root_lines = _load_gitignore_lines(root)
        root_scopes = (_GitIgnoreScope(root, root_lines),) if root_lines else ()
        scope_cache[root] = root_scopes
        spec_cache[root] = _compile_scoped_gitignore(root, root_scopes)

    for current_root, dir_names, file_names in os.walk(
        root, followlinks=config.extraction.follow_symlinks
    ):
        current_path = Path(current_root)
        active_spec = None
        active_scopes: tuple[_GitIgnoreScope, ...] = ()
        if respect_gitignore:
            active_scopes = scope_cache.get(current_path, ())
            active_spec = spec_cache.get(current_path)

        retained_dirs: list[str] = []
        for dir_name in sorted(dir_names):
            if dir_name in config.extraction.exclude_dirs:
                continue
            child_dir = current_path / dir_name
            relative_dir = child_dir.relative_to(root).as_posix()
            if respect_gitignore and _matches_gitignore(active_spec, relative_dir, is_dir=True):
                continue
            retained_dirs.append(dir_name)

            if respect_gitignore:
                child_lines = _load_gitignore_lines(child_dir)
                child_scopes = (
                    (*active_scopes, _GitIgnoreScope(child_dir, child_lines))
                    if child_lines
                    else active_scopes
                )
                scope_cache[child_dir] = child_scopes
                spec_cache[child_dir] = _compile_scoped_gitignore(root, child_scopes)

        dir_names[:] = retained_dirs
        for file_name in sorted(file_names):
            candidate = Path(current_root) / file_name
            if respect_gitignore:
                relative_file = candidate.relative_to(root).as_posix()
                if _matches_gitignore(active_spec, relative_file, is_dir=False):
                    continue
            if candidate.suffix in extension_registry:
                files.append(candidate)
    return files


def _build_parser(language_setting: LanguageSettings) -> Parser:
    module = import_module(language_setting.grammar_package)
    language_factory = getattr(module, language_setting.grammar_module)
    language_object = language_factory() if callable(language_factory) else language_factory
    language = language_object if isinstance(language_object, Language) else Language(language_object)
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        parser.language = language
        return parser


def _parse_tree(parser: Parser, source: bytes):
    return parser.parse(source)


def _collect_captures(raw_captures: object) -> dict[str, list[object]]:
    captures: dict[str, list[object]] = defaultdict(list)
    if isinstance(raw_captures, dict):
        for capture_name, nodes in raw_captures.items():
            captures[capture_name].extend(nodes)
        return captures

    for node, capture_name in raw_captures:  # type: ignore[misc]
        captures[capture_name].append(node)
    return captures


def _extract_signature(source: bytes, definition, signature_nodes: list[object]) -> str:
    for signature_node in signature_nodes:
        if definition.start_byte <= signature_node.start_byte and signature_node.end_byte <= definition.end_byte:
            text = source[signature_node.start_byte : signature_node.end_byte].decode("utf-8").strip()
            if text:
                return text
    line = source.decode("utf-8").splitlines()[definition.start_point[0]]
    return line.strip()


def _extract_docstring(source: bytes, definition, docstring_nodes: list[object]) -> str:
    for docstring_node in docstring_nodes:
        if definition.start_byte <= docstring_node.start_byte and docstring_node.end_byte <= definition.end_byte:
            return source[docstring_node.start_byte : docstring_node.end_byte].decode("utf-8").strip()
    return ""


def _extract_python_nodes_with_ast(
    *,
    source: bytes,
    path: Path,
    summarize: bool,
    summarizer,
    summarizer_kwargs: dict,
    language_name: str,
) -> list[SkeletonNode]:
    source_text = source.decode("utf-8")
    parsed = ast.parse(source_text)
    source_lines = source_text.splitlines()
    collected_nodes = [
        node for node in ast.walk(parsed) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    collected_nodes.sort(key=lambda item: (item.lineno, item.col_offset))

    result: list[SkeletonNode] = []
    for node in collected_nodes:
        signature = source_lines[node.lineno - 1].strip()
        docstring = _ast_docstring_literal(source_text, node)
        if summarize and summarizer and not docstring:
            docstring = summarizer(
                signature,
                file_path=path.resolve().as_posix(),
                language=language_name,
                **summarizer_kwargs,
            )
        result.append(
            SkeletonNode(
                file_path=path.resolve().as_posix(),
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                raw_signature=signature,
                docstring=docstring,
            )
        )
    return result


def _ast_docstring_literal(source_text: str, node: ast.AST) -> str:
    body = getattr(node, "body", [])
    if not body:
        return ""
    first_statement = body[0]
    if not isinstance(first_statement, ast.Expr):
        return ""
    value = first_statement.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return ""
    literal = ast.get_source_segment(source_text, value)
    return literal.strip() if isinstance(literal, str) else ""
