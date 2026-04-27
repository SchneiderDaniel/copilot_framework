from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from cosk.config import TopKValidationError, resolve_top_k
from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest
from cosk.mcp.server import enrich_neighbor_entries, enrich_search_results, read_file_range


def create_http_app(manager: IndexManager):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import StreamingResponse
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("FastAPI is required for HTTP mode. Install with: pip install 'cosk[http]'") from exc

    app = FastAPI(title="cosk")

    @app.post("/v1/search")
    def search(payload: dict[str, object]):  # noqa: ANN001
        query = str(payload.get("query_string", ""))
        if not query.strip():
            raise HTTPException(status_code=400, detail="query_string must not be blank")
        try:
            top_k, warnings = resolve_top_k(payload.get("top_k"), manager.config)
        except TopKValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        context = manager.get_context(index_name=payload.get("index_name"))
        results = context.vector_store.search(query.strip(), top_k=top_k)
        enriched, token_warnings = enrich_search_results(results)
        return {
            "results": enriched,
            "top_k_requested": payload.get("top_k"),
            "top_k_applied": top_k,
            "warnings": [*warnings, *token_warnings],
        }

    @app.post("/v1/neighbors")
    def neighbors(payload: dict[str, object]):  # noqa: ANN001
        node_id = str(payload.get("node_id", ""))
        context = manager.get_context(index_name=payload.get("index_name"))
        enriched, warnings = enrich_neighbor_entries(context.vector_store, context.graph.get_neighbors(node_id))
        return {"inbound": enriched["inbound"], "outbound": enriched["outbound"], "warnings": warnings}

    @app.post("/v1/find-usage")
    def find_usage(payload: dict[str, object]):  # noqa: ANN001
        entity_name = str(payload.get("entity_name", ""))
        context = manager.get_context(index_name=payload.get("index_name"))
        return context.graph.find_usages(entity_name)

    @app.post("/v1/expand")
    def expand(payload: dict[str, object]):  # noqa: ANN001
        file_path = str(payload.get("file_path", ""))
        start_line = int(payload.get("start_line", 0))
        end_line = int(payload.get("end_line", 0))
        context = manager.get_context(index_name=payload.get("index_name"))
        return {"content": read_file_range(file_path, start_line, end_line, context_target_dir=context.target_dir)}

    @app.post("/v1/index")
    def index(payload: dict[str, object]):  # noqa: ANN001
        target_dir = Path(str(payload["target_dir"]))
        result = manager.sync(
            IndexBuildRequest(
                name=payload.get("name"),
                target_dir=target_dir,
                db_dir=Path(str(payload["db_dir"])) if payload.get("db_dir") else None,
                incremental=bool(payload.get("incremental", False)),
                config=manager.config,
            )
        )
        return dataclasses.asdict(result)

    @app.get("/v1/registry")
    def registry():  # noqa: ANN201
        return manager.list_registry()

    @app.get("/v1/events/search")
    def search_events(query_string: str, top_k: int | None = None, index_name: str | None = None):  # noqa: ANN201
        def _events():
            context = manager.get_context(index_name=index_name)
            resolved_top_k, warnings = resolve_top_k(top_k, manager.config)
            yield f"event: meta\ndata: {json.dumps({'top_k': resolved_top_k, 'warnings': warnings})}\n\n"
            results = context.vector_store.search(query_string, top_k=resolved_top_k)
            enriched, token_warnings = enrich_search_results(results)
            for result in enriched:
                yield f"event: result\ndata: {json.dumps(result)}\n\n"
            yield f"event: done\ndata: {json.dumps({'warnings': token_warnings})}\n\n"

        return StreamingResponse(_events(), media_type="text/event-stream")

    @app.get("/v1/events/index")
    def index_events(
        target_dir: str,
        name: str | None = None,
        incremental: bool = False,
        db_dir: str | None = None,
    ):  # noqa: ANN201
        def _events():
            yield "event: started\ndata: {}\n\n"
            try:
                result = manager.sync(
                    IndexBuildRequest(
                        name=name,
                        target_dir=Path(target_dir),
                        db_dir=Path(db_dir) if db_dir else None,
                        incremental=incremental,
                        config=manager.config,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
                return
            yield f"event: completed\ndata: {json.dumps(dataclasses.asdict(result))}\n\n"

        return StreamingResponse(_events(), media_type="text/event-stream")

    return app


def run_http_server(manager: IndexManager, host: str, port: int) -> None:
    try:
        import uvicorn
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("uvicorn is required for HTTP mode. Install with: pip install 'cosk[http]'") from exc
    uvicorn.run(create_http_app(manager), host=host, port=port)

