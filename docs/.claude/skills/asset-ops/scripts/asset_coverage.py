"""Derive device compliance and per-user coverage from an enriched asset report.

Import-only. Used by asset_report_html.py (step 4); no API calls, no credentials —
every value here is computed from columns steps 1-3 already wrote.

Why this exists: the report is device-grained but the operative question is
user-grained. "Does this person have a working machine?" cannot be answered by
filtering a device list, because one user's devices are judged independently and
scattered across the table. A user with three assets and one Managed+installed
device is fine; their other two rows are noise in a remediation list. These helpers
roll device rows up to a per-user verdict and write it back onto every row, so a
device table can be filtered by it.
"""

import datetime as dt

# Compliance vocabulary. Shared by the app axis, the device verdict, and the
# coverage rollup so a reader never has to translate between three dialects.
COMPLIANT = "compliant"
NON_COMPLIANT = "non-compliant"
UNKNOWN = "unknown"

# MDM is reported as a clean binary. The precise reason (management lapsed vs never
# enrolled) stays in MDM Status and is surfaced as a tooltip — different remediation
# paths, but not a distinction worth six values on a filter axis.
MDM_MANAGED = "managed"
MDM_NOT_MANAGED = "not managed"
MDM_NA = "not applicable"

# Per-user status. Ordered worst-first; this is also the facet display order.
# Plain-language on purpose — this rolls up to people outside CPE who don't use
# "coverage" as a term of art, so the words have to stand on their own.
NOT_COVERED = "Action Needed"
COVERAGE_STALE = "Needs Recheck"
COVERED = "OK (multi device)"
FULLY_COMPLIANT = "OK"
UNMEASURABLE = "Can't Verify"
NO_DEVICE = "No Device"

COVERAGE_ORDER = [NOT_COVERED, COVERAGE_STALE, COVERED, FULLY_COMPLIANT, UNMEASURABLE, NO_DEVICE]
COVERAGE_PILL = {
    NOT_COVERED: "bad", COVERAGE_STALE: "bad", COVERED: "warn",
    FULLY_COMPLIANT: "good", UNMEASURABLE: "none", NO_DEVICE: "none",
}

DERIVED_COLUMNS = ["MDM State", "Device Compliant", "Status",
                   "Coverage Ratio", "Coverage Note"]

# States meaning the asset is on its way back to IT. Excluded from the coverage
# denominator only when the caller opts in, since dropping them changes the counts.
RETURN_STATES = ("term - waiting on return", "repl - waiting on return")


def mdm_state(status):
    """Collapse MDM Status to managed / not managed / not applicable."""
    text = str(status or "").strip()
    if not text or text.startswith("Skipped"):
        return MDM_NA
    return MDM_MANAGED if text == "Managed" else MDM_NOT_MANAGED


def app_verdict(health):
    """Translate the app health axis into compliance vocabulary."""
    return {"healthy": COMPLIANT, "unhealthy": NON_COMPLIANT}.get(
        str(health or "").strip(), UNKNOWN)


def days_since(value, today):
    try:
        return (today - dt.date.fromisoformat(str(value)[:10])).days
    except (ValueError, TypeError):
        return None


def device_verdict(row, apps, mdm_available=True):
    """A device is compliant only if it is managed AND every scored app passes.

    Unmanaged-but-installed is non-compliant on purpose: the app is present, but
    without management we cannot enforce or verify it going forward.

    When step 2 (MDM enrollment) never ran, there is no MDM signal to gate on at
    all — `mdm_available=False` scores purely on the app axis instead of reading
    the always-"not applicable" MDM State as an automatic UNKNOWN, which is the
    step-3-without-step-2 mirror of the step-2-without-step-3 case below.
    """
    verdicts = [app_verdict(row.get(f"{app} Health")) for app in apps]
    if not mdm_available:
        if not verdicts:
            return UNKNOWN
        if NON_COMPLIANT in verdicts:
            return NON_COMPLIANT
        if UNKNOWN in verdicts:
            return UNKNOWN
        return COMPLIANT
    state = mdm_state(row.get("MDM Status"))
    if state == MDM_NA:
        return UNKNOWN
    if state == MDM_NOT_MANAGED or NON_COMPLIANT in verdicts:
        return NON_COMPLIANT
    if not verdicts:
        # MDM-only run (step 2 without step 3): managed is all we can assert.
        return COMPLIANT if state == MDM_MANAGED else NON_COMPLIANT
    if UNKNOWN in verdicts:
        return UNKNOWN
    return COMPLIANT


def add_compliance(df, apps, stale_days=14, ignore_return_states=False, today=None):
    """Add DERIVED_COLUMNS in place and return (df, stats).

    apps: app names to score against. Empty means score on MDM alone.
    """
    today = today or dt.date.today()
    df = df.copy()

    mdm_available = "MDM Status" in df.columns
    df["MDM State"] = df["MDM Status"].map(mdm_state) if mdm_available else MDM_NA
    df["Device Compliant"] = [device_verdict(r, apps, mdm_available) for _, r in df.iterrows()]

    # A device we could not reach is not evidence either way, so it must not sit in
    # the denominator — otherwise an iPad invents a compliance problem for its owner.
    # Without an MDM run there's no "MDM State" signal to gate on, so checkability
    # falls back to "is this a real device row" (a non-blank serial) instead.
    if mdm_available:
        checkable = df["MDM State"] != MDM_NA
    else:
        checkable = df["Serial"].astype(str).str.strip() != ""
    if ignore_return_states and "Substate" in df.columns:
        checkable &= ~df["Substate"].str.strip().str.casefold().isin(RETURN_STATES)
    df["_checkable"] = checkable
    df["_compliant"] = df["Device Compliant"] == COMPLIANT
    df["_age"] = (df["MDM Last Check-In"].map(lambda v: days_since(v, today))
                  if "MDM Last Check-In" in df.columns else None)
    df["_stale"] = df["_age"].map(lambda a: a is not None and a > stale_days)

    coverage, ratio, note, n_ok, n_total = {}, {}, {}, {}, {}
    for username, group in df.groupby("Username", sort=False):
        pool = group[group["_checkable"]]
        good = pool[pool["_compliant"]]
        total, ok = len(pool), len(good)
        ratio[username] = f"{ok}/{total}" if total else "—"
        n_ok[username], n_total[username] = ok, total

        if not total:
            outlier = group["Platform"].isin(("No Device Assigned", "Not Found in SN")).all()
            coverage[username] = NO_DEVICE if outlier else UNMEASURABLE
        elif ok == 0:
            coverage[username] = NOT_COVERED
        elif good["_stale"].all():
            # Compliant on paper, but nothing has checked in recently enough to
            # believe the user is actually on it. Different fix from a failed install.
            coverage[username] = COVERAGE_STALE
        elif ok == total:
            coverage[username] = FULLY_COMPLIANT
        else:
            coverage[username] = COVERED

        fresh = good[~good["_stale"]]
        anchor = (fresh if len(fresh) else good)
        note[username] = str(anchor.iloc[0]["Serial"]) if len(anchor) else ""

    df["Status"] = df["Username"].map(coverage)
    df["Coverage Ratio"] = df["Username"].map(ratio)
    # Numeric halves of the ratio, so exports can carry counts a spreadsheet can
    # sum or pivot instead of a "0/2" string Excel reads as text or a date.
    df["_user_ok"] = df["Username"].map(n_ok).fillna(0).astype(int)
    df["_user_n"] = df["Username"].map(n_total).fillna(0).astype(int)
    # Only meaningful on a failing row: it is the "do not chase this" marker.
    df["Coverage Note"] = [
        f"already has a working device: {note[r['Username']]}"
        if (not r["_compliant"] and r["_checkable"]
            and r["Status"] in (COVERED, FULLY_COMPLIANT) and note[r["Username"]])
        else ""
        for _, r in df.iterrows()
    ]

    users = df.drop_duplicates("Username").set_index("Username")["Status"]
    stats = {
        "users": int(len(users)),
        "coverage": {k: int((users == k).sum()) for k in COVERAGE_ORDER if (users == k).any()},
        "devices_checkable": int(df["_checkable"].sum()),
        "devices_compliant": int((df["_compliant"] & df["_checkable"]).sum()),
        "stragglers": int((~df["_compliant"] & df["_checkable"]
                           & df["Coverage Note"].ne("")).sum()),
        "action_devices": int((~df["_compliant"] & df["_checkable"]
                               & df["Status"].isin([NOT_COVERED, COVERAGE_STALE])).sum()),
        "stale_days": stale_days,
        "ignored_return_states": bool(ignore_return_states),
    }
    return df, stats


def user_rows(df):
    """One record per user for the Users tab, worst coverage first.

    Values are kept atomic — counts as ints, serial lists as lists, the staleness
    figure in its own field — so the HTML and the CSV export can each format them
    without one having to parse the other's presentation.
    """
    apps = _apps(df)
    order = {k: i for i, k in enumerate(COVERAGE_ORDER)}
    out = []
    for username, group in df.groupby("Username", sort=False):
        pool = group[group["_checkable"]]
        bad = pool[~pool["_compliant"]]
        good = pool[pool["_compliant"]]
        coverage = group.iloc[0]["Status"]

        issues = {}
        for _, r in bad.iterrows():
            key = (r["MDM Status"] if "MDM Status" in r and mdm_state(r["MDM Status"]) == MDM_NOT_MANAGED
                   else next((str(r[f"{a} Status"]) for a in apps
                              if app_verdict(r.get(f"{a} Health")) != COMPLIANT), "unknown"))
            issues[key] = issues.get(key, 0) + 1
        issue_list = sorted(issues.items(), key=lambda kv: (-kv[1], kv[0]))

        stale_days = (int(good["_age"].max())
                      if len(good) and good["_age"].notna().any() else None)
        # A stale-coverage user with nothing failing still has a problem: the problem
        # IS the staleness. Leaving this blank would read as "nothing to do".
        if not issue_list and coverage == COVERAGE_STALE and stale_days is not None:
            issue_list = [(f"working device not seen for {stale_days}d", 1)]

        out.append({
            "Priority": order.get(coverage, 9) + 1,
            "Username": username,
            "Status": coverage,
            "Ratio": group.iloc[0]["Coverage Ratio"],
            "Compliant": int(len(good)),
            "Devices": int(len(pool)),
            "Total Assigned": int(len(group[group["Serial"].astype(str).str.strip() != ""])),
            "Platforms": sorted({p for p in group["Platform"] if p}),
            "Issues": issue_list,
            "Needs Work": [str(s) for s in bad["Serial"] if str(s).strip()],
            "Working": [str(s) for s in good["Serial"] if str(s).strip()],
            "Stale Days": stale_days if coverage == COVERAGE_STALE else None,
        })
    out.sort(key=lambda r: (r["Priority"], -r["Devices"], r["Username"]))
    return out


def format_issues(issue_list, sep=" · ", times="×"):
    """Render the issue counts. ASCII `x`/`;` for CSV, `×`/`·` for the page."""
    return sep.join(f"{n}{times} {label}" for label, n in issue_list)


def _apps(df):
    return [c[: -len(" Status")] for c in df.columns
            if c.endswith(" Status") and c != "MDM Status"
            and f"{c[: -len(' Status')]} Health" in df.columns]
