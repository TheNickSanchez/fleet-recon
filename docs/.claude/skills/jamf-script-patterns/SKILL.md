---
name: jamf-script-patterns
description: "Environment and execution gotchas for scripts run as root under Jamf (PATH, parameter offsets, idempotency, version resolution, root-vs-console-user keychain context) plus the live-validation harness for proving a fix under actual root/Jamf execution before promoting it to production. Load alongside any domain skill that writes a remediation script."
argument-hint: "script content or failure symptom"
user-invocable: true
---

# Jamf Script Authoring Patterns

Use this skill whenever writing or debugging a Jamf policy/EA script.

---

## Full Playbook

# Jamf Script Authoring Patterns Skill

## Overview

Environment and execution gotchas specific to scripts that run **as root, under Jamf**
(clean environment, no user shell config, `$1`-`$3` reserved). Load this alongside any
domain skill that ends in "write a remediation script" — it's the shared foundation, not
a domain of its own.

**Load this skill when:** writing or debugging a Jamf policy script, an Extension
Attribute script, or diagnosing a script that behaves differently under Jamf than in a
local test.
**Do NOT use for:** Jamf API/MCP call patterns (`jamf-api-patterns`) or pkg-building
(`build-macos-pkg`).

---

## Prerequisites

- **Data to gather first:** the script's shebang, whether it calls `brew`/other
  non-`/bin`/`/usr/bin` tools, and whether it runs standalone or via a Jamf policy
  (parameter offset differs).

---

## Failure Patterns

### Pattern 1: `brew: command not found` under Jamf

**Indicators:** `sudo: brew: command not found` when a script calls `brew`, but the same
script works fine when run manually as the logged-in user.

**Root Cause:** Jamf runs scripts as root with a clean environment — `/opt/homebrew/bin`
and `/usr/local/bin` are absent from root's PATH. `command -v brew` fails the same way.

**Remediation:** Detect and use the full path for every brew invocation:
```zsh
brew_bin=""
[[ -x "/opt/homebrew/bin/brew" ]] && brew_bin="/opt/homebrew/bin/brew"
[[ -x "/usr/local/bin/brew" ]] && brew_bin="/usr/local/bin/brew"
[[ -z "$brew_bin" ]] && { echo "ERROR: brew not found"; exit 1; }
# Then: sudo -u "$logged_in_user" "$brew_bin" upgrade ...
```

---

### Pattern 2: Script dies silently with `set -euo pipefail` + `grep`

**Indicators:** Script output ends abruptly; Jamf shows "exit code: 1" with no
diagnostic text.

**Root Cause:** `grep` exits 1 on zero matches. With `set -e` + `pipefail`, the whole
pipeline exits before any error handling runs — this bites `curl ... | grep` patterns
especially hard.

**Remediation:**
```zsh
URL=$(curl -fsS --max-time 30 -o /dev/null -w '%{url_effective}' -L 'https://...' 2>/dev/null) || URL=""
[[ "${URL}" != *".dmg"* ]] && { echo "ERROR: could not resolve download URL"; exit 1; }
```

---

### Pattern 3: `command not found` inside nested function → subshell chains

**Indicators:** `export PATH` at the top of the script works for top-level `$()`
subshells but fails inside `$()` calls nested in functions called from other functions —
`command not found: date`, `command not found: rm`, etc.

**Root Cause:** zsh function scope combined with Jamf's restricted execution environment;
PATH export doesn't propagate reliably through nested function → subshell chains.

**Remediation:** Use absolute paths for every external binary:
```zsh
readonly _DATE=/bin/date
readonly _RM=/bin/rm
readonly _STAT=/usr/bin/stat
readonly _ID=/usr/bin/id
readonly _LAUNCHCTL=/bin/launchctl
readonly _DSCL=/usr/bin/dscl
```
**Verified:** CPE-4028, 2026-06-03, Script 642.

---

### Pattern 4: Wrong parameter used as a fallback default

**Indicators:** A script-specific parameter reads garbage — e.g. a mount point (`/`)
being treated as an expected cert fingerprint.

**Root Cause:** Jamf ALWAYS passes `$1`=mount point, `$2`=computer name, `$3`=username to
every script. Script-specific parameters start at `$4`. Using `$1`/`$2` as a fallback
(e.g. `${4:-${1:-DEFAULT}}`) silently substitutes a Jamf reserved value.

**Remediation:** Read only `$4`+; hard-code true defaults as named variables, never fall
back onto `$1`/`$2`/`$3`.

**Real incident:** `${4:-${1:-DEFAULT}}` caused `$1=/` to be used as the expected cert
fingerprint on 596 machines (CPE-3852).

---

### Pattern 5: Homebrew formula name assumption breaks version checks

**Indicators:** `brew upgrade node` (or similar) fails to find the installed formula.

**Root Cause:** The formula may be versioned (`node@20`, `node@22`, ...) rather than the
bare name.

**Remediation:** Detect the actual formula first: `brew list --formula | grep -E "^node(@[0-9]+)?$"`.
Applies to any versioned formula — always detect before `brew upgrade`.

---

### Pattern 6: Broken Homebrew binary — exists but exits 134

**Indicators:** Binary exists and is executable but exits 134 with "Library not loaded".
Script gets an empty version string and silently skips the device.

**Remediation:** If `"$binary" --version` returns empty, fall back to the Cellar
directory name as the version signal:
- Dir version < latest → `brew upgrade` (fixes version AND dependencies)
- Dir version == latest → `brew reinstall` (fixes broken deps without a version bump)

---

### Pattern 7: Wall-clock timeout kills a healthy, slow download

**Indicators:** `--max-time 120` kills a 217MB download that's 75% complete.

**Remediation:** Use stall detection instead of (or in addition to) an absolute ceiling:
```bash
curl -fL --max-time 600 --speed-limit 1024 --speed-time 30 --retry 3 --retry-delay 5 -o "$output" "$url"
```
`--speed-limit 1024 --speed-time 30` aborts if throughput drops below 1KB/s for 30s;
`--max-time 600` is the absolute ceiling.

---

### Pattern 8: Preflight curl hangs behind a captive portal

**Indicators:** A preflight curl with `--max-time 10` hangs for 15 minutes.

**Root Cause:** `--max-time` bounds total transfer time, not connection time — a captive
portal can hold the TCP/SSL handshake open indefinitely.

**Remediation:** Always add `--connect-timeout`:
```bash
curl -fsSL --connect-timeout 8 --max-time 15 "$url"
```

---

### Pattern 9: `security find-certificate` (or any keychain lookup) misses certs when run as root

**Indicators:** A cert/keychain lookup succeeds when the script is run interactively as
the logged-in user, but returns empty/not-found when the identical script runs via an
actual Jamf policy — no error, just silently behaves as if the cert doesn't exist.

**Root Cause:** `security find-certificate` with no explicit keychain argument only
searches the *caller's* default keychain search list. Jamf runs scripts as root, and
root's search list is not the console user's login keychain — a cert that lives in the
user's login keychain is invisible to a bare-root lookup, even though the same command
found it when you ran it yourself in Terminal.

**Remediation:** Wrap the lookup in `sudo -u "$CONSOLE_USER"` when running as root —
the same pattern every other user-scoped operation in a well-formed Jamf script already
uses for binary version checks, PATH resolution, etc.:
```bash
find_certificate() {
    if [ "$(id -u)" -eq 0 ]; then
        sudo -u "${CONSOLE_USER}" security find-certificate "$@"
    else
        security find-certificate "$@"
    fi
}
```

**Edge Cases:** A cert delivered via an MDM *configuration profile* usually lands in the
System keychain, which root can see without this wrapper — the failure only shows up
for certs the user (or another process) put in their own login keychain. Wrap it
unconditionally anyway; the `sudo -u` path is a correct no-op when the cert is already
root-visible.

**Verified:** CPE-4264, 2026-08-19, Script 637 (Antigravity CLI / Zscaler cert fix) —
interactive test showed 129 certs found; first Jamf-policy run (before this fix) would
have silently reported zero.

---

### Pattern 10: `curl: (16) Error in the HTTP2 framing layer` / middlebox download stalls

**Indicators:** `curl: (16) Error in the HTTP2 framing layer`, `curl: (28) Operation timed out`, or checksum mismatches when downloading large binaries (>100MB) over corporate networks.

**Root Cause:** TLS-intercepting forward proxies (Zscaler, Palo Alto) desynchronize HTTP/2 multiplexed streams and window flow control on large single-binary payloads. Default `curl --retry` also fails to catch transport-layer disconnects.

**Remediation:** Force HTTP/1.1, replace hard wall-clock timeouts with stall-detection, add retry-all-errors, and enable resume support:
```bash
curl -fL --http1.1 \
     --speed-limit 1024 --speed-time 30 \
     --max-time 600 \
     --retry 3 --retry-delay 5 --retry-all-errors \
     -C - \
     -o "$output" "$url"
```
**Verified:** CPE-4161, 2026-08-20, Script 628 (Claude Code CLI installer).

---

### Pattern 11: Subshell interactive flag (`zsh -lic`) hanging in unattended root daemon context

**Indicators:** Script hangs indefinitely during PATH or binary probing when spawned under Jamf daemon context.

**Root Cause:** The `-i` (interactive) flag instructs zsh to initialize job control and wait for TTY / stdin, which halts unattended background execution.

**Remediation:** Use login-only execution (`zsh -lc '<cmd>'`) and wrap with an alarm/timeout runner:
```bash
run_with_timeout() {
    local secs="$1"; shift
    perl -e 'alarm shift @ARGV; exec @ARGV or exit 127' "$secs" "$@"
}

path_resolves() {
    if [ "$(id -u)" -eq 0 ]; then
        run_with_timeout 20 sudo -u "${CONSOLE_USER}" zsh -lc 'command -v claude' 2>/dev/null | grep -E '/claude$' | head -1 || true
    else
        run_with_timeout 20 zsh -lc 'command -v claude' 2>/dev/null | grep -E '/claude$' | head -1 || true
    fi
}
```
**Verified:** CPE-4161, 2026-08-20, Script 628.

---

## Live Validation Strategy (prove it under root, not just interactively)

Interactive testing (`bash script.sh` as yourself) does not exercise the same code path
as an actual Jamf deployment (root, clean environment, console-user resolution via
`/dev/console`). A fix that works interactively can still do nothing once deployed —
Pattern 9 above is a direct example: it passed an interactive test and would have
silently failed in production.

**Standard harness — a disposable script + policy kept wired together for exactly this:**

1. **Test script slot:** a sandbox script (e.g. Jamf script ID 685, category
   "05 - Sandbox") — overwrite its `script_contents` with the candidate fix via
   `jamf_update_script`. Never test unvalidated logic directly in the production
   script ID.
2. **Test policy:** a policy already scoped to run that test script on a manual
   trigger event (e.g. policy 1460, event `arlo_test`).
3. **Run it for real:** `sudo jamf policy -event <trigger>` on a device you have local
   access to. This executes as root through the actual Jamf policy pipeline —
   the same context production devices run under.
4. **Verify the claim, not just the exit code:** read the script's own log output, then
   independently check the state it claims to have changed (`ls -la` a directory it
   should have created, `grep` a config file it should have edited, etc.). A script
   exiting 0 does not prove the fix worked — Pattern 2's `pipefail` failure mode and
   Pattern 9's silent-miss both exit non-zero or zero in ways that don't tell the whole
   story on their own.
5. **Only after a live pass**, promote the validated content into the real production
   script ID via `jamf_update_script`, then read the script back to confirm the
   uploaded content matches what was validated before considering it shipped.

**Never treat an interactive-only test as sufficient validation for any logic that
behaves differently under root** — keychain/security access (Pattern 9), PATH
resolution, or console-user detection are the usual suspects.

---

## Idempotency (non-negotiable on every script)

Always check current version/state before acting; skip with `exit 0` and an "already up
to date" log message if already at target — never `exit 1` for a no-op.

---

## Version Resolution Strategy (priority order — never hardcode)

1. GitHub Releases API: `curl -s https://api.github.com/repos/{owner}/{repo}/releases/latest`
2. Vendor download/releases page (parse HTML with Python `re`)
3. Homebrew Cask formulae: `brew info --json=v2 --cask <app>`
4. If all fail → `exit 1` with "could not resolve version" and log the gap

### Known Version Sources
| App | Source | Method |
|-----|--------|--------|
| iTerm2 | iterm2.com/downloads.html | HTML scrape |
| Node.js | nodejs.org/dist/latest-vXX.x/ | URL parse |
| Cursor | downloader.cursor.sh/mac/installer/universal/dmg | Redirect URL |

---

## Escalation Criteria

- A script needs a binary with no reliable absolute path across the fleet (custom
  vendor-installed tooling in variable locations) — escalate rather than guessing paths.
- Version resolution fails against all three sources for a given app — flag as a gap,
  don't ship a hardcoded fallback version.

---

## Standalone Mode

Fully standalone — every pattern above is a code-level fix you can apply from pasted
script content and a description of the failure, no MCP required.

---
*Last verified: 2026-08-19 | Owner: CPE Team*
