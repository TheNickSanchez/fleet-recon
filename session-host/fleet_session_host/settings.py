"""Environment configuration for the Fleet Recon session host.

Reads only the env names defined in ``.env.example`` / ``setup.md``. Never
invents ``DATABASE_URL``, ``CREWAI_*``, or an HTTP MCP URL. If a value is
missing, callers get a clear ``Diagnostic`` (see :class:`Diagnostic`) instead
of a stack trace, so the operator knows exactly what to fill in.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_HOST_ROOT = Path(__file__).resolve().parents[1]


class Diagnostic(RuntimeError):
    """A user-safe, actionable error. Never wraps a secret value."""


def _load_dotenv_if_present(path: Path) -> None:
    """Minimal ``.env`` loader (no extra dependency). Does not override an
    already-set environment variable, matching standard dotenv precedence."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    asset_ops_scripts_dir: Path
    session_tmp_dir: Path
    session_reports_dir: Path
    mcp_transport: str
    mcp_servers_config: Path
    anthropic_base_url: str
    anthropic_api_key: str
    litellm_model: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            host=_env("SESSION_HOST_HOST", "127.0.0.1"),
            port=int(_env("SESSION_HOST_PORT", "8100") or "8100"),
            asset_ops_scripts_dir=(
                REPO_ROOT / _env("ASSET_OPS_SCRIPTS_DIR", "docs/.claude/skills/asset-ops/scripts")
            ).resolve(),
            session_tmp_dir=(REPO_ROOT / _env("SESSION_TMP_DIR", "session-host/var/tmp")).resolve(),
            session_reports_dir=(
                REPO_ROOT / _env("SESSION_REPORTS_DIR", "session-host/var/reports")
            ).resolve(),
            mcp_transport=_env("MCP_TRANSPORT", "stdio"),
            mcp_servers_config=(
                REPO_ROOT / _env("MCP_SERVERS_CONFIG", "session-host/config/mcp.stdio.json")
            ).resolve(),
            anthropic_base_url=_env("ANTHROPIC_BASE_URL"),
            anthropic_api_key=_env("ANTHROPIC_API_KEY"),
            litellm_model=_env("LITELLM_MODEL"),
        )

    def ensure_dirs(self) -> None:
        self.session_tmp_dir.mkdir(parents=True, exist_ok=True)
        self.session_reports_dir.mkdir(parents=True, exist_ok=True)

    def check_skeleton(self) -> list[str]:
        """Return a list of human-readable problems. Empty means healthy.

        This never halts the process by itself -- callers decide whether a
        given problem should fail a request (asset_ops) or just show up in
        ``/api/v1/ready``.
        """
        problems: list[str] = []
        if not self.asset_ops_scripts_dir.is_dir():
            problems.append(f"ASSET_OPS_SCRIPTS_DIR not found: {self.asset_ops_scripts_dir}")
        if self.mcp_transport != "stdio":
            problems.append(
                f"MCP_TRANSPORT={self.mcp_transport!r} is not supported; only 'stdio' is implemented."
            )
        if shutil.which("passkey") is None:
            problems.append(
                "passkey is not on PATH. asset_ops requires profiles: servicenow, jamf_api, intune."
            )
        return problems


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
        _settings.ensure_dirs()
    return _settings
