---
name: asset-ops
description: "Build a device-grained asset CSV from a user list (one row per device), then optionally enrich it in place with MDM enrollment status and per-app install/health columns, sync macOS devices into a Jamf static group, and render a shareable HTML report — neutral stat tiles when only the base CSV exists, coverage-verdict framing once MDM/app data has been added. Each step independent and platform-aware (macOS→Jamf, Windows→Intune). Use when the user says \"get asset data from <file>.csv\", \"include device mdm status\", \"tell me if <app> is installed\", \"add <file> to Jamf group <id>\", or \"sync users to Jamf group\"."
argument-hint: "input CSV; optionally an app name for step 3, or a Jamf group ID for the sync step"
user-invocable: true
---

# Asset Ops

Independent capabilities over one CSV that grows rightward: `input/output/asset_report.csv`.

1. `get asset data from <file>.csv` → user / serial / platform / state / substate,
   **one row per device**. `--platforms "macOS,Windows"` drops iPad/Android/ChromeOS/VDI
   rows entirely when the user wants a computer-only list (e.g. an app-install check).
1.5. optional, agent-driven — reverse-check "No Device Assigned" rows against Jamf/Intune
   directly and fill `Serial`/`Platform`/`Model` in place when a real device is found.
   **Must run before step 3** if used, since app discovery skips rows with no serial.
2. `include device mdm status` → MDM columns (macOS→Jamf, Windows→Intune)
3. `tell me if <app> is installed` → `<App> Status` / `Health` / `Source`
- `add [file] to group [ID]` / `sync users to Jamf group` → sync macOS serials from
  `asset_report.csv` into a Jamf static computer group. Independent of the numbered chain —
  needs only step 1's CSV, not steps 1.5–4.
4. optional — render `reports/<source>-YYYY-MM-DD-HHMM.html` (no creds, no API calls):
   neutral stat tiles if only step 1 has run, coverage-verdict framing once MDM/app columns
   exist.

Run **only** the capability the user asked for. Steps are additive and idempotent;
re-running one overwrites its own columns.

---

## Full Playbook

# Asset Ops

## Overview

Turns a flat list of usernames into a **device-grained CSV that grows rightward**, one
independently-invocable step at a time, plus one independent write capability (Jamf group
sync) that branches off the same CSV. Step 1 resolves ServiceNow hardware (one row per
device, not per user). Step 1.5 (optional) fills "No Device Assigned" rows from a direct
Jamf/Intune reverse-lookup, since a blank ServiceNow record isn't proof the user has no
device. Step 2 adds MDM enrollment, dispatching per platform. Step 3 adds per-app
install/health columns, also per platform. Each step reads the same CSV, adds its own
columns (or, for step 1.5, fills existing ones), backs up the previous version, and prints
a compact summary — the agent reads the summary, never the CSV body. Jamf group sync reads
the same CSV but only ever needs step 1's output — it's a consumer of the pipeline, not
another rightward-growing step.

**Load this skill when:**
- The user asks to "get asset data from `<file>.csv`" or "grab asset data from `<file>.csv`" → **step 1 only**
- The user then says "check for ServiceNow gaps" / "cross-reference Intune and Jamf" for users
  showing "No Device Assigned" → **step 1.5 only**
- The user then says "and get device mdm status" / "include device mdm status" → **step 2 only**
- The user then says "tell me if zscaler is installed" / "include zscaler install status" /
  "is slack installed" → **step 3 only**, one run per app
- The user says "add [file] to group [ID]", "sync users to Jamf group", "populate group
  from this list", or names a CSV + a group ID together → **Jamf group sync only** (needs
  step 1's `asset_report.csv`; does not require steps 1.5–4). Do not render the HTML report
  unless they also ask for it.
- The user asks for both an enrichment check and a group sync in the same request (e.g.
  "give me MDM status AND add macOS to group X") → run step 1 once, then both branches.
- Any request needing per-device rows for a mixed macOS/Windows population

Steps are independent and additive. Run **only** the step asked for — do not pre-emptively
run step 2 or 3 because they seem useful. Re-running a step overwrites its own columns.

**Do NOT use for:**
- Smart group rule changes or policy scoping edits that don't start from a flat user list
  (the group sync below only ever adds/replaces static-group membership from a CSV).
- Any write action beyond the Jamf group sync below — every enrichment step (1–4) here is
  read-only.

---

## Prerequisites

- **MCP servers needed:** none for steps 1–4 or the Jamf group sync — those scripts use
  passkey-injected creds. **Step 1.5 is the exception** — it needs live `jamf`/`intune` MCP
  tool access (`jamf_get_user_devices`, `intune_lookup_users`) since a plain script can't
  call MCP tools. Otherwise use MCP only to spot-verify a few rows afterwards.
- **Scripts:** `${CLAUDE_SKILL_DIR}/scripts/asset_report_build.py` (1), `${CLAUDE_SKILL_DIR}/scripts/asset_report_snow_gap.py` (1.5),
  `${CLAUDE_SKILL_DIR}/scripts/asset_report_mdm.py` (2), `${CLAUDE_SKILL_DIR}/scripts/asset_report_app.py` (3),
  `${CLAUDE_SKILL_DIR}/scripts/intune_app_lookup.py` (3, Windows-only Managed Apps variant),
  `${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py` (Jamf group sync — needs only step 1's
  CSV), `${CLAUDE_SKILL_DIR}/scripts/asset_coverage.py` (import-only, used by step 4),
  `${CLAUDE_SKILL_DIR}/scripts/asset_report_html.py` (4),
  `${CLAUDE_SKILL_DIR}/scripts/fleet_common.py` (shared, import-only), `${CLAUDE_SKILL_DIR}/scripts/app_signal_map.yaml` (optional
  overrides), `${CLAUDE_SKILL_DIR}/../report/templates/asset-ops.html` (step 4's template)
- **Input:** CSV in `input/` with a username or email column — see **Input File Variants**
  below. Domains are stripped automatically; do not pre-strip.
- **Output:** `input/output/asset_report.csv`, plus a `.bak-YYYYmmdd-HHMMSS.csv` per rewrite.
  The Jamf group sync reads this same file — there is only one artifact in this pipeline.
- **Access required:** `servicenow` for step 1; live `jamf`/`intune` MCP tools for step 1.5;
  `jamf_api` and/or `intune` passkey profiles for steps 2–3 (only the platforms actually
  present in the CSV are required); `jamf_api` for the Jamf group sync.

### Input File Variants

| Column header | Action |
|---|---|
| `Usernames` | Works as-is |
| `Username` (singular) | Works as-is |
| `Email` | Works as-is — domain stripped automatically |
| `User Email` | Works as-is — domain stripped automatically |
| Full emails in any column | Domain stripped automatically; do NOT pre-strip |
| Bare list, no header | Add one of the above header lines first |

Every script here normalizes inputs to bare usernames before querying ServiceNow, so both
`abigail.giannou` and `abigail.giannou@docusign.com` produce the same result.

**Quick header fix if needed:**
```zsh
sed -i '' '1s/.*/Usernames/' input/<input_file.csv>
```

---

## Standard Execution

### Step 1 — build the device-grained report

```zsh
cd ~/work
passkey run servicenow -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_build.py" \
  --location "input/<input_file.csv>"
```

Every input username lands somewhere: a user with three assets yields three rows
(`Notes = device 2 of 3`), a user with none yields one row (`Platform = No Device Assigned`),
a user ServiceNow doesn't know yields `Not Found in SN`. Nothing is silently dropped.

Columns: `Username`, `Serial`, `Platform`, `State`, `Substate`, `Model`, `Asset Tag`, `Notes`.

`Platform` is one of `macOS`, `Windows`, `iOS/iPadOS`, `Android`, `ChromeOS`,
`Virtual Desktop`, `Unknown`, `No Device Assigned`, `Not Found in SN`. Only macOS and Windows
have an MDM to dispatch to; the rest are named explicitly so a skip in steps 2–3 is never
mistaken for an enrollment gap. Platform comes from ServiceNow model/manufacturer — **never**
from serial-number prefixes, which `get_fleet_encryption_status.py` does and misclassifies
anything outside its prefix list.

**All asset states are included by default** (the old `install_status=1` filter is gone).
Narrow it when the user wants only live kit:

```zsh
passkey run servicenow -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_build.py" \
  --location "input/<file>.csv" --states "In use,In stock"
```

Narrow to computer platforms only (drops iPads/Android/ChromeOS/Virtual Desktop/Unknown
device rows entirely, rather than listing them and letting steps 2–3 report them as
`Skipped`). Use this whenever the user asks for a Windows/Mac-only device list, e.g. an
app-install check:

```zsh
passkey run servicenow -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_build.py" \
  --location "input/<file>.csv" --platforms "macOS,Windows"
```

A user whose only hardware is out-of-scope (iPad-only, VM-only) is excluded entirely and
counted in the `[!] N user(s) have hardware but none in {...}` line — **not** shown as `No
Device Assigned`, which would misreport "has no device" as "has a device we don't want."

### Sync macOS devices to a Jamf group (independent of steps 1.5–4)

Triggered by "add [file] to group [ID]", "sync users to Jamf group", "populate group from
this list", or a CSV + group ID named together. Needs only step 1's `asset_report.csv` —
run step 1 first if it doesn't exist yet, but nothing past it.

```zsh
cd ~/work
passkey run jamf_api -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py" \
  --group-id <GROUP_ID>
```

`--location` defaults to `input/output/asset_report.csv`. Override only if needed. Reads
the `Serial`/`Platform` columns, filters to `Platform == "macOS"`, and dedupes by `Serial`
— unlike the old joined-column hardware report this superseded, `asset_report.csv` is
already one row per device, so there's no `;`-joined multi-serial string to split.

Default mode is additive (safe): existing static group members are preserved and new
enrolled serials are added.

Optional modes:
```zsh
# additive (default)
passkey run jamf_api -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py" \
  --group-id <GROUP_ID> --mode additive

# replace (dangerous, full overwrite)
passkey run jamf_api -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py" \
  --group-id <GROUP_ID> --mode replace
```

Use `--dry-run` to validate without pushing to Jamf:
```zsh
passkey run jamf_api -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py" \
  --group-id <GROUP_ID> --dry-run
```

For benchmark-quality telemetry, append one JSON summary per run:
```zsh
passkey run jamf_api -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/jamf_group_sync.py" \
  --group-id <GROUP_ID> --summary-json /tmp/jamf_sync_runs.jsonl
```

**Expected output:**
```
[*] Inventory validation batch 1/N...
...
[+] N serials confirmed enrolled in Jamf.
[!] X serials not found in Jamf (skipping): ...   ← retired/SN-only
[*] Preflight: mode=additive existing=E enrolled=N planned_add=A target=T
[*] Pushing target set of T devices to Jamf Static Group ID: XXXX...
[*] Chunk 1/M: pushing 75 devices (attempt 1)...
[*] Chunk 2/M: pushing 150 devices (attempt 1)...
...
[+] Success! Added T-U macOS devices to Group XXXX.
[!] Y unmanaged devices skipped: ...              ← if any
[+] Summary: duration_s=... token_calls=... inventory_calls=... group_get_calls=... group_put_calls=... computer_get_calls=... not_found=... unmanaged=...
```

If no devices need to be added in additive mode, script exits quickly with:
```
[+] No-op: group already contains all N enrolled devices.
```

**Known Group IDs**

| Group | ID | Used for |
|---|---|---|
| GP Uninstall — June 2026 | 1470 | GP-Uninstall-June2026 wave |

Add new entries here as groups are created.

### Step 1.5 (optional) — fill "No Device Assigned" gaps from Jamf/Intune

ServiceNow "No Device Assigned" means the asset record has nothing linked to that user —
it does **not** mean the user has no device. Scoped to that cohort only (checking every
user for a shadow/extra device is a separate, more expensive workflow, not this step): for
each "No Device Assigned" username, look up Jamf and Intune directly and, if either shows
an active device, write it into the **same** `Serial` / `Platform` / `Model` columns step 1
uses — not a parallel set of columns. A device found this way isn't a different kind of
fact than one ServiceNow reported; it's the same fact ServiceNow's record was missing.
`Notes` gets a one-line provenance tag (`not in ServiceNow — found via jamf`) since that's
the only part that's genuinely different.

**Run this before step 3.** A row only gets checked for an app if it already has a real
Serial + Platform — filling gaps after the app step means those rows get skipped rather
than looked up. Order is: build (step 1) → this step → MDM/app steps (2–3).

This step is agent-driven, not script-driven — `jamf_get_user_devices` and
`intune_lookup_users` are MCP tools, and the enrichment scripts have no MCP access. The
procedure:

1. Pull the cohort from the report:
   ```zsh
   .venv/bin/python -c "
   import pandas as pd
   df = pd.read_csv('input/output/asset_report.csv', dtype=str).fillna('')
   print(df[df['Platform']=='No Device Assigned']['Username'].tolist())"
   ```
2. Look up every username in parallel, in one message: `intune_lookup_users`
   **once** with all usernames comma-separated (it's already a batch tool), and
   `jamf_get_user_devices` **once per username** (no batch parameter on that
   tool) — CLAUDE.md's "always batch independent MCP reads in parallel" rule.
3. Write the results to `input/output/snow_gap_findings.json`:
   `{"<username>": {"found": bool, "source": "jamf"|"intune"|"none", "serial":
   str, "platform": str, "model": str, "last_check_in": str}}`.
4. Merge into the report:
   ```zsh
   .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_snow_gap.py" \
     --findings input/output/snow_gap_findings.json
   ```

Overwrites `Serial`/`Platform`/`Model`/`Notes` on the same "No Device Assigned" rows in
place — idempotent, same as every other step. Once filled, a row looks like any other
device row: subsequent steps (MDM, app checks, the HTML report) need no special-casing for
it. A user Jamf/Intune also can't find gets a `Notes` tag instead
(`confirmed no active device (checked jamf/intune)`) and stays `No Device Assigned`.

On the 2026-08-25 recon run this filled **13 of 13** "No Device Assigned" users (12
Jamf-managed Macs checked in the same day, 1 Intune-managed Windows box) — the entire
bucket was a ServiceNow record gap, not a real "no device" population. Worth running every
time that platform shows up non-trivially; a 100% or near-100% hit rate is itself the
signal to escalate to whoever owns ServiceNow asset hygiene rather than to individual
users.

### Step 2 — add MDM enrollment status

```zsh
cd ~/work
passkey run jamf_api -- passkey run intune -- \
  .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_mdm.py"
```

Adds `MDM`, `MDM Status`, `MDM Last Check-In`, `MDM Detail`. macOS → Jamf, Windows → Intune,
dispatched on the `Platform` column step 1 derived. `--batch-size` (default 40) and
`--workers` (default 10) are the tuning knobs.

### Step 3 — add per-app install/health status

```zsh
cd ~/work
passkey run jamf_api -- passkey run intune -- \
  .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_app.py" --app Zscaler
```

Adds `<App> Status`, `<App> Health`, `<App> Source`. Run once per app; column sets coexist,
so `--app Zscaler` then `--app Slack` gives both. `<App> Status` is the **raw** signal (the
EA string, with its diagnostic nuance intact); `<App> Health` is the sortable
`healthy`/`unhealthy`/`unknown` collapse; `<App> Source` is provenance, so a value is never
ambiguous about how it was obtained.

Add `--summary-json /tmp/asset_pipeline_runs.jsonl` to any step for one telemetry object per run.

### Step 4 (optional) — render the shareable HTML report

```zsh
cd ~/work
.venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/asset_report_html.py" --source zscaler-recon.csv
```

No credentials and no API calls — it reads whatever columns the CSV already has and adapts.
Renders `${CLAUDE_SKILL_DIR}/../report/templates/asset-ops.html`, which supports two modes
from the same template and the same generic facet/search/sort/copy/export table JS:

- **Bare mode** — only step 1 has run (no `MDM Status` and no `<App> Status` column yet).
  There's no coverage verdict to compute, so this renders the old `device-list-ops`
  device-audit framing instead: plain stat tiles (Users / macOS / Windows / Outliers), a
  Platform breakdown table, and a **single flat Devices tab** — no verdict pills, no
  "Action Needed" language. Outliers = `No Device Assigned` + `Not Found in SN` + `Unknown`,
  read straight off the `Platform` column step 1 already wrote — no separate script needed.
  This is the mode for "just show me a device list, nothing enriched yet" — cross-team
  sharing, factual counts only.
- **Coverage-framed mode** — once step 2 and/or step 3 has run, this renders the full
  **Summary, Users, Devices** tabs with compliance verdicts, exactly as below. The Users tab
  is the one that drives action.

Once any enrichment column is present the report always renders coverage-framed — there is
no flag to force bare mode on an enriched CSV.

#### Why there is a Users tab

The CSV is device-grained, but the operative question is user-grained: *does this person
have a working machine?* That cannot be answered by filtering a device list, because one
user's devices are judged independently and scattered across the table. On the
zscaler-recon run, **27 of 76 non-compliant devices belonged to users who already had a
compliant one** — a third of the apparent remediation list was noise, while the users with
nothing were buried in the same rows.

`${CLAUDE_SKILL_DIR}/scripts/asset_coverage.py` derives five columns (no new API calls, all from existing data):

| Column | Meaning |
|---|---|
| `MDM State` | `managed` / `not managed` / `not applicable` — one binary axis |
| `Device Compliant` | `compliant` = managed **and** every scored app passes |
| `Status` | the per-user rollup, written onto every row of that user |
| `Coverage Ratio` | `1/3` — compliant over **checkable** devices |
| `Coverage Note` | on a failing row: `already has a working device: <serial>` |

`Status` is deliberately plain-language, not a jargon term — the report goes to people
outside CPE who don't use "coverage" day to day. Values, worst first: `Action Needed` ·
`Needs Recheck` · `OK (multi device)` · `OK` · `Can't Verify` · `No Device`.

Three rules that make the numbers trustworthy, each of which is wrong in an obvious way
if you skip it:

- **Unmanaged never passes.** An unmanaged device with the app installed is
  `non-compliant`: the app is there, but nothing can be enforced or verified on it. So a
  device can read `Zscaler: compliant` and `Device: non-compliant` — not a contradiction.
- **Only checkable devices are in the denominator.** A Mac plus two iPads is `1/1`, not
  `1/3`. iPads, virtual desktops and placeholder serials have no agent to query, so
  counting them would invent a compliance failure for their owner.
- **A stale sole-working device doesn't count as OK.** If a user's only compliant device
  hasn't checked in for over `--stale-days` (default 14) they become `Needs Recheck`, not
  `OK (multi device)`. On the recon run this caught 6 users, one whose single device was
  last seen 59 days ago — a naive rollup would have dropped them off the action list
  entirely.

MDM is reported as a binary because that's the filter you want, but the underlying reason
(management lapsed vs never enrolled) is different remediation and is preserved: it's the
tooltip on each device row and its own Summary breakdown.

The two filter combinations that replace manual cross-referencing:

| Filter | Gives you |
|---|---|
| Users tab → `Action Needed` + `Needs Recheck` | the real action list, with blocking issue and serials per user |
| Devices tab → `non-compliant` + status `OK (multi device)` | stragglers — asset cleanup, not a remediation ticket |

#### CSV export

Both tabs export **only the currently visible rows**, so filter first and the export is
already scoped. The CSV is generated from a JSON payload embedded in the page, **not** by
scraping the table — a cell can hold a pill plus a sub-note, and reading its text glued
them together (`Needs Recheck working device last seen 22d ago`, `non-compliantalready
has a working device: X`). Every exported value is atomic:

- Counts are integers in their own columns (`Compliant Devices`, `Checkable Devices`,
  `Assigned Devices`). The `1/3` ratio is display-only and never exported — Excel reads
  `0/2` as text or a date, so it can't be summed, sorted, or pivoted.
- `Priority` (1–6, worst first) makes the status order sortable in a spreadsheet;
  sorting the text column alphabetically would put `Needs Recheck` in the wrong place
  relative to `Action Needed`.
- Staleness is its own numeric column (`Working Device Age (Days)`).
- Serial lists are `; `-separated; the devices export adds `MDM Reason` (the tooltip) and
  `Other Working Device Serial` as a bare serial rather than a sentence.
- Written with a UTF-8 BOM and CRLF so Excel on Windows doesn't mojibake it, ASCII
  separators (`3x`, `; `) instead of `×`/`·`, empty cells rather than `—` placeholders,
  and a leading `'` on any value starting `=`/`+`/`-`/`@` to defuse formula injection.

A `Needs Recheck` user with nothing technically failing still gets a stated
`Blocking Issue` (`1x working device not seen for 59d`) — a blank cell on an action-list
row reads as "nothing to do", which is the opposite of true.

Flags: `--stale-days N`, `--compliance-app <name>` (default: every app column must pass),
`--ignore-return-states` (drop `Waiting on Return` assets from the ratios; **off by
default** so nothing is hidden silently — on the recon run it moved 5 users to `OK`
and cut stragglers from 27 to 20).

**Use this template, not `compliance.html`.** The compliance template carries a
remediation-script block and a copy-back prompt that this workflow has no use for; the
CSV is the deliverable and the skill owns the remediation guidance.

Output is `reports/<source>-YYYY-MM-DD-HHMM.html`, **timestamped to the minute**, so a
revised pull produces a new file instead of overwriting the previous one. The header
carries two distinct timestamps, which are not the same thing:
- **Generated** — when the HTML was rendered
- **Data pulled** — the CSV's mtime, i.e. when the API data was actually collected

A report rendered from an old CSV shows a stale "Data pulled" — that's the signal to
re-run steps 1–3 rather than trusting the page.

The CSV itself keeps the stable path `input/output/asset_report.csv` so steps 2–4 can
chain onto it; run history lives in the timestamped `.bak-YYYYmmdd-HHMMSS.csv` copies
each rewrite leaves behind.

---

## How the app signal is resolved

Step 3 resolves the `--app` token at runtime, in this order. Nothing is hardcoded in the script.

1. **Override** — `${CLAUDE_SKILL_DIR}/scripts/app_signal_map.yaml`, matched on `key`/`label`. Only needed when
   the token is ambiguous or unmatchable.
2. **Dynamic EA match** — the app token is matched against the extension-attribute names in
   the inventory payloads already fetched (zero extra API calls). `zscaler` finds
   `Compliance - Zscaler Status`; `slack` finds `Compliance - Slack`. On a multi-match the
   shortest name wins and the others are **reported**, not silently discarded.
3. **Jamf application inventory** — per-device `section=APPLICATIONS`, yielding
   `installed (<version>)` / `not installed`, `Source = jamf-inventory`.
4. **No match** → `No Signal Mapped`, `Source = none`. Explicit, never blank.

Windows is independent of all of the above: substring match on Intune Managed Apps
`displayName`, collapsed via `STATE_PRIORITY = installed > failed > notApplicable > unknown`.

**When to add a YAML override.** Only when matching genuinely can't work:
- The EA name is worded differently from the app. `globalprotect` can never substring-match
  `Compliance - Global Protect Status` — two words vs one. This entry is mandatory.
- The token hits several EAs. Five attributes contain "nessus"; the override pins one.
- The generic word lists misread the app's status strings.

`unhealthy_contains` is evaluated **before** `healthy_contains`, because real values carry
both signals — `ERROR - Installed (Not Enrolled)` must not read as healthy. The corollary:
plain `installed` is safe in `healthy_contains`, since `not installed` is caught first. A
narrower `"ok - installed"` looks safer but silently marks the entire Windows fleet
`unknown`, because Intune reports a bare `installed`.

---

## Expected output shape

```
[+] input/output/asset_report.csv — 471 rows (362 users, 389 devices)
    Platform: No Device Assigned 38 · Not Found in SN 44 · Unknown 1 · Virtual Desktop 3 · Windows 197 · iOS/iPadOS 7 · macOS 181
    State:    In use 380 · Missing 3 · Replacement Hold 6
    Substate: Primary 272 · Secondary 43 · REPL - Waiting on Return 33 · ...
[i] calls: snow=15  duration=2.6s
```

Step 2 and 3 additionally print a `Skipped:` line accounting for every unlooked-up row, and
step 3 prints a `[!] N device(s) need attention` tail capped at 25 rows.

**Report the summary, not the CSV.** Point the user at the file path for detail.

---

### Pattern 0: Reporting a device list as if it were a people list

**Indicators:** A remediation list where several rows share a `Username`, and the user has
another row that is `compliant`. Or a headline like "76 devices need Zscaler" when many of
those users are already working fine.

**Root Cause:** Device-grained data answered with a device-grained filter. Compliance per
device is not the same question as coverage per person, and multi-device users make the two
diverge — on the recon run, by a third of the list.

**Remediation:** Report from the **Users tab** (`Status`), not the device count.
Quote both numbers and keep them distinct: *N users need action* and *M devices block
someone*, never a bare device total. Stragglers go to asset cleanup, not to a Zscaler
ticket — check `Coverage Note` before writing one.

**Edge Cases:** `Needs Recheck` users look fine by every device-level metric. They are
the highest-risk bucket precisely because nothing about the device row is wrong.

---

## Failure Patterns

### Pattern 1: Placeholder serial reported as an enrollment gap

**Indicators:** `MDM Status = Skipped (placeholder serial)`, or (before this was handled)
a `Not Found in Jamf` row whose `Serial` reads `PENDING`, `N/A`, `NONE`, `TBD`.

**Root Cause:** ServiceNow `serial_number` is free text, so procurement placeholders land in
it. Querying one returns nothing, which looks identical to a device that exists but was never
enrolled — two completely different problems.

**Diagnostic Steps:**
1. Read step 1's `[!] N asset(s) with a placeholder serial` line — it names user, value, model.
2. Confirm in ServiceNow (`snow_lookup_device_details`) that the asset record really carries
   the placeholder rather than the script mangling a real serial.

**Remediation:** Nothing to fix in the fleet — this is an asset-record correction. Flag the
list to Ticket Assignee for ServiceNow cleanup. `is_real_serial()` in `fleet_common.py` holds the
placeholder set; add new values there as they turn up.

**Edge Cases:** A genuinely short serial would trip the `len >= 5` guard. No real Apple or
Dell serial is that short, but check the model before assuming the value is junk.

---

### Pattern 2: Device that has a serial but no MDM record to find

**Indicators:** `Skipped (mobile device)` / `Skipped (chromeos device)` /
`Skipped (virtual desktop)`. Before this was handled, these surfaced as
`Not Found in Jamf` or `Not Found in Intune` on rows whose `Model` reads `iPad …`,
`Galaxy Tab …`, `Chromebook …`, or `AWS Virtual Server`.

**Root Cause:** Platform is derived from ServiceNow model/manufacturer, and several vendors
build for more than one OS. An iPad's manufacturer is Apple, so a manufacturer-first check
calls it `macOS` — but iPads live in Jamf's **mobile-device** inventory, not
`computers-inventory`, so the lookup can only ever miss. Same for Samsung, which makes both
Android tablets and Windows laptops.

**Diagnostic Steps:** Read `Model` on any `Not Found in <MDM>` row. If it names a phone,
tablet, Chromebook, or virtual server, the platform derivation is the bug, not enrollment.

**Remediation:** Already handled — `derive_platform()` runs **model-keyword** checks before
the manufacturer list, so the more specific signal wins. On this fleet that removed 6 of 25
false `Not Found in Jamf` results, and on the 3548-device list it cut `Unknown` from 75 to 26
(23 of which have a genuinely blank model). If the user needs real iPad or Android MDM state,
that's a Jamf/Intune mobile endpoint this pipeline doesn't cover — say so rather than
reporting the row as unenrolled.

**Edge Cases:** The inverse error is worse and is specifically guarded against: an Acer or MSI
laptop left as `Unknown` gets skipped from Intune entirely, which reads as "not checked" when
the device is in fact enrolled. The Windows vendor list therefore extends past the big three.
`Skipped (unknown platform)` should mean only "we could not identify this model at all" — if
you see it on a recognizable laptop, the vendor list needs an entry.

---

### Pattern 3: Extension attribute silently missed

**Indicators:** `<App> Source = jamf-inventory` or `none` for an app you know has an EA; or
`[i] No extension attribute matches '<app>'` when one plainly exists in Jamf.

**Root Cause:** Two traps, both live on this fleet. Jamf mixes dash characters across EA
names — `Compliance - Zscaler Status` uses a hyphen, `Compliance – Nessus – Connectivity`
uses an **en-dash** — so a raw substring match misses attributes. And EA values arrive as
**lists**, not scalars, sometimes containing a multi-line block.

**Diagnostic Steps:**
1. `jamf_get_computer_full_context(serial, sections=["EXTENSION_ATTRIBUTES"])` on a known-good
   device and read the exact attribute name, character for character.
2. Compare against the app token. If the EA wording differs from the app name (spaces,
   suffixes like ` Status`), substring matching cannot bridge it.

**Remediation:** Add a `paths` entry to `${CLAUDE_SKILL_DIR}/scripts/app_signal_map.yaml`. Matching runs through
`normalize_label()`, so either dash form works in the YAML. Never "fix" this by hardcoding an
EA name in the script — that violates the dynamic-resolution rule.

**Edge Cases:** Multi-line EA values are collapsed to `field; field; field` by
`flatten_value()`. If a raw newline ever reaches the CSV it breaks grep/awk over the output
and garbles the console summary — that's the bug to look for, not the EA itself.

---

### Pattern 4: Whole platform reads `unknown` health

**Indicators:** `Health: unknown` dominates, and the count is close to the device total for
one platform while `Status` values look perfectly sensible.

**Root Cause:** The app's `healthy_contains` list doesn't match the status strings that
platform actually emits. macOS EA values are verbose (`OK - installed (4.8.0.83)`); Intune
emits a bare `installed`. A word list tuned only against macOS leaves every Windows row
unclassified.

**Diagnostic Steps:** Read the `Status:` breakdown alongside `Health:`. If a high-count status
value isn't matched by any token in either list, that's the gap.

**Remediation:** Widen `healthy_contains` in `app_signal_map.yaml`. Rely on unhealthy-first
precedence rather than writing narrow, over-qualified tokens.

**Edge Cases:** `unknown` is also the correct answer for Intune's literal `unknown` and
`notApplicable` states, and for every `Not Found` / `Skipped` row. Some `unknown` is expected —
compare against the `Source` breakdown before treating it as a bug.

---

### Pattern 5: Step 2 or 3 run before step 1

**Indicators:** `[-] Report not found: input/output/asset_report.csv`, or
`[-] … is missing required column(s): Serial, Platform`.

**Root Cause:** The enrichment steps are deliberately independent, so they don't regenerate
the base report. The second message means the CSV predates the current schema.

**Remediation:** Run step 1. The scripts print the exact command. Never hand-edit the CSV to
add the missing columns.

**Edge Cases:** A CSV older than `--max-age-hours` (default 24) triggers a staleness warning
but still runs — MDM state moves, so mention the age when reporting results off an old file.

---

### Pattern 6: Every user reads `Can't Verify` when step 2 was skipped

**Indicators:** Step 4 summary shows `coverage: Can't Verify N · No Device M` with
zero `OK (multi device)`/`Action Needed`/`OK` — even though step 3 clearly scored the app.

**Root Cause:** `asset_coverage.py`'s checkable gate used to require an MDM signal
(`MDM State != not applicable`). Running only step 3 (app check) without step 2 (MDM
enrollment) — the normal path for a plain "is Zscaler installed" ask — left `MDM Status`
absent from every row, so every device read `not applicable` and got excluded from the
denominator entirely. The mirror case (MDM without app) was already handled; this one wasn't.

**Remediation:** Fixed in `asset_coverage.py` — `device_verdict()` and the checkable
calculation in `add_compliance()` both take an `mdm_available` flag (`"MDM Status" in
df.columns`). When false, compliance is scored on the app axis alone and checkability
falls back to "has a real serial" instead of "has an MDM state." Run step 2 first only
when the user actually wants the MDM-managed gate on top of the app check.

**Edge Cases:** If step 2 *was* run, behavior is unchanged — MDM is still required for
`compliant`. This only changes the app-only path.

---

### Pattern 7: Gap-fill rows show "Skipped (no serial)" next to a serial you already found

**Indicators:** A row has a `Serial`/`Platform` filled in from Jamf or Intune (or a
parallel "MDM ..." column set carrying the same serial) but the app-check column still
reads `Skipped (no serial)`.

**Root Cause:** Step 3 (app discovery) only looks up rows that already have a real
`Serial` + `Platform`. If the gap-fill step ran *after* step 3, the app check saw the
original blank row and skipped it — the fill and the app check never touched the same
data at the same time, so the serial and the "no serial" skip both linger on the same row.

**Remediation:** Run step 1.5 (gap-fill) before step 3, not after — `Serial`/`Platform`/
`Model` on those rows have to exist before app discovery runs. Re-running step 3 after a
gap-fill picks the newly filled rows up like any other device. Also don't give a filled
row its own column set (`SN Gap Flag`, `MDM Source`, `MDM Serial`, ...) — it duplicates
`Serial`/`Platform`/`Model` that are already on the row and reads as two conflicting
sources of truth for the same device. A one-line `Notes` tag is enough provenance.

---

### Windows-only Managed Apps variant of step 3

Step 3's default Windows path (`asset_report_app.py`) reads Intune **software inventory** —
fine for a mixed macOS/Windows population, but the older, less reliable of Intune's two
signals. When the target list is **Windows-only** and already narrowed (e.g. this skill's
own step 1 run with `--platforms Windows`), `${CLAUDE_SKILL_DIR}/scripts/intune_app_lookup.py`
checks the same app against Intune's **Managed Apps** intent/state data instead, which is
more accurate for that Windows-only case. Use this variant when the user names a CSV
**and** an app together for a Windows-only list; use step 3 proper for a mixed population.

```zsh
cd ~/work
passkey run intune -- .venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/intune_app_lookup.py" \
  --app "Zscaler" \
  --workers 10
```

- **Input:** `input/output/asset_report.csv` (from step 1) via `--location` (override only
  if the report lives elsewhere). Filters to `Platform == "Windows"` internally.
- **Output:** `input/output/windows_devices.csv` (Windows-only subset: Username, Serial,
  Model) and `input/output/windows_<app>_status.csv` (same subset plus `<App> Status` /
  `<App> Detail`), defaulting to `input/output/windows_<app_slug>_status.csv` via `--output`.
- **Access required:** `intune` passkey profile. No MCP needed at execution time.
- Windows only — macOS devices in the input list are counted and reported as skipped, never
  silently dropped. Always report the skipped-platform count so a Windows-only result isn't
  mistaken for "macOS was checked too and came back clean."
- Status values come from Intune's Managed Apps intent/state, not a fixed enum: `installed`,
  `failed`, `notApplicable`, `unknown` (assigned but install not confirmed — often a
  certificate-installer companion app rather than the main app itself), plus this script's
  own `Device Not Found in Intune` / `No Assigned User` / `Lookup Error` for devices that
  don't resolve.
- On a multi-match (e.g. `Zscaler Certificate Installer:unknown; Zscaler:installed`), the
  script picks the highest-priority state across all matches (`installed` > `failed` >
  `notApplicable` > `unknown`) — not a failure, just a helper app with its own assignment.
  Only worth a second look if the *primary* app itself is stuck on `unknown`.
- Fleet-wide "who's missing this app" reporting is out of scope for this variant — it's one
  Graph lookup per device (fine for a list, not efficient for a fleet-wide audit); a
  fleet-wide report needs a single Intune report-API call gated behind a missing Graph
  permission (`DeviceManagementApps.Read.All`, tracked in CPE-4254).

**Failure patterns specific to this variant:**
- *High `Device Not Found in Intune` count* — device isn't Intune-managed (not enrolled,
  Config Manager-only, decommissioned) or the ServiceNow serial doesn't exactly match
  Intune's `serialNumber` field. Cross-check one or two serials with `intune_lookup_device`
  (MCP tool); if Intune also can't find them, it's a real enrollment gap, not a script bug.
- *`403 Forbidden` mid-run* — the Intune app registration is missing the Graph permission
  scope for `mobileAppIntentAndStates`. Escalate to the Intune admin rather than
  retry-looping.
- Escalate to Lead Engineer if `Device Not Found in Intune` exceeds ~20% of the Windows
  list, or if a token fetch errors outright (credentials may be rotated).
- Standalone (no MCP/passkey): given an `asset_report.csv`, confirm it has `Serial`/
  `Platform` columns and count the Windows subset so the run's scope is known before creds
  are available. No macOS equivalent exists yet — say so rather than implying coverage.

---

### Pattern 8: Same serial on two rows

**Indicators:** Step 1 prints `[!] N duplicate serial(s)`.

**Root Cause:** A shared or reassigned asset is assigned to two users in ServiceNow.

**Remediation:** Both rows are kept and both get identical enrichment values — deduping would
hide a real ServiceNow data problem. Report the count. If it's high, that's an asset-hygiene
item for Ticket Assignee, not a pipeline fault.

**Edge Cases:** This is why enrichment results are keyed serial → **list of row indices**. A
serial-keyed dict silently drops the second row, which reads as `Skipped` and quietly
undercounts. If a future change touches `jamf_pass()`, keep that mapping. The Jamf group
sync (Pattern 9 below) dedupes serials on purpose instead — it's pushing group membership,
not writing per-row columns, so there is nothing to undercount by collapsing to one entry.

---

### Pattern 9: 409 Unmanaged Devices (Jamf group sync)

**Indicators:** `[!] N unmanaged Jamf IDs — resolving serials...`

**Root Cause:** Device exists in Jamf but MDM management has lapsed (expired profile, wiped
and not re-enrolled).

**Remediation:** `jamf_group_sync.py` handles this automatically per chunk — parses
unmanaged Jamf IDs from the error, resolves their serials, strips them, and retries that
chunk. No manual action needed. Log the skipped serials for follow-up re-enrollment if
count is high (>10).

---

### Pattern 10: Serials Not Found in Jamf (Jamf group sync)

**Indicators:** `[!] X serials not found in Jamf (skipping): ...`

**Root Cause:** Device is in `asset_report.csv` with `Platform == "macOS"` but was never
enrolled in Jamf, or is a non-Mac serial that got through the platform filter.

**Diagnostic:** Check the `Model` column in `asset_report.csv` for those serials. If the
model is clearly a Mac, the device needs Jamf enrollment.

---

### Pattern 11: 400 Bad Request on Inventory Validation (Jamf group sync)

**Indicators:** `Inventory validation failed (batch N): 400 Client Error`

**Root Cause:** RSQL filter syntax rejected — usually too many serials or unsupported
field name. Current limit is 40 per batch with `hardware.serialNumber` field.

**Remediation:** Reduce the `40` batch size in `jamf_group_sync.py`'s inventory-validation
loop to `20`.

---

### Pattern 12: Partial Sync Exit (Jamf group sync)

**Indicators:** `[-] Partial sync: added X/Y expected...` and non-zero exit code.

**Root Cause:** Non-retryable API error during chunk push.

**Remediation:** Re-run once; if repeated, escalate with the summary line and group ID.

---

## Escalation Criteria

Stop and involve Lead Engineer when:
- \>20% of the user list comes back `Not Found in SN` — upstream data problem, and the
  scripts say so themselves
- \>20% of a platform subset is `Not Found in <MDM>` — enrollment gap, not a script fault
- An EA multi-match is reported and no override obviously applies — picking one silently
  would fabricate a result
- Jamf returns `400` on inventory even at `--batch-size 20`
- A step's summary shows a `State` breakdown dominated by retired states, meaning the
  all-states default pulled in more dead hardware than expected for this list
- A Jamf group sync chunk keeps 409-ing after the unmanaged-strip retry and the same IDs
  reappear
- The target Jamf group ID doesn't exist (404 from Jamf PUT) — need to create the group first
- The Jamf group sync errors on token fetch (Jamf API client may be rotated)
- Additive-mode sync reports repeated partial-sync failures on the same group/input pair

---

## Standalone Mode

With no API access, this skill can still: read an existing `asset_report.csv` and interpret
it; explain which column came from which step and which source; classify a pasted EA value
via the `app_signal_map.yaml` word lists; identify the failure patterns above from a pasted
summary block; and diagnose a pasted Jamf group sync failure/response the same way it
diagnoses enrichment failures. The `Source` column makes any row self-describing without a
re-query.

---
*Last verified: 2026-08-27 | Owner: CPE Team*
