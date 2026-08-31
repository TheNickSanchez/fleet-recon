"""Thin private HTTP API (product pivot 2026-08-31 -- see backend.md Audit).

Binds to ``SESSION_HOST_HOST:SESSION_HOST_PORT`` (default ``127.0.0.1:8100``).
No CORS middleware -- same-origin only, via a Vite proxy. No admin routes, no
OIDC. Every message is one turn of a general chat session (``chat.py``); the
old mode-routing preprocessor is gone -- see chat.py's module docstring for
why.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .chat import run_chat_turn
from .runs import get_store
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


def _build_prompt(text: str, csv_path: Path | None) -> str:
    if csv_path is None:
        return text
    note = (
        f'The user also uploaded a CSV, saved at: {csv_path}. If relevant, call '
        f"build_asset_report with csv_path=\"{csv_path}\"."
    )
    return f"{text}\n\n{note}" if text else note


async def create_run(request: Request) -> JSONResponse:
    settings = get_settings()
    content_type = request.headers.get("content-type", "")

    text = ""
    csv_bytes: bytes | None = None
    thread_id = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            csv_bytes = await upload.read()
            if len(csv_bytes) > MAX_CSV_BYTES:
                return _error("VALIDATION_ERROR", "CSV exceeds the 5 MiB upload limit.", 400)
        text = str(form.get("text", "") or "").strip()
        thread_id = str(form.get("thread_id", "") or "").strip()
    else:
        try:
            payload: dict[str, Any] = await request.json()
        except Exception:
            payload = {}
        text = str(payload.get("text", "") or "").strip()
        thread_id = str(payload.get("thread_id", "") or "").strip()

    has_csv = csv_bytes is not None
    if not text and not has_csv:
        return _error("VALIDATION_ERROR", "Type a message or attach a CSV.", 400)

    thread_id = thread_id or str(uuid.uuid4())

    store = get_store()
    run = store.create(thread_id=thread_id, input_kind="csv" if has_csv else "text")

    csv_path: Path | None = None
    if has_csv:
        settings.session_tmp_dir.mkdir(parents=True, exist_ok=True)
        csv_path = settings.session_tmp_dir / f"{run.id}-upload.csv"
        csv_path.write_bytes(csv_bytes)

    prompt = _build_prompt(text, csv_path)
    asyncio.create_task(_process_chat_turn(run.id, settings, thread_id, prompt))

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


async def _process_chat_turn(run_id: str, settings: Settings, thread_id: str, prompt: str) -> None:
    store = get_store()
    store.update(run_id, status="running")
    store.append_activity(run_id, "Connecting to the session...")
    history = store.get_thread_history(thread_id)
    try:
        result = await run_chat_turn(
            run_id, prompt, settings, history, on_progress=lambda line: store.append_activity(run_id, line)
        )
    except Exception as exc:  # noqa: BLE001 - never crash the host on a bad run
        logger.exception("chat run %s failed", run_id)
        _mark_failed(run_id, f"chat turn crashed: {exc}")
        return

    if result.status == "failed":
        _mark_failed(run_id, result.diagnostic or "chat turn failed.")
        return

    store.append_thread_history(thread_id, "user", prompt)
    store.append_thread_history(thread_id, "assistant", result.text or "")
    store.update(
        run_id,
        status="completed",
        result={"type": "chat.text", "text": result.text},
    )


routes = [
    Route("/api/v1/health", health, methods=["GET"]),
    Route("/api/v1/ready", ready, methods=["GET"]),
    Route("/api/v1/runs", create_run, methods=["POST"]),
    Route("/api/v1/runs/{run_id}", get_run, methods=["GET"]),
]

app = Starlette(routes=routes)
