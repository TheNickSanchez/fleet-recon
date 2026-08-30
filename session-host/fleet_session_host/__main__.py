"""Entrypoint: ``uv run python -m fleet_session_host`` (from ``session-host/``).

Binds privately to ``SESSION_HOST_HOST:SESSION_HOST_PORT`` (default
``127.0.0.1:8100``). Not an open proxy -- do not change the bind address to
``0.0.0.0`` without adding real authentication first.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from .settings import get_settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    problems = settings.check_skeleton()
    for problem in problems:
        logging.getLogger("fleet_session_host").warning("startup check: %s", problem)

    uvicorn.run(
        "fleet_session_host.api:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
