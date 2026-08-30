"""Intent + identity preprocessor (SAD §2.1, §2.5; PRD FR-1, FR-2).

Pure host code. Strips instruction stopwords, sanitizes/dedupes identities,
and binds the skill route (``device_lookup`` vs ``asset_ops``) deterministically
*before* any model or connector is involved. The model never sees this
decision get made and cannot change it mid-run.

Routing rule (SAD §2.5 / PRD FR-2 / SFS §4):
  - Exactly one identity (serial, hostname, or username), no CSV -> device_lookup
  - Any pasted name list (any count, including 4), or any CSV        -> asset_ops
  - Zero identities                                                  -> rejected
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["device_lookup", "asset_ops"]

# Instruction vocabulary that must never be treated as an identity. This is
# deliberately generous with common request phrasing rather than exhaustive --
# a real identity is virtually never a bare dictionary word from this set.
STOPWORDS: frozenset[str] = frozenset(
    {
        "look", "looking", "lookup", "up", "this", "that", "these", "those",
        "user", "users", "device", "devices", "serial", "serials", "hostname",
        "hostnames", "username", "usernames", "id", "identifier", "please", "the", "a", "an",
        "for", "of", "on", "in", "at", "by", "with", "to", "from", "and",
        "or", "get", "fetch", "find", "show", "list", "pull", "give", "me",
        "us", "our", "their", "his", "her", "who", "what", "which", "is",
        "are", "was", "were", "has", "have", "had", "can", "could", "would",
        "should", "need", "needs", "want", "wants", "check", "checking",
        "see", "tell", "if", "do", "does", "did", "paste", "pasted", "below",
        "above", "following", "attached", "csv", "file", "spreadsheet",
        "report", "asset", "assets", "info", "information", "data",
        "details", "detail", "here", "there", "all", "each", "every",
        "please find", "thanks", "thank", "you", "hi", "hello", "hey",
    }
)

# A candidate token: email/username/serial/hostname shaped. Deliberately
# includes '.', '-', '_', '@' so "nina.patel" and "nina.patel@example.com"
# both match as one token.
_TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._%+@\-]*[A-Za-z0-9])?")


def _canonicalize(token: str) -> str:
    """Casefold and drop an email domain, mirroring asset_report_build.py's
    ``normalize_username`` so host-side counts match what the script will
    ultimately dedupe to."""
    return token.strip().casefold().split("@", 1)[0]


def extract_identities(text: str) -> list[str]:
    """Strip instruction stopwords and return unique candidate identities,
    in first-seen order. Does not know about CSV; text-only."""
    seen: dict[str, None] = {}
    for raw_token in _TOKEN_RE.findall(text or ""):
        token = raw_token.strip(".-_")
        if not token:
            continue
        if token.casefold() in STOPWORDS:
            continue
        canonical = _canonicalize(token)
        if not canonical or canonical in STOPWORDS:
            continue
        seen.setdefault(canonical, None)
    return list(seen.keys())


@dataclass(frozen=True)
class BindResult:
    mode: Mode | None
    identities: tuple[str, ...] = field(default_factory=tuple)
    input_count: int = 0
    rejected: bool = False
    rejection_reason: str = ""


def bind_skill(text: str, has_csv: bool) -> BindResult:
    """Deterministic skill bind. Never calls MCP or scripts itself.

    ``has_csv`` short-circuits straight to ``asset_ops`` regardless of any
    pasted text that accompanied the upload (PRD FR-2, SFS §4.2/§6).
    """
    if has_csv:
        # Text accompanying a CSV (if any) is not used for routing; the CSV
        # itself is the identity source, parsed in asset_ops.
        return BindResult(mode="asset_ops", identities=(), input_count=0)

    identities = extract_identities(text)
    if not identities:
        return BindResult(
            mode=None,
            rejected=True,
            rejection_reason="No usernames, serials, or hostnames were found after removing "
            "instruction words. Paste one or more identities or upload a CSV.",
        )
    if len(identities) == 1:
        return BindResult(mode="device_lookup", identities=tuple(identities), input_count=1)
    return BindResult(mode="asset_ops", identities=tuple(identities), input_count=len(identities))


_VULN_KEYWORDS = frozenset({"vuln", "vulnerability", "vulnerabilities", "cve", "exposure", "tenable"})


def is_vuln_phrasing(text: str) -> bool:
    """SAD §2.8 / device-lookup SKILL.md: Tenable is only in play for
    vulnerability-assessment phrasing, and only for a single-identifier
    lookup -- never for the pasted name-list route."""
    lowered = (text or "").casefold()
    return any(keyword in lowered for keyword in _VULN_KEYWORDS)
