from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cosk.config import CoskConfig, ExtractionSettings, LanguageSettings, SummarizerSettings
from cosk.extraction.models import SkeletonNode
from cosk.extraction.parser import extract_skeleton_nodes
from cosk.graph import state
from cosk.graph.builder import RelationshipGraph, rebuild
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.mcp.server import create_mcp_server
from cosk.safety import middleware


@pytest.fixture(autouse=True)
def isolated_registry_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    registry_path = tmp_path / ".cosk" / "registry.yaml"
    monkeypatch.setenv("COSK_REGISTRY_PATH", str(registry_path))
    return registry_path


@pytest.fixture
def progress_spy():
    class _ProgressSpy:
        def __init__(self) -> None:
            self.events: list[tuple[str, object]] = []

        def start(self, mode: str, total_files: int, deleted_files: int = 0) -> None:
            self.events.append(("start", {"mode": mode, "total_files": total_files, "deleted_files": deleted_files}))

        def advance(self, file_path: Path, extracted_nodes: int, skipped: bool = False) -> None:
            self.events.append(
                (
                    "advance",
                    {"file_path": Path(file_path), "extracted_nodes": extracted_nodes, "skipped": skipped},
                )
            )

        def record_issue(self, issue) -> None:  # noqa: ANN001
            self.events.append(("issue", issue))

        def finish(self, result, elapsed_seconds: float, issue_summary: dict[str, int]) -> None:  # noqa: ANN001
            self.events.append(
                (
                    "finish",
                    {
                        "result": result,
                        "elapsed_seconds": elapsed_seconds,
                        "issue_summary": issue_summary,
                    },
                )
            )

    return _ProgressSpy()


@pytest.fixture
def python_language_settings() -> LanguageSettings:
    return LanguageSettings(
        name="python",
        extensions=(".py",),
        grammar_package="tree_sitter_python",
        grammar_module="language",
        query_file="python.scm",
        enabled=True,
    )


@pytest.fixture
def base_config(python_language_settings: LanguageSettings) -> CoskConfig:
    return CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(python_language_settings,),
            summarizer=SummarizerSettings(),
        )
    )


@pytest.fixture
def python_file(tmp_path: Path) -> Path:
    target = tmp_path / "sample.py"
    target.write_text(
        "def hello(name: str) -> str:\n"
        "    \"\"\"Say hello.\"\"\"\n"
        "    value = name.strip()\n"
        "    for _ in range(1):\n"
        "        value = value.upper()\n"
        "    return f'Hello {value}'\n",
        encoding="utf-8",
    )
    return target


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_nodes(fixture_dir: Path, base_config: CoskConfig) -> list[SkeletonNode]:
    nodes = extract_skeleton_nodes(fixture_dir, config=base_config)
    assert nodes
    return nodes


class DeterministicEmbeddingProvider:
    def __init__(self) -> None:
        self._keywords = ("helper", "wrapper", "consume", "return", "def", "import", "from")

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        fallback_tokens = len([token for token in lowered.replace("\n", " ").split(" ") if token.strip()])
        return [*[float(lowered.count(keyword)) for keyword in self._keywords], float(fallback_tokens)]


@pytest.fixture
def deterministic_embedding_provider() -> DeterministicEmbeddingProvider:
    return DeterministicEmbeddingProvider()


@pytest.fixture
def indexed_vector_store(
    tmp_path: Path, deterministic_embedding_provider: DeterministicEmbeddingProvider
) -> SkeletonNodeVectorStore:
    return SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=deterministic_embedding_provider)


@pytest.fixture
def loaded_fixture_graph(fixture_nodes: list[SkeletonNode]) -> RelationshipGraph:
    graph = rebuild(fixture_nodes)
    yield graph
    state.clear_graph()


@pytest.fixture
def mcp_tools(
    indexed_vector_store: SkeletonNodeVectorStore,
    fixture_nodes: list[SkeletonNode],
    loaded_fixture_graph: RelationshipGraph,  # noqa: ARG001
) -> dict[str, Callable]:
    indexed_vector_store.upsert_nodes(fixture_nodes)
    mcp = create_mcp_server(indexed_vector_store)
    return {
        "cosk_search_by_name": mcp._tool_manager.get_tool("cosk_search_by_name").fn,  # noqa: SLF001
        "cosk_semantic_search": mcp._tool_manager.get_tool("cosk_semantic_search").fn,  # noqa: SLF001
        "cosk_get_neighbors": mcp._tool_manager.get_tool("cosk_get_neighbors").fn,  # noqa: SLF001
        "cosk_get_symbol_source": mcp._tool_manager.get_tool("cosk_get_symbol_source").fn,  # noqa: SLF001
        "cosk_find_usage": mcp._tool_manager.get_tool("cosk_find_usage").fn,  # noqa: SLF001
    }


@pytest.fixture(autouse=True)
def clear_shared_singletons() -> None:
    state.clear_graph()
    middleware._registry.clear()  # noqa: SLF001
    yield
    state.clear_graph()
    middleware._registry.clear()  # noqa: SLF001
