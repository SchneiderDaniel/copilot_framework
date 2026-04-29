from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypedDict

import lancedb
import pyarrow as pa

from cosk.extraction.models import SkeletonNode
from cosk.indexing.embedding import (
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    _GEMINI_BATCH_LIMIT,
    build_node_embedding_text,
)

_EMBED_BATCH_SIZE = _GEMINI_BATCH_LIMIT


def _embed_all(
    provider: EmbeddingProvider,
    texts: list[str],
    on_node_embedded: Callable[[int, int], None] | None,
) -> list[list[float]]:
    """Embed all texts, batching 100 at a time if provider supports embed_batch."""
    total = len(texts)
    if not total:
        return []

    if hasattr(provider, "embed_batch"):
        vectors: list[list[float]] = []
        for start in range(0, total, _EMBED_BATCH_SIZE):
            chunk = texts[start : start + _EMBED_BATCH_SIZE]
            chunk_vectors = provider.embed_batch(chunk)  # type: ignore[attr-defined]
            vectors.extend(chunk_vectors)
            if on_node_embedded:
                for j in range(len(chunk_vectors)):
                    on_node_embedded(start + j + 1, total)
        return vectors

    # Sequential fallback for providers without embed_batch
    vectors = []
    for i, text in enumerate(texts, 1):
        vectors.append(provider.embed(text))
        if on_node_embedded:
            on_node_embedded(i, total)
    return vectors


class SkeletonNodeSearchResult(TypedDict):
    node_id: str
    file_path: str
    start_line: int
    end_line: int
    raw_signature: str
    summary: str


class SkeletonNodeVectorStore:
    _REQUIRED_COLUMNS = (
        "node_id",
        "file_path",
        "start_line",
        "end_line",
        "raw_signature",
        "summary",
        "vector",
    )

    def __init__(
        self,
        *,
        db_dir: Path | str | None = None,
        table_name: str = "skeleton_nodes",
        embedding_provider: EmbeddingProvider | None = None,
        model_name: str = "gemini-embedding-001",
        key_file: str = ".geminikey",
    ) -> None:
        self._db_dir = Path(db_dir) if db_dir is not None else Path(__file__).resolve().parent.parent / ".lancedb"
        self._table_name = table_name
        self._embedding_provider = embedding_provider or GeminiEmbeddingProvider(model_name=model_name, key_file=key_file)
        self._vector_dim: int | None = None

    @staticmethod
    def compute_node_id(node: SkeletonNode) -> str:
        digest = hashlib.sha256(f"{node.file_path}:{node.start_line}".encode("utf-8"))
        return digest.hexdigest()

    def _build_row(self, node: SkeletonNode, vector: list[float]) -> dict[str, object]:
        summary = node.docstring.strip() or node.raw_signature.strip()
        return {
            "node_id": self.compute_node_id(node),
            "file_path": node.file_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "raw_signature": node.raw_signature,
            "summary": summary,
            "vector": [float(v) for v in vector],
        }

    @staticmethod
    def _schema(vector_dim: int) -> pa.Schema:
        return pa.schema(
            [
                pa.field("node_id", pa.string()),
                pa.field("file_path", pa.string()),
                pa.field("start_line", pa.int64()),
                pa.field("end_line", pa.int64()),
                pa.field("raw_signature", pa.string()),
                pa.field("summary", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), vector_dim)),
            ]
        )

    def _connect(self):
        self._db_dir.mkdir(parents=True, exist_ok=True)
        return lancedb.connect(str(self._db_dir))

    def _open_table_if_exists(self, db):
        try:
            return db.open_table(self._table_name)
        except Exception:  # noqa: BLE001
            return None

    def _ensure_vector_dim_from_table(self, table) -> None:
        if self._vector_dim is not None:
            return
        try:
            vector_field = table.schema.field("vector")
            list_size = getattr(vector_field.type, "list_size", None)
            if isinstance(list_size, int) and list_size > 0:
                self._vector_dim = list_size
        except Exception:  # noqa: BLE001
            return

    def validate_index(self) -> bool:
        if not self._db_dir.exists():
            return False

        try:
            db = lancedb.connect(str(self._db_dir))
            table = self._open_table_if_exists(db)
            if table is None:
                return False
            schema = table.schema
            return all(schema.get_field_index(column) >= 0 for column in self._REQUIRED_COLUMNS)
        except Exception:  # noqa: BLE001
            return False

    def rebuild_index(
        self,
        nodes: Sequence[SkeletonNode],
        *,
        on_node_embedded: Callable[[int, int], None] | None = None,
    ) -> None:
        rows: list[dict[str, object]] = []
        vector_dim: int | None = None

        if nodes:
            texts = [build_node_embedding_text(n) for n in nodes]
            vectors = _embed_all(self._embedding_provider, texts, on_node_embedded)
            for node, vector in zip(nodes, vectors):
                if not vector:
                    raise ValueError("embedding vector must not be empty")
                if vector_dim is None:
                    vector_dim = len(vector)
                if len(vector) != vector_dim:
                    raise ValueError("embedding vector dimension mismatch across nodes")
                rows.append(self._build_row(node, vector))
        else:
            probe_vector = self._embedding_provider.embed("cosk-empty-index-probe")
            if not probe_vector:
                raise ValueError("embedding vector must not be empty")
            vector_dim = len(probe_vector)

        if vector_dim is None:
            raise ValueError("vector dimension is not initialized")

        self._vector_dim = vector_dim
        db = self._connect()
        staging_table_name = f"{self._table_name}__staging"
        db.drop_table(staging_table_name, ignore_missing=True)
        staging_table = db.create_table(staging_table_name, schema=self._schema(vector_dim))
        if rows:
            staging_table.add(rows)

        db.drop_table(self._table_name, ignore_missing=True)
        target_table = db.create_table(self._table_name, schema=self._schema(vector_dim))
        if rows:
            target_table.add(rows)
        db.drop_table(staging_table_name, ignore_missing=True)
        if not self.validate_index():
            raise RuntimeError("index rebuild failed validation")

    def upsert_nodes(
        self,
        nodes: Sequence[SkeletonNode],
        *,
        on_node_embedded: Callable[[int, int], None] | None = None,
    ) -> int:
        if not nodes:
            return 0

        rows: list[dict[str, object]] = []
        first_vector_dim: int | None = None

        texts = [build_node_embedding_text(n) for n in nodes]
        vectors = _embed_all(self._embedding_provider, texts, on_node_embedded)
        for node, vector in zip(nodes, vectors):
            if first_vector_dim is None:
                first_vector_dim = len(vector)
                if first_vector_dim == 0:
                    raise ValueError("embedding vector must not be empty")
            if len(vector) != first_vector_dim:
                raise ValueError("embedding vector dimension mismatch across nodes")
            rows.append(self._build_row(node, vector))

        if self._vector_dim is None and first_vector_dim is not None:
            self._vector_dim = first_vector_dim
        if first_vector_dim is not None and self._vector_dim != first_vector_dim:
            raise ValueError("embedding vector dimension mismatch with existing index")

        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            if self._vector_dim is None:
                raise ValueError("vector dimension is not initialized")
            table = db.create_table(self._table_name, schema=self._schema(self._vector_dim))
        else:
            self._ensure_vector_dim_from_table(table)

        (
            table.merge_insert("node_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )
        return len(nodes)

    def delete_by_file_paths(self, file_paths: Sequence[str]) -> int:
        if not file_paths:
            return 0
        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            return 0
        quoted = ", ".join(f"'{str(path).replace(chr(39), chr(39) * 2)}'" for path in file_paths)
        table.delete(f"file_path IN ({quoted})")
        return len(file_paths)

    def load_all_nodes(self) -> list[SkeletonNode]:
        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            return []
        rows = table.to_arrow().to_pylist()
        return [
            SkeletonNode(
                file_path=str(row["file_path"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                raw_signature=str(row["raw_signature"]),
                docstring=str(row["summary"]),
            )
            for row in rows
        ]

    def get_node_details(self, node_ids: Sequence[str]) -> dict[str, dict[str, object]]:
        if not node_ids:
            return {}
        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            return {}
        requested = set(node_ids)
        details: dict[str, dict[str, object]] = {}
        for row in table.to_arrow().to_pylist():
            db_node_id = str(row["node_id"])
            graph_node_id = f"{row['file_path']}:{row['start_line']}"
            payload = {
                "node_id": db_node_id,
                "graph_node_id": graph_node_id,
                "file_path": str(row["file_path"]),
                "start_line": int(row["start_line"]),
                "end_line": int(row["end_line"]),
                "raw_signature": str(row["raw_signature"]),
                "summary": str(row["summary"]),
            }
            if db_node_id in requested:
                details[db_node_id] = payload
            if graph_node_id in requested:
                details[graph_node_id] = payload
        return details

    def search(self, query: str, top_k: int = 5) -> list[SkeletonNodeSearchResult]:
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be > 0")

        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            return []

        self._ensure_vector_dim_from_table(table)
        query_vector = self._embedding_provider.embed(query)
        if not query_vector:
            raise ValueError("query embedding vector must not be empty")
        if self._vector_dim is not None and len(query_vector) != self._vector_dim:
            raise ValueError("query embedding vector dimension mismatch")

        rows = table.search([float(value) for value in query_vector]).limit(top_k).to_list()
        return [
            {
                "node_id": row["node_id"],
                "file_path": row["file_path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "raw_signature": row["raw_signature"],
                "summary": row["summary"],
            }
            for row in rows
        ]

    @staticmethod
    def _extract_symbol_name(raw_signature: str) -> str:
        signature = raw_signature.strip()
        class_match = re.match(r"^class\s+([A-Za-z_]\w*)", signature)
        if class_match:
            return class_match.group(1)
        function_match = re.match(r"^(?:async\s+def|def)\s+([A-Za-z_]\w*)", signature)
        if function_match:
            return function_match.group(1)
        return signature

    @staticmethod
    def _is_class_signature(raw_signature: str) -> bool:
        return bool(re.match(r"^\s*class\s+[A-Za-z_]\w*", raw_signature))

    @staticmethod
    def _is_function_signature(raw_signature: str) -> bool:
        return bool(re.match(r"^\s*(?:async\s+def|def)\s+[A-Za-z_]\w*", raw_signature))

    @staticmethod
    def _looks_like_regex(query: str) -> bool:
        return bool(re.search(r"(\\[AbBdDsSwWZ]|[\^\$\.\*\+\?\[\]\(\)\{\}\|])", query))

    @staticmethod
    def _line_within_any_span(line: int, spans: list[tuple[int, int]]) -> bool:
        return any(start <= line <= end for start, end in spans)

    def search_by_name(self, query: str, kind: str = "any") -> list[SkeletonNodeSearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be blank")

        normalized_kind = kind.strip().lower()
        valid_kinds = {"any", "function", "class", "method"}
        if normalized_kind not in valid_kinds:
            raise ValueError("kind must be one of: function, class, method, any")

        db = self._connect()
        table = self._open_table_if_exists(db)
        if table is None:
            return []

        rows = table.to_arrow().to_pylist()
        if not rows:
            return []

        class_spans_by_file: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for row in rows:
            raw_signature = str(row.get("raw_signature", ""))
            if self._is_class_signature(raw_signature):
                class_spans_by_file[str(row.get("file_path", ""))].append(
                    (int(row.get("start_line", 0)), int(row.get("end_line", 0)))
                )

        matcher = None
        if self._looks_like_regex(normalized_query):
            try:
                matcher = re.compile(normalized_query, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid regex query: {exc}") from exc
        lowered_query = normalized_query.lower()

        matches: list[SkeletonNodeSearchResult] = []
        for row in rows:
            raw_signature = str(row.get("raw_signature", ""))
            symbol_name = self._extract_symbol_name(raw_signature)
            file_path = str(row.get("file_path", ""))
            start_line = int(row.get("start_line", 0))

            inferred_kind = "other"
            if self._is_class_signature(raw_signature):
                inferred_kind = "class"
            elif self._is_function_signature(raw_signature):
                enclosed_by_class = self._line_within_any_span(start_line, class_spans_by_file[file_path])
                inferred_kind = "method" if enclosed_by_class else "function"

            if normalized_kind != "any" and inferred_kind != normalized_kind:
                continue

            searchable_text = symbol_name or raw_signature.strip()
            if matcher is not None:
                is_match = bool(matcher.search(searchable_text))
            else:
                is_match = lowered_query in searchable_text.lower()
            if not is_match:
                continue

            matches.append(
                {
                    "node_id": str(row["node_id"]),
                    "file_path": file_path,
                    "start_line": int(row["start_line"]),
                    "end_line": int(row["end_line"]),
                    "raw_signature": raw_signature,
                    "summary": str(row.get("summary", "")),
                }
            )
        return matches
