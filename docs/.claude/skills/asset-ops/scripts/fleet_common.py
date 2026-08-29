"""Shared helpers for the asset-ops pipeline.

Used by asset_report_build.py (step 1), asset_report_mdm.py (step 2),
asset_report_app.py (step 3), and jamf_group_sync.py (Jamf group sync).
Import-only — never run directly.

Design rules this module enforces:
  - Platform is carried forward from ServiceNow, never re-guessed from serial prefixes.
  - Extension-attribute names are matched on a normalized form, because Jamf mixes
    hyphens and en-dashes ("Compliance - Zscaler Status" vs "Compliance – Nessus – Connectivity").
  - Every enrichment step is idempotent: it overwrites its own columns rather than
    appending duplicates.
"""

import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

import pandas as pd

DEFAULT_REPORT = "input/output/asset_report.csv"

# Step 1 schema. Steps 2 and 3 append to the right of this.
BASE_COLUMNS = [
    "Username",
    "Serial",
    "Platform",
    "State",
    "Substate",
    "Model",
    "Asset Tag",
    "Notes",
]

# Rows with these Platform values have no serial to look up.
OUTLIER_PLATFORMS = ("No Device Assigned", "Not Found in SN")

PLATFORM_ORDER = {
    "macOS": 0,
    "Windows": 1,
    "iOS/iPadOS": 2,
    "Android": 3,
    "ChromeOS": 4,
    "Virtual Desktop": 5,
    "Unknown": 6,
    "No Device Assigned": 7,
    "Not Found in SN": 8,
}

# Platforms with a real serial but no Jamf-computer or Intune record to look up.
# Named individually so a skip never reads as "we couldn't identify this device".
UNMANAGED_PLATFORMS = {
    "iOS/iPadOS": "mobile device",
    "Android": "mobile device",
    "ChromeOS": "chromeos device",
    "Virtual Desktop": "virtual desktop",
}

# ServiceNow serial_number is free text, so placeholders land in it. These are not
# serials: querying them wastes a call and returns a false "Not Found in <MDM>",
# which reads as an enrollment gap rather than a ServiceNow data-entry problem.
PLACEHOLDER_SERIALS = {
    "PENDING", "NONE", "N/A", "NA", "UNKNOWN", "TBD", "NULL", "-", "0",
    "NOSERIAL", "NO SERIAL", "TOBEDETERMINED", "XXXXXXX",
}


def is_real_serial(serial):
    """A serial we can actually look up in an MDM."""
    text = str(serial or "").strip().upper()
    return bool(text) and text not in PLACEHOLDER_SERIALS and len(text) >= 5


# --------------------------------------------------------------------------- env


def require_env(names, profile):
    """Exit with a copy-pasteable passkey command if any credential is missing."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        script = os.path.basename(sys.argv[0])
        print(f"[-] Missing required environment credentials: {', '.join(missing)}")
        print(f"    Run via: passkey run {profile} -- .venv/bin/python scripts/{script} ...")
        sys.exit(1)


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------- matching

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def normalize_label(text):
    """Casefold, unify every dash variant to '-', collapse whitespace.

    Jamf EA names are not consistent about dash characters, so a raw substring
    match silently misses attributes. Always compare through this.
    """
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).translate(_DASHES)).strip().casefold()


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().casefold()).strip("_")


def extension_attributes(payload):
    """Flatten a Jamf computers-inventory record's EAs to {name: value}.

    Handles the four shapes Jamf returns them in (top-level or nested under
    'general', snake or camel case), each of which may be a dict or a list of
    {name, value, values}. First write wins.
    """
    out = {}
    candidates = [
        payload.get("extensionAttributes"),
        payload.get("extension_attributes"),
        (payload.get("general") or {}).get("extensionAttributes"),
        (payload.get("general") or {}).get("extension_attributes"),
    ]
    for block in candidates:
        if not block:
            continue
        if isinstance(block, dict):
            items = block.items()
        else:
            items = [
                (ea.get("name"), ea.get("value") or ", ".join(ea.get("values") or []))
                for ea in block
                if isinstance(ea, dict)
            ]
        for name, value in items:
            if not name or name in out:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v not in (None, ""))
            out[name] = flatten_value(value)
    return out


def flatten_value(value):
    """Collapse an EA value to a single line, keeping every field.

    Some EAs return a multi-line block ("status = not enrolled\\ndeferrals = 1/3").
    Embedded newlines wreck the console summary and any grep/awk over the CSV, so
    join the lines with '; ' rather than dropping the extra detail.
    """
    if value is None:
        return ""
    lines = [ln.strip() for ln in str(value).splitlines() if ln.strip()]
    return re.sub(r"[ \t]+", " ", "; ".join(lines))


# --------------------------------------------------------------------------- csv


def load_report(path, required=("Serial", "Platform")):
    """Read the pipeline CSV, failing loudly if a prior step hasn't run."""
    if not os.path.exists(path):
        print(f"[-] Report not found: {path}")
        print("    Run step 1 first: scripts/asset_report_build.py --location input/<file>.csv")
        sys.exit(1)
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[-] {path} is missing required column(s): {', '.join(missing)}")
        print("    Re-run step 1 to regenerate the report with the current schema.")
        sys.exit(1)
    return df


def skip_reason(platform, serial):
    """Why a row was never looked up. Steps 2 and 3 both write this verbatim."""
    if platform in OUTLIER_PLATFORMS or not str(serial).strip():
        return "Skipped (no serial)"
    if not is_real_serial(serial):
        return "Skipped (placeholder serial)"
    if platform in UNMANAGED_PLATFORMS:
        return f"Skipped ({UNMANAGED_PLATFORMS[platform]})"
    return "Skipped (unknown platform)"


def lookup_rows(df):
    """Rows that have a real serial and a platform we can dispatch on.

    Returns (rows, skipped) where rows is a list of {index, Serial, Platform, Username}
    and skipped counts why everything else was left alone.
    """
    rows, skipped = [], {}
    for idx, row in df.iterrows():
        platform = str(row.get("Platform", "")).strip()
        serial = str(row.get("Serial", "")).strip().upper()
        if platform in OUTLIER_PLATFORMS or not is_real_serial(serial):
            reason = skip_reason(platform, serial)
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        if platform not in ("macOS", "Windows"):
            # Name the platform in the reason — "Virtual Desktop" has no MDM to
            # dispatch to, which is a different story from an unrecognized model.
            reason = skip_reason(platform, serial)
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        rows.append(
            {
                "index": idx,
                "Serial": serial,
                "Platform": platform,
                "Username": str(row.get("Username", "")).strip(),
            }
        )
    return rows, skipped


def write_report(df, path, columns=None, backup=True):
    """Back up the existing report, then rewrite it.

    Column order is preserved so each step's additions land to the right of
    whatever is already there.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if backup and os.path.exists(path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base, ext = os.path.splitext(path)
        shutil.copy2(path, f"{base}.bak-{stamp}{ext}")
    if columns:
        df = df.reindex(columns=columns)
    df.to_csv(path, index=False)


def set_columns(df, index_to_values, columns):
    """Idempotently write per-row values into named columns.

    Re-running a step overwrites its own columns instead of adding duplicates.
    """
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    for idx, values in index_to_values.items():
        for col in columns:
            df.at[idx, col] = values.get(col, "")
    return df


# ----------------------------------------------------------------------- output


def breakdown(values, top=None):
    """'a 12 · b 3' — compact enough for the agent to read instead of the CSV."""
    from collections import Counter

    counts = Counter(v for v in values if str(v).strip())
    items = counts.most_common(top) if top else sorted(counts.items())
    return " · ".join(f"{k} {v}" for k, v in items) or "none"


def stale_warning(path, max_age_hours):
    """Warn when an enrichment step is about to read a report that may be stale."""
    if not os.path.exists(path) or not max_age_hours:
        return
    age_h = (time.time() - os.path.getmtime(path)) / 3600.0
    if age_h > max_age_hours:
        print(f"[!] {path} is {age_h:.1f}h old (>{max_age_hours}h) — data may be stale.")


def write_summary_json(path, payload):
    """Append one JSONL telemetry object per run, mirroring jamf_group_sync.py."""
    if not path:
        return
    import json

    payload = dict(payload)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(payload) + "\n")


# --------------------------------------------------------------------- sessions

import threading

import requests

JAMF_ENV = ("JAMF_BASE_URL", "JAMF_CLIENT_ID", "JAMF_CLIENT_SECRET")
INTUNE_ENV = ("INTUNE_TENANT_ID", "INTUNE_CLIENT_ID", "INTUNE_CLIENT_SECRET")

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"

RETRY_STATUS = {429, 503, 504}


class _Session:
    """Shared token-refresh, retry, and call-counting behaviour."""

    def __init__(self, counters):
        self.http = requests.Session()
        self.token = None
        self.refresh_at = 0.0
        self.lock = threading.Lock()
        self.calls = dict.fromkeys(counters, 0)

    def _fetch_token(self):
        raise NotImplementedError

    def auth_header(self):
        with self.lock:
            if not self.token or time.time() >= self.refresh_at:
                self.token, self.refresh_at = self._fetch_token()
                self.calls["token"] += 1
            if not self.token:
                raise RuntimeError(f"{type(self).__name__}: token unavailable")
            return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, params=None, counter=None, retries=2):
        """GET with 401-refresh and bounded backoff on 429/503/504."""
        for attempt in range(retries + 1):
            headers = self.auth_header() | {"Accept": "application/json"}
            resp = self.http.get(url, headers=headers, params=params, timeout=30)
            if counter:
                with self.lock:
                    self.calls[counter] = self.calls.get(counter, 0) + 1
            if resp.status_code == 401 and attempt < retries:
                with self.lock:
                    self.token = None
                continue
            if resp.status_code in RETRY_STATUS and attempt < retries:
                delay = resp.headers.get("Retry-After")
                time.sleep(min(int(delay) if delay and delay.isdigit() else 2, 10))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"GET failed after {retries + 1} attempts: {url}")


class JamfSession(_Session):
    """Read-only Jamf Pro client. Batches serials into one RSQL inventory call."""

    def __init__(self):
        super().__init__(("token", "inventory", "detail"))
        self.base = os.environ["JAMF_BASE_URL"].rstrip("/")

    def _fetch_token(self):
        resp = self.http.post(
            f"{self.base}/api/oauth/token",
            data={
                "client_id": os.environ["JAMF_CLIENT_ID"],
                "client_secret": os.environ["JAMF_CLIENT_SECRET"],
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        # Refresh slightly early so a long batch can't expire mid-flight.
        return body.get("access_token"), time.time() + max(60, int(body.get("expires_in", 1800)) - 120)

    def inventory_batch(self, serials, sections):
        """Fetch a batch of serials in one call. Returns {SERIAL: record}.

        Jamf RSQL serial matching is case-sensitive, so callers must pass
        uppercase serials — lookup_rows() already guarantees that.
        """
        if not serials:
            return {}
        params = [("filter", ",".join(f'hardware.serialNumber=="{s}"' for s in serials))]
        params.append(("page-size", str(max(len(serials), 1))))
        for section in sections:
            params.append(("section", section))
        data = self.get(f"{self.base}/api/v1/computers-inventory", params=params, counter="inventory")
        found = {}
        for record in data.get("results", []):
            serial = ((record.get("hardware") or {}).get("serialNumber") or "").strip().upper()
            if serial:
                found[serial] = record
        return found


class IntuneSession(_Session):
    """Read-only Microsoft Graph client for Windows devices."""

    def __init__(self):
        super().__init__(("token", "device", "apps"))
        self.tenant = os.environ["INTUNE_TENANT_ID"]

    def _fetch_token(self):
        resp = self.http.post(
            f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token",
            data={
                "client_id": os.environ["INTUNE_CLIENT_ID"],
                "client_secret": os.environ["INTUNE_CLIENT_SECRET"],
                "grant_type": "client_credentials",
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("access_token"), time.time() + max(60, int(body.get("expires_in", 3600)) - 120)

    def find_device_by_serial(self, serial):
        params = {
            "$filter": f"serialNumber eq '{serial}'",
            "$select": "id,deviceName,serialNumber,userId,complianceState,"
            "managementAgent,lastSyncDateTime,operatingSystem,managedDeviceOwnerType",
            "$top": "1",
        }
        data = self.get(f"{GRAPH}/deviceManagement/managedDevices", params=params, counter="device")
        results = data.get("value") or []
        return results[0] if results else None

    def managed_app_states(self, user_id, device_id):
        data = self.get(
            f"{GRAPH_BETA}/users/{user_id}/mobileAppIntentAndStates('{device_id}')",
            counter="apps",
        )
        return data.get("mobileAppList", [])
