"""Host script runner for the ``asset_ops`` route (SAD §2.2/§2.3, PRD FR-2/FR-3).

Any pasted name list or CSV upload lands here. The host writes a temp
username CSV, then subprocesses ``asset_report_build.py`` (passkey
``servicenow``) followed by ``asset_report_mdm.py`` (passkey ``jamf_api`` +
``intune``) with a **fixed argv** -- never unconstrained Bash, never a shell
string built from chat text. The model is handed the printed stdout summary
only; the CSV body and the identity list never enter model context.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .csv_preview import CsvPreview, build_csv_preview
from .settings import Settings

BUILD_SCRIPT = "asset_report_build.py"
MDM_SCRIPT = "asset_report_mdm.py"

# Always requested for this skill: the requestor asked for the users'
# devices, and this drops iPad/Android/ChromeOS/Virtual Desktop rows that
# have no MDM to dispatch to (see docs/.claude/skills/asset-ops/SKILL.md).
DEVICE_PLATFORMS = "macOS,Windows"

SUBPROCESS_TIMEOUT_S = 600
STDOUT_SUMMARY_MAX_CHARS = 4000

_USERNAME_COLUMN_CANDIDATES = ("usernames", "username", "email", "user email", "user_email")

AssetOpsStatus = Literal["completed", "partial", "failed"]


class AssetOpsDiagnostic(RuntimeError):
    """Raised for conditions the operator must fix (missing passkey, etc.)."""


@dataclass(frozen=True)
class StepResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AssetOpsResult:
    status: AssetOpsStatus
    diagnostic: str | None
    csv_preview: dict | None
    step1_summary: str
    step2_summary: str


def _require_passkey() -> str:
    passkey_path = shutil.which("passkey")
    if not passkey_path:
        raise AssetOpsDiagnostic(
            "passkey is not on PATH. asset_ops requires profiles: servicenow, jamf_api, intune. "
            "Install/configure passkey, then retry."
        )
    return passkey_path


def _tail(text: str, limit: int = STDOUT_SUMMARY_MAX_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[-limit:]


def write_identities_csv(identities: list[str], tmp_dir: Path, run_id: str) -> Path:
    """Pasted-name-list path: write a minimal 'Usernames' CSV (SFS §4.3)."""
    path = tmp_dir / f"{run_id}-usernames.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("Usernames\n")
        for identity in identities:
            fh.write(f"{identity}\n")
    return path


def save_uploaded_csv(csv_bytes: bytes, tmp_dir: Path, run_id: str) -> Path:
    """CSV-upload path: persist the upload as-is. The scripts already handle
    every header variant (Usernames/Username/Email/User Email) and strip
    domains themselves -- the host does not need to rewrite it."""
    path = tmp_dir / f"{run_id}-upload.csv"
    path.write_bytes(csv_bytes)
    return path


def count_csv_identities(csv_bytes: bytes) -> int:
    """Best-effort unique-identity count for the run summary only. Mirrors
    asset_report_build.py's column detection and username normalization
    without importing that module (scripts are invoked, never imported)."""
    import io

    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str).fillna("")
    column = None
    for col in df.columns:
        if str(col).strip().casefold() in _USERNAME_COLUMN_CANDIDATES:
            column = col
            break
    if column is None:
        return 0
    values = {
        str(v).strip().casefold().split("@", 1)[0]
        for v in df[column]
        if str(v).strip()
    }
    return len(values)


def _run_subprocess(argv: list[str], cwd: Path) -> StepResult:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )
    return StepResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _build_step1_argv(python_exe: str, script_path: Path, input_csv: Path, report_csv: Path) -> list[str]:
    return [
        "passkey", "run", "servicenow", "--",
        python_exe, str(script_path),
        "--location", str(input_csv),
        "--output", str(report_csv),
        "--platforms", DEVICE_PLATFORMS,
    ]


def _build_step2_argv(python_exe: str, script_path: Path, report_csv: Path) -> list[str]:
    return [
        "passkey", "run", "jamf_api", "--",
        "passkey", "run", "intune", "--",
        python_exe, str(script_path),
        "--location", str(report_csv),
    ]


def run_asset_ops(
    run_id: str,
    settings: Settings,
    identities: list[str] | None = None,
    csv_bytes: bytes | None = None,
) -> AssetOpsResult:
    """Execute steps 1 then 2 for a name list or CSV upload. Returns a result
    with ``chat.csv_preview`` when a report file exists, even on partial
    failure (SAD §2.7: a failed source is a result state, not a crash)."""
    try:
        _require_passkey()
    except AssetOpsDiagnostic as exc:
        return AssetOpsResult(
            status="failed", diagnostic=str(exc), csv_preview=None, step1_summary="", step2_summary=""
        )

    scripts_dir = settings.asset_ops_scripts_dir
    build_script = scripts_dir / BUILD_SCRIPT
    mdm_script = scripts_dir / MDM_SCRIPT
    if not build_script.is_file() or not mdm_script.is_file():
        return AssetOpsResult(
            status="failed",
            diagnostic=f"asset-ops scripts not found under ASSET_OPS_SCRIPTS_DIR={scripts_dir}",
            csv_preview=None,
            step1_summary="",
            step2_summary="",
        )

    if csv_bytes is not None:
        input_csv = save_uploaded_csv(csv_bytes, settings.session_tmp_dir, run_id)
    else:
        input_csv = write_identities_csv(identities or [], settings.session_tmp_dir, run_id)

    report_csv = settings.session_reports_dir / f"devices-{run_id}.csv"
    python_exe = sys.executable

    step1 = _run_subprocess(
        _build_step1_argv(python_exe, build_script, input_csv, report_csv), cwd=scripts_dir
    )
    if not report_csv.is_file():
        return AssetOpsResult(
            status="failed",
            diagnostic=f"asset_report_build.py did not produce a report (exit {step1.returncode}).",
            csv_preview=None,
            step1_summary=_tail(step1.stdout + step1.stderr),
            step2_summary="",
        )

    step2 = _run_subprocess(_build_step2_argv(python_exe, mdm_script, report_csv), cwd=scripts_dir)

    preview: CsvPreview = build_csv_preview(
        report_path=report_csv,
        filename=f"devices-{run_id}.csv",
        file_ref=report_csv.name,
    )

    if step2.returncode != 0:
        return AssetOpsResult(
            status="partial",
            diagnostic=f"asset_report_mdm.py exited {step2.returncode}; device rows from step 1 are still returned.",
            csv_preview=preview.to_dict(),
            step1_summary=_tail(step1.stdout + step1.stderr),
            step2_summary=_tail(step2.stdout + step2.stderr),
        )

    return AssetOpsResult(
        status="completed",
        diagnostic=None,
        csv_preview=preview.to_dict(),
        step1_summary=_tail(step1.stdout + step1.stderr),
        step2_summary=_tail(step2.stdout + step2.stderr),
    )
