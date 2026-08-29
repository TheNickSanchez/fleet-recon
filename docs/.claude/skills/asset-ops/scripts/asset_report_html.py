#!/usr/bin/env python3
"""Step 4 (optional) — render the asset report as a shareable HTML page.

    .venv/bin/python scripts/asset_report_html.py --source zscaler-recon.csv

No credentials and no API calls: this reads whatever columns are already in
input/output/asset_report.csv and adapts. Facets and table columns are built from
the data, so it works whether the CSV has just the base columns, MDM columns, or
any number of per-app column sets.

Two render paths, chosen by is_bare_mode():
  - Bare mode — only step 1 (asset_report_build.py) has run: no "MDM Status" and no
    "<App> Status" column yet. There's no coverage verdict to compute, so this
    renders a neutral framing instead: plain stat tiles (Users / macOS / Windows /
    Outliers), a Platform breakdown table, and a single flat Devices tab. No
    "Action Needed" language, no verdict box — this is the neutral,
    cross-team-shareable mode. Outliers = No Device Assigned + Not Found in SN +
    Unknown, read off the Platform column asset_report.csv already carries.
  - Coverage-framed mode — once step 2 and/or step 3 has run, this renders the full
    Devices + Users tabs with compliance verdicts, exactly as before. Devices asks
    "is this machine compliant?"; Users asks "does this person have a working
    machine?" — the second cannot be answered by filtering the first, which is what
    asset_coverage exists to fix.

Output is timestamped to the minute, so re-running after a revised pull produces a
new file instead of silently overwriting the previous one.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

import asset_coverage as cov
from fleet_common import DEFAULT_REPORT, OUTLIER_PLATFORMS, slugify

# templates/ lives under the sibling `report` skill, not this skill — resolve from
# this file's own location so it's correct regardless of cwd.
TEMPLATE = Path(__file__).resolve().parent.parent.parent / "report" / "templates" / "asset-ops.html"

# Bare mode's Outliers bucket: a device row that isn't a real, resolvable machine.
BARE_OUTLIER_PLATFORMS = ("No Device Assigned", "Not Found in SN", "Unknown")

PLATFORM_PILL = {"macOS": "macos", "Windows": "windows"}
VERDICT_PILL = {cov.COMPLIANT: "good", cov.NON_COMPLIANT: "bad", cov.UNKNOWN: "warn"}
MDM_PILL = {cov.MDM_MANAGED: "good", cov.MDM_NOT_MANAGED: "bad", cov.MDM_NA: "none"}


def esc(v):
    return html.escape(str(v or ""))


def app_names(df):
    """App column sets present in the CSV, in the order they were added."""
    return [c[: -len(" Status")] for c in df.columns
            if c.endswith(" Status") and c != "MDM Status"
            and f"{c[: -len(' Status')]} Health" in df.columns]


def is_bare_mode(df):
    """True once only step 1 has run: no MDM Status and no '<App> Status' column.

    There is no coverage signal to compute yet, so the Summary tab renders a
    neutral framing instead of a verdict, and Devices is a single flat tab instead
    of Devices + Users.
    """
    return "MDM Status" not in df.columns and not app_names(df)


def facet(key, label, counts):
    items = "".join(
        f'<label><input type="checkbox" data-facet="{key}" value="{esc(slugify(v))}" checked>'
        f'<span class="txt">{esc(v)}</span><span class="n">{n}</span></label>'
        for v, n in counts
    )
    return (f'<div class="facet"><div class="fh"><span>{esc(label)}</span>'
            f'<button data-facet="{key}" type="button">toggle all</button></div>{items}</div>')


def ordered_counts(series, order=None):
    counts = series.value_counts()
    keys = ([k for k in order if k in counts] + [k for k in counts.index if k not in order]
            if order else list(counts.index))
    return [(k, int(counts[k])) for k in keys]


def breakdown_table(title, counts, total, note=""):
    rows = "".join(f"<tr><td>{esc(k)}</td><td class='num'>{n}</td>"
                   f"<td class='num'>{100 * n / total:.1f}%</td></tr>" for k, n in counts)
    tail = f"<p class='small'>{note}</p>" if note else ""
    return (f"<h3>{esc(title)}</h3><table><thead><tr><th>Value</th><th class='num'>Count</th>"
            f"<th class='num'>Share</th></tr></thead><tbody>{rows}</tbody></table>{tail}")


def pill(value, cls):
    return f'<span class="pill {cls}">{esc(value)}</span>'


def device_export(df, apps, has_mdm, ordered):
    """Explicit CSV schema for the Devices tab.

    Built from the dataframe, never from the rendered cells: a table cell may carry a
    pill plus a sub-note, and scraping textContent glues them into one unusable value
    ("non-compliantuser covered by X"). Everything here is atomic and Excel-safe —
    counts are integers, no ratio strings that spreadsheets read as dates.
    """
    rows = []
    for _, r in ordered.iterrows():
        row = {"Serial": r["Serial"], "Username": r["Username"], "Platform": r["Platform"],
               "Model": r["Model"], "State": r["State"], "Substate": r["Substate"]}
        if has_mdm:
            row["MDM"] = r["MDM State"]
            row["MDM Reason"] = r["MDM Status"]          # the tooltip, kept as a real field
            row["Device Compliant"] = r["Device Compliant"]
            row["Last Check-In"] = r["MDM Last Check-In"]
            row["Check-In Age (Days)"] = "" if pd.isna(r["_age"]) or r["_age"] is None else int(r["_age"])
        for app in apps:
            row[f"{app} Status"] = r[f"{app} Status"]
            row[f"{app} Compliant"] = cov.app_verdict(r[f"{app} Health"])
            if f"{app} Source" in df.columns:
                row[f"{app} Source"] = r[f"{app} Source"]
        row["User Status"] = r["Status"]
        row["User Compliant Devices"] = int(r["_user_ok"])
        row["User Checkable Devices"] = int(r["_user_n"])
        # Split out of the display note so it is a usable serial, not a sentence.
        row["Other Working Device Serial"] = (
            r["Coverage Note"].replace("already has a working device: ", "") if r["Coverage Note"] else "")
        row["Notes"] = r["Notes"]
        rows.append(row)
    return rows


def user_export(records):
    """Explicit CSV schema for the Users tab, one atomic value per column."""
    rows = []
    for r in records:
        rows.append({
            "Priority": r["Priority"],
            "User": r["Username"],
            "Status": r["Status"],
            "Compliant Devices": r["Compliant"],
            "Checkable Devices": r["Devices"],
            "Assigned Devices": r["Total Assigned"],
            "Working Device Age (Days)": "" if r["Stale Days"] is None else r["Stale Days"],
            "Platforms": "; ".join(r["Platforms"]),
            # ASCII separators: Excel on Windows mangles bare UTF-8, and the export
            # already ships a BOM, but there is no reason to spend it on a middot.
            "Blocking Issue": cov.format_issues(r["Issues"], sep="; ", times="x"),
            "Serials Needing Work": "; ".join(r["Needs Work"]),
            "Working Serials": "; ".join(r["Working"]),
        })
    return rows


def device_table(df, apps, has_mdm):
    cols = [("Serial", "Serial"), ("Username", "Username"), ("Platform", "Platform"),
            ("Model", "Model"), ("State", "State"), ("Substate", "Substate")]
    if has_mdm:
        cols += [("MDM State", "MDM"), ("Device Compliant", "Compliant")]
    for app in apps:
        cols.append((f"{app} Status", app))
    cols.append(("Coverage Ratio", "Status"))
    cols = [(c, l) for c, l in cols if c in df.columns]

    head = "".join(f'<th class="sortable" data-col="{i}">{esc(l)}</th>'
                   for i, (_, l) in enumerate(cols))

    rank = {cov.NON_COMPLIANT: 0, cov.UNKNOWN: 1, cov.COMPLIANT: 2}
    order = {k: i for i, k in enumerate(cov.COVERAGE_ORDER)}
    ordered = df.sort_values(
        by=["Status", "Device Compliant", "Platform", "Username"],
        key=lambda c: (c.map(order) if c.name == "Status"
                       else c.map(rank) if c.name == "Device Compliant" else c))

    rows = []
    for i, (_, r) in enumerate(ordered.iterrows()):
        # data-i ties the row to its export record, so filtering the table filters the
        # export without the export having to read the table.
        attrs = [f'data-i="{i}"',
                 f'data-platform="{esc(slugify(r["Platform"]))}"',
                 f'data-status="{esc(slugify(r["Status"]))}"']
        if has_mdm:
            attrs.append(f'data-mdm="{esc(slugify(r["MDM State"]))}"')
            attrs.append(f'data-compliant="{esc(slugify(r["Device Compliant"]))}"')
        for app in apps:
            attrs.append(f'data-{slugify(app)}="{esc(slugify(cov.app_verdict(r[f"{app} Health"])))}"')

        cls = []
        if r["Status"] in (cov.NOT_COVERED, cov.COVERAGE_STALE):
            cls.append("uncovered")
        if r["Coverage Note"]:
            cls.append("straggler")
        if cls:
            attrs.append(f'class="{" ".join(cls)}"')

        cells = []
        for col, _ in cols:
            v = str(r[col]).strip()
            if col == "Serial":
                cells.append(f"<td><code>{esc(v) or '—'}</code></td>")
            elif col == "Platform":
                cells.append(f"<td>{pill(v, PLATFORM_PILL.get(v, 'other'))}</td>")
            elif col == "MDM State":
                # Binary axis; the precise reason stays available on hover.
                cells.append(f'<td><span class="pill {MDM_PILL.get(v, "none")}" '
                             f'title="{esc(r["MDM Status"])}">{esc(v)}</span></td>')
            elif col == "Device Compliant":
                note = (f'<span class="cnote">{esc(r["Coverage Note"])}</span>'
                        if r["Coverage Note"] else "")
                cells.append(f"<td>{pill(v, VERDICT_PILL.get(v, 'none'))}{note}</td>")
            elif col.endswith(" Status"):
                app = col[: -len(" Status")]
                verdict = cov.app_verdict(r[f"{app} Health"])
                cells.append(f"<td>{pill(v, VERDICT_PILL.get(verdict, 'none'))}</td>")
            elif col == "Coverage Ratio":
                cells.append(f'<td><span class="ratio">{esc(v)}</span> '
                             f'{pill(r["Status"], cov.COVERAGE_PILL.get(r["Status"], "none"))}</td>')
            else:
                cells.append(f"<td>{esc(v) or '—'}</td>")
        rows.append(f'<tr {" ".join(attrs)}>{"".join(cells)}</tr>')
    return head, "\n".join(rows), ordered


def bare_platform_pill_class(platform):
    """macOS/Windows keep their own colors; the Outliers bucket reuses the amber
    'warn' pill; everything else (iPad, Android, ChromeOS, Virtual Desktop) falls
    back to the neutral 'other' pill."""
    if platform in PLATFORM_PILL:
        return PLATFORM_PILL[platform]
    if platform in BARE_OUTLIER_PLATFORMS:
        return "warn"
    return "other"


def bare_device_table(df):
    """The single flat Devices tab for bare mode — no compliance verdict, no
    coverage ratio, just the device row as asset_report_build.py wrote it."""
    cols = [(c, c) for c in
            ("Serial", "Username", "Platform", "Model", "State", "Substate", "Notes")
            if c in df.columns]
    head = "".join(f'<th class="sortable" data-col="{i}">{esc(l)}</th>'
                   for i, (_, l) in enumerate(cols))

    ordered = df.sort_values(by=["Platform", "Username"])

    rows = []
    for i, (_, r) in enumerate(ordered.iterrows()):
        attrs = [f'data-i="{i}"', f'data-platform="{esc(slugify(r["Platform"]))}"']
        cells = []
        for col, _ in cols:
            v = str(r[col]).strip()
            if col == "Serial":
                cells.append(f"<td><code>{esc(v) or '—'}</code></td>")
            elif col == "Platform":
                cells.append(f"<td>{pill(v, bare_platform_pill_class(v))}</td>")
            else:
                cells.append(f"<td>{esc(v) or '—'}</td>")
        rows.append(f'<tr {" ".join(attrs)}>{"".join(cells)}</tr>')
    return head, "\n".join(rows), ordered


def bare_device_export(ordered):
    """Explicit CSV schema for bare mode's Devices tab, same atomic-values rule as
    device_export() — built from the dataframe, never scraped from the table."""
    cols = [c for c in ("Serial", "Username", "Platform", "Model", "State", "Substate", "Notes")
            if c in ordered.columns]
    return [{c: r[c] for c in cols} for _, r in ordered.iterrows()]


def users_table(records):
    labels = ["User", "Status", "Compliant", "Checkable", "Assigned",
              "Platforms", "Blocking issue", "Serials needing work"]
    head = "".join(f'<th class="sortable" data-col="{i}">{esc(l)}</th>'
                   for i, l in enumerate(labels))
    rows = []
    for i, r in enumerate(records):
        uncovered = r["Status"] in (cov.NOT_COVERED, cov.COVERAGE_STALE)
        stale = (f'<span class="cnote">working device last seen {r["Stale Days"]}d ago</span>'
                 if r["Stale Days"] is not None else "")
        rows.append(
            f'<tr data-i="{i}" data-status="{esc(slugify(r["Status"]))}" '
            f'data-platform="{esc(slugify(r["Platforms"][0] if r["Platforms"] else ""))}" '
            f'data-needs="{esc(" ".join(r["Needs Work"]))}"'
            f'{" class=uncovered" if uncovered else ""}>'
            f'<td>{esc(r["Username"])}</td>'
            f'<td>{pill(r["Status"], cov.COVERAGE_PILL.get(r["Status"], "none"))}{stale}</td>'
            f'<td><span class="ratio">{esc(r["Ratio"])}</span></td>'
            f'<td class="num">{r["Devices"]}</td>'
            f'<td class="num">{r["Total Assigned"]}</td>'
            f'<td>{esc(", ".join(r["Platforms"])) or "—"}</td>'
            f'<td>{esc(cov.format_issues(r["Issues"])) or "—"}</td>'
            f'<td class="serials">{esc(" ".join(r["Needs Work"])) or "—"}</td></tr>')
    return head, "\n".join(rows)


def build(df, apps, stats, source, out_path, data_as_of, generated, user_export_name):
    has_mdm = "MDM Status" in df.columns
    devices = df[~df["Platform"].isin(OUTLIER_PLATFORMS)]
    users = stats["users"]
    c = stats["coverage"]

    # Rows step 1.5 filled in from an MDM reverse-lookup carry a one-line note
    # rather than a parallel column set — a filled row is just a device row now.
    gap_filled = int(df["Notes"].str.contains("not in ServiceNow", regex=False).sum()) if "Notes" in df.columns else 0

    covered = c.get(cov.FULLY_COMPLIANT, 0) + c.get(cov.COVERED, 0)
    action = c.get(cov.NOT_COVERED, 0) + c.get(cov.COVERAGE_STALE, 0)
    tiles = [
        f'<div class="s"><b class="red">{action}</b><span>Users need action</span></div>',
        f'<div class="s"><b class="green">{covered}</b><span>Users covered</span></div>',
        f'<div class="s"><b class="yellow">{stats["stragglers"]}</b><span>Straggler devices</span></div>',
        f'<div class="s"><b>{users}</b><span>Users</span></div>',
        f'<div class="s"><b>{len(devices)}</b><span>Devices</span></div>',
    ]
    if gap_filled:
        tiles.append(f'<div class="s"><b class="red">{gap_filled}</b><span>Filled from Jamf/Intune, not ServiceNow</span></div>')

    label = apps[0] if apps else "MDM"
    verdict = [
        f'<strong>{action} of {users} users need action</strong> — they have no device that is '
        f'both managed and {"running " + esc(label) if apps else "managed"}. '
        f"{covered} already have at least one working device. ",
        f'Of the {stats["devices_checkable"] - stats["devices_compliant"]} non-compliant devices, '
        f'<strong>{stats["stragglers"]} belong to a user who already has a working one</strong> — '
        f"asset cleanup rather than a remediation ticket — leaving "
        f'{stats["action_devices"]} that actually block someone. ',
        f"Ratios count checkable devices only; iPads, virtual desktops and placeholder serials "
        f"have no agent to query. A user whose only working device has not checked in for over "
        f'{stats["stale_days"]} days is marked <em>Needs Recheck</em>, not <em>OK</em>.',
    ]
    if stats["ignored_return_states"]:
        verdict.append(" Devices awaiting return are excluded from the ratios (<code>--ignore-return-states</code>).")
    if gap_filled:
        verdict.append(
            f' <strong>{gap_filled} device row(s) came from a Jamf/Intune lookup, not ServiceNow</strong> — '
            f'ServiceNow had "No Device Assigned" for these users even though they have an active device; '
            f"that's a ServiceNow record gap to escalate for asset-record cleanup, not a hardware issue.")

    breakdowns = [
        breakdown_table("Status",
                        [(k, v) for k, v in c.items()], users),
        breakdown_table("Operating system", ordered_counts(df["Platform"]), len(df)),
    ]
    if has_mdm:
        breakdowns.append(breakdown_table(
            "MDM", ordered_counts(df["MDM State"], [cov.MDM_MANAGED, cov.MDM_NOT_MANAGED, cov.MDM_NA]), len(df),
            "Reported as a binary. The underlying reason — management lapsed vs never enrolled vs "
            "nothing to enrol — is on the device row as a tooltip and in the breakdown below, "
            "because they are different fixes."))
        breakdowns.append(breakdown_table("MDM — underlying reason",
                                          ordered_counts(df["MDM Status"]), len(df)))
    for app in apps:
        breakdowns.append(breakdown_table(f"{app} — reported status",
                                          ordered_counts(df[f"{app} Status"]), len(df)))

    if apps and has_mdm:
        breakdowns.insert(0, (
            '<div class="note">macOS and Windows values come from different sources and are not '
            'directly comparable: macOS reports a Jamf extension attribute (diagnostic detail kept '
            'verbatim), Windows reports the Intune Managed Apps install state (installed or not). '
            'The <em>Compliant</em> column normalises both, and requires the device to be managed '
            'as well — so an unmanaged machine with the app installed is still non-compliant, '
            'because nothing can be enforced or verified on it.</div>'))

    # ---- facets
    dev_facets = [facet("status", "Status",
                        ordered_counts(df["Status"], cov.COVERAGE_ORDER)),
                  facet("platform", "Operating system", ordered_counts(df["Platform"]))]
    if has_mdm:
        dev_facets.append(facet("compliant", "Device compliance",
                                ordered_counts(df["Device Compliant"],
                                               [cov.NON_COMPLIANT, cov.UNKNOWN, cov.COMPLIANT])))
        dev_facets.append(facet("mdm", "MDM",
                                ordered_counts(df["MDM State"],
                                               [cov.MDM_NOT_MANAGED, cov.MDM_NA, cov.MDM_MANAGED])))
    for app in apps:
        dev_facets.append(facet(slugify(app), f"{app}",
                                ordered_counts(df[f"{app} Health"].map(cov.app_verdict),
                                               [cov.NON_COMPLIANT, cov.UNKNOWN, cov.COMPLIANT])))

    per_user = df.drop_duplicates("Username")
    user_facets = [facet("status", "Status",
                         ordered_counts(per_user["Status"], cov.COVERAGE_ORDER))]

    dev_head, dev_rows, dev_ordered = device_table(df, apps, has_mdm)
    records = cov.user_rows(df)
    usr_head, usr_rows = users_table(records)

    # Export payloads travel as JSON, not as scraped table text.
    dev_csv = device_export(df, apps, has_mdm, dev_ordered)
    usr_csv = user_export(records)
    payload = (
        f'<script id="export-device-table" type="application/json">'
        f"{json.dumps(dev_csv, ensure_ascii=False)}</script>"
        f'<script id="export-user-table" type="application/json">'
        f"{json.dumps(usr_csv, ensure_ascii=False)}</script>"
    )

    title = f"{apps[0]} Compliance" if apps else ("MDM Compliance" if has_mdm else "Asset Report")

    nav_tabs = ('<button data-tab="summary" class="active">Summary</button>'
                '<button data-tab="users">Users</button>'
                '<button data-tab="devices">Devices</button>')

    users_section = f'''<section id="users">
  <h2>Users</h2>
  <p class="small">One row per person, not per device. <strong>Status</strong> answers
  &ldquo;does this user have at least one device that is managed and installed?&rdquo; — so a
  user with three assets and one working machine reads <em>OK (multi device)</em>, and their
  other rows stop competing for attention with someone who has nothing. The ratio counts only
  devices we can actually check; iPads, virtual desktops and placeholder serials have no agent
  to query and are excluded rather than counted as failures.</p>
  <div class="facets" data-facets-for="user-table">{"".join(user_facets)}</div>
  <div class="toolbar">
    <input class="search" data-search-for="user-table" type="text" placeholder="Search username, platform, or issue..."/>
    <button class="btn ghost" data-reset-for="user-table">Reset filters</button>
  </div>
  <div class="rowcount" data-count-for="user-table"></div>
  <div class="tbl-wrap">
    <table id="user-table" data-export="{user_export_name}">
      <thead><tr>{usr_head}</tr></thead>
      <tbody>
{usr_rows}
      </tbody>
    </table>
  </div>
  <button class="btn" data-copy-for="user-table" data-copy-col="0">Copy usernames</button>
  <button class="btn" data-copy-for="user-table" data-copy-attr="needs">Copy serials needing work</button>
  <button class="btn ghost" data-export-for="user-table">Export CSV</button>
</section>'''

    devices_section = f'''<section id="devices">
  <h2>Devices</h2>
  <div class="facets" data-facets-for="device-table">{"".join(dev_facets)}</div>
  <div class="toolbar">
    <input class="search" data-search-for="device-table" type="text" placeholder="Search serial, username, model, or status..."/>
    <button class="btn ghost" data-reset-for="device-table">Reset filters</button>
  </div>
  <div class="rowcount" data-count-for="device-table"></div>

  <div class="tbl-wrap">
    <table id="device-table" data-export="{os.path.basename(out_path).replace(".html", "-devices.csv")}">
      <thead><tr>{dev_head}</tr></thead>
      <tbody>
{dev_rows}
      </tbody>
    </table>
  </div>

  <button class="btn" data-copy-for="device-table" data-copy-col="0">Copy serials</button>
  <button class="btn" data-copy-for="device-table" data-copy-col="1">Copy usernames</button>
  <button class="btn ghost" data-export-for="device-table">Export CSV</button>
</section>'''

    with open(TEMPLATE) as fh:
        page = fh.read()
    for key, value in {
        "{{TITLE}}": esc(title),
        "{{SOURCE}}": esc(source),
        "{{GENERATED}}": esc(generated),
        "{{DATA_AS_OF}}": esc(data_as_of),
        "{{USER_COUNT}}": str(users),
        "{{DEVICE_COUNT}}": str(len(devices)),
        "{{NAV_TABS}}": nav_tabs,
        "{{STAT_TILES}}": "".join(tiles),
        "{{VERDICT_BLOCK}}": f'<div class="verdict">{"".join(verdict)}</div>',
        "{{BREAKDOWNS}}": "".join(breakdowns),
        "{{USERS_SECTION}}": users_section,
        "{{DEVICES_SECTION}}": devices_section,
        "{{EXPORT_PAYLOAD}}": payload,
    }.items():
        page = page.replace(key, value)

    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if left:
        print(f"[-] Unfilled placeholders: {sorted(set(left))}")
        sys.exit(1)
    return page


def build_bare(df, source, out_path, data_as_of, generated):
    """Bare mode's Summary + single Devices tab — no coverage verdict, no Users
    tab. Neutral framing (stat tiles + platform breakdown, no 'Action Needed'
    language), reusing this template's own generic facet/search/sort/copy/export
    table JS so there is one table engine for the whole pipeline.
    """
    total_users = int(df["Username"].nunique())
    total_devices = len(df)
    macos = int((df["Platform"] == "macOS").sum())
    windows = int((df["Platform"] == "Windows").sum())
    outliers = int(df["Platform"].isin(BARE_OUTLIER_PLATFORMS).sum())

    tiles = (
        f'<div class="s"><b>{total_users}</b><span>Users</span></div>'
        f'<div class="s"><b>{macos}</b><span>macOS</span></div>'
        f'<div class="s"><b>{windows}</b><span>Windows</span></div>'
        f'<div class="s"><b>{outliers}</b><span>Outliers</span></div>'
    )
    breakdowns = breakdown_table("Platform breakdown", ordered_counts(df["Platform"]), total_devices)

    dev_facets = [facet("platform", "Platform", ordered_counts(df["Platform"]))]
    dev_head, dev_rows, dev_ordered = bare_device_table(df)
    dev_csv = bare_device_export(dev_ordered)
    payload = (
        f'<script id="export-device-table" type="application/json">'
        f"{json.dumps(dev_csv, ensure_ascii=False)}</script>"
    )

    nav_tabs = ('<button data-tab="summary" class="active">Summary</button>'
                '<button data-tab="devices">Devices</button>')

    devices_section = f'''<section id="devices">
  <h2>Devices</h2>
  <div class="facets" data-facets-for="device-table">{"".join(dev_facets)}</div>
  <div class="toolbar">
    <input class="search" data-search-for="device-table" type="text" placeholder="Search serial, username, or model..."/>
    <button class="btn ghost" data-reset-for="device-table">Reset filters</button>
  </div>
  <div class="rowcount" data-count-for="device-table"></div>

  <div class="tbl-wrap">
    <table id="device-table" data-export="{os.path.basename(out_path).replace(".html", "-devices.csv")}">
      <thead><tr>{dev_head}</tr></thead>
      <tbody>
{dev_rows}
      </tbody>
    </table>
  </div>

  <button class="btn" data-copy-for="device-table" data-copy-col="0">Copy serials</button>
  <button class="btn" data-copy-for="device-table" data-copy-col="1">Copy usernames</button>
  <button class="btn ghost" data-export-for="device-table">Export CSV</button>
</section>'''

    with open(TEMPLATE) as fh:
        page = fh.read()
    for key, value in {
        "{{TITLE}}": esc("Asset Report"),
        "{{SOURCE}}": esc(source),
        "{{GENERATED}}": esc(generated),
        "{{DATA_AS_OF}}": esc(data_as_of),
        "{{USER_COUNT}}": str(total_users),
        "{{DEVICE_COUNT}}": str(total_devices),
        "{{NAV_TABS}}": nav_tabs,
        "{{STAT_TILES}}": tiles,
        "{{VERDICT_BLOCK}}": "",
        "{{BREAKDOWNS}}": breakdowns,
        "{{USERS_SECTION}}": "",
        "{{DEVICES_SECTION}}": devices_section,
        "{{EXPORT_PAYLOAD}}": payload,
    }.items():
        page = page.replace(key, value)

    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if left:
        print(f"[-] Unfilled placeholders: {sorted(set(left))}")
        sys.exit(1)
    return page


def main():
    parser = argparse.ArgumentParser(description="Render the asset report as HTML.")
    parser.add_argument("--location", default=DEFAULT_REPORT, help=f"Report CSV (default: {DEFAULT_REPORT}).")
    parser.add_argument("--source", default="", help="Input list name shown in the header.")
    parser.add_argument("--output", default="", help="Override the output path.")
    parser.add_argument("--stale-days", type=int, default=14,
                        help="A user whose only compliant device is older than this reads "
                             "'Needs Recheck', not 'OK' (default: 14).")
    parser.add_argument("--compliance-app", default="",
                        help="Score compliance against this app only. Default: every app "
                             "column in the CSV must pass.")
    parser.add_argument("--ignore-return-states", action="store_true",
                        help="Exclude 'Waiting on Return' assets from the coverage ratios. "
                             "Off by default so nothing is hidden silently.")
    args = parser.parse_args()

    if not os.path.exists(args.location):
        print(f"[-] Report not found: {args.location}\n    Run scripts/asset_report_build.py first.")
        sys.exit(1)

    df = pd.read_csv(args.location, dtype=str).fillna("")

    now = dt.datetime.now()
    generated = now.strftime("%Y-%m-%d %H:%M")
    data_as_of = dt.datetime.fromtimestamp(os.path.getmtime(args.location)).strftime("%Y-%m-%d %H:%M")
    source = args.source or os.path.basename(args.location)
    stem = slugify(os.path.splitext(source)[0]).replace("_", "-") or "asset-report"
    out = args.output or f"reports/{stem}-{now.strftime('%Y-%m-%d-%H%M')}.html"

    if is_bare_mode(df):
        # Only step 1 has run — no MDM/App Status column to score compliance on.
        # Render the neutral device-audit framing instead of a coverage verdict.
        if args.compliance_app:
            print(f"[-] --compliance-app {args.compliance_app!r} has nothing to score against — "
                  "no MDM/App Status columns yet. Run step 2 and/or step 3 first.")
            sys.exit(1)
        page = build_bare(df, source, out, data_as_of, generated)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w") as fh:
            fh.write(page)
        print(f"[+] {out}")
        print(f"    {df['Username'].nunique()} users · {len(df)} device rows · bare mode (Step 1 only)")
        print(f"    generated {generated} · data pulled {data_as_of}")
        return

    apps = app_names(df)
    scored = apps
    if args.compliance_app:
        match = [a for a in apps if a.casefold() == args.compliance_app.casefold()]
        if not match:
            print(f"[-] --compliance-app {args.compliance_app!r} not in the report. Found: {apps or 'none'}")
            sys.exit(1)
        scored = match

    df, stats = cov.add_compliance(df, scored, stale_days=args.stale_days,
                                   ignore_return_states=args.ignore_return_states,
                                   today=now.date())

    page = build(df, apps, stats, source, out, data_as_of, generated,
                 os.path.basename(out).replace(".html", "-users.csv"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as fh:
        fh.write(page)

    c = stats["coverage"]
    print(f"[+] {out}")
    print(f"    {stats['users']} users · {len(df)} device rows · "
          f"scored on: {', '.join(scored) or 'MDM only'}")
    print(f"    coverage: " + " · ".join(f"{k} {v}" for k, v in c.items()))
    print(f"    {stats['action_devices']} devices block someone · "
          f"{stats['stragglers']} stragglers (owner already covered)")
    print(f"    generated {generated} · data pulled {data_as_of}")


if __name__ == "__main__":
    main()
