"""Thin private HTTP API (SAD §4.2 minimum subset; this persona's scope only).

Binds to ``SESSION_HOST_HOST:SESSION_HOST_PORT`` (default ``127.0.0.1:8100``).
No CORS middleware -- same-origin only, for a later Vite proxy. No admin
routes, no OIDC, no canvas, no action-confirm. This is not an open proxy to
MCP or passkey: every route either runs the deterministic preprocessor or
reads back an already-computed run record.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .asset_ops import count_csv_identities, run_asset_ops
from .device_lookup import run_device_lookup
from .preprocessor import bind_skill
from .runs import Run, get_store
from .settings import Settings, get_settings

logger = logging.getLogger("fleet_session_host")

MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 MiB, matches SFS §3 upload limit.


def _error(code: str, message: str, status_code: int, correlation_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}, "correlation_id": correlation_id},
        status_code=status_code,
    )


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def ready(_request: Request) -> JSONResponse:
    settings = get_settings()
    problems = settings.check_skeleton()
    return JSONResponse({"status": "ok" if not problems else "degraded", "problems": problems})


async def create_run(request: Request) -> JSONResponse:
    settings = get_settings()
    content_type = request.headers.get("content-type", "")

    text = ""
    csv_bytes: bytes | None = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            return _error("VALIDATION_ERROR", "multipart upload must include a 'file' field.", 400)
        csv_bytes = await upload.read()
        if len(csv_bytes) > MAX_CSV_BYTES:
            return _error("VALIDATION_ERROR", "CSV exceeds the 5 MiB upload limit.", 400)
        text = str(form.get("text", "") or "")
    else:
        try:
            payload: dict[str, Any] = await request.json()
        except Exception:
            payload = {}
        text = str(payload.get("text", "") or "")

    has_csv = csv_bytes is not None
    bind = bind_skill(text, has_csv=has_csv)

    if bind.rejected:
        return _error("VALIDATION_ERROR", bind.rejection_reason, 400)

    store = get_store()

    if bind.mode == "asset_ops":
        input_count = count_csv_identities(csv_bytes) if has_csv else bind.input_count
        run = store.create(
            mode="asset_ops",
            input_kind="csv" if has_csv else "text",
            input_count=input_count,
            intent_id="asset-ops",
            status="queued",
        )
        asyncio.create_task(_process_asset_ops(run.id, settings, list(bind.identities), csv_bytes))
    else:
        run = store.create(
            mode="device_lookup",
            input_kind="text",
            input_count=1,
            intent_id="device-lookup",
            status="queued",
        )
        asyncio.create_task(_process_device_lookup(run.id, settings, bind.identities[0], text))

    return JSONResponse(run.to_summary(), status_code=202)


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    run = get_store().get(run_id)
    if run is None:
        return _error("NOT_FOUND", f"No run with id {run_id}.", 404, correlation_id=run_id)
    return JSONResponse(run.to_summary())


def _mark_failed(run_id: str, diagnostic: str) -> None:
    get_store().update(
        run_id,
        status="failed",
        diagnostic=diagnostic,
        error={"code": "RUN_FAILED", "message": diagnostic},
    )


async def _process_asset_ops(
    run_id: str, settings: Settings, identities: list[str], csv_bytes: bytes | None
) -> None:
    store = get_store()
    store.update(run_id, status="running")
    try:
        result = await run_in_threadpool(
            run_asset_ops, run_id, settings, identities, csv_bytes
        )
    except Exception as exc:  # noqa: BLE001 - never crash the host on a bad run
        logger.exception("asset_ops run %s failed", run_id)
        _mark_failed(run_id, f"asset_ops crashed: {exc}")
        return

    if result.status == "failed":
        _mark_failed(run_id, result.diagnostic or "asset_ops failed with no report file.")
        return

    store.update(run_id, status=result.status, result=result.csv_preview, diagnostic=result.diagnostic)


async def _process_device_lookup(run_id: str, settings: Settings, identifier: str, raw_text: str) -> None:
    store = get_store()
    store.update(run_id, status="running")
    try:
        result = await run_device_lookup(identifier, raw_text, settings)
    except Exception as exc:  # noqa: BLE001
        logger.exception("device_lookup run %s failed", run_id)
        _mark_failed(run_id, f"device_lookup crashed: {exc}")
        return

    if result.status == "failed":
        _mark_failed(run_id, result.diagnostic or "device_lookup failed.")
        return

    store.update(run_id, status="completed", result=result.card)


routes = [
    Route("/api/v1/health", health, methods=["GET"]),
    Route("/api/v1/ready", ready, methods=["GET"]),
    Route("/api/v1/runs", create_run, methods=["POST"]),
    Route("/api/v1/runs/{run_id}", get_run, methods=["GET"]),
]

app = Starlette(routes=routes)
