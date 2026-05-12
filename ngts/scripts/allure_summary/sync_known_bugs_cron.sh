#!/bin/bash
# Nightly regeneration of /auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_baseline.json
# from Redmine saved query 36102 ("nvos verification open issues").
#
# Canonical install location (what cron invokes):
#   /auto/sw_system_project/NVOS_INFRA/bug_attribution/sync_known_bugs_cron.sh
# A copy lives in the repo at
#   ngts/scripts/allure_summary/sync_known_bugs_cron.sh
# for recovery / source-of-truth. Edits should go to the repo copy and be
# re-deployed to the shared location.
#
# Install (one-liner on a regression player with /auto autofs + REDMINE_API_TOKEN):
#
#   crontab -l > /tmp/cron && cat >>/tmp/cron <<'EOF'
#   # NVOS known-bugs baseline regen, every night at 02:30 local time
#   30 2 * * * /auto/sw_system_project/NVOS_INFRA/bug_attribution/sync_known_bugs_cron.sh >> /auto/sw_system_project/NVOS_INFRA/verification_files/known_bugs_baseline.cron.log 2>&1
#   EOF
#   crontab /tmp/cron
#
# Output is appended to known_bugs_baseline.cron.log next to the JSON, so a
# `tail -50 known_bugs_baseline.cron.log` on any player tells you the last
# refresh time and any errors.
#
# Required env (inherited from the shell that installed the crontab, or set
# inside this script if cron starts with a bare environment):
#   REDMINE_API_TOKEN   - same token used by check_redmine_issues.py
#
# Optional env overrides (defaults shown):
#   REPO   - sonic-mgmt checkout. Derived from this script's location if it
#            sits inside a sonic-mgmt tree (the in-repo recovery copy);
#            otherwise falls back to /root/mars/workspace/sonic-mgmt (the
#            MARS canonical path). Override on dev workstations.
#   PY     - python interpreter   (defaults to $REPO/.venv/bin/python)
#   OUT    - baseline JSON path   (defaults to the shared NVOS_INFRA location)
#   DEVTS  - devts checkout added to PYTHONPATH if it exists (defaults to
#            $(dirname $REPO)/devts; silently skipped when absent)
#
# Exit codes:
#   0  - new baseline written
#   1  - sync failed (Redmine 5xx / network / no token); old baseline left alone
#   2  - CLI usage error
set -euo pipefail

# Resolve REPO: derive from script location if it looks like a sonic-mgmt
# checkout (so the in-repo recovery copy "just works"); else fall back to
# the MARS canonical path.
_self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_derived_repo="$(cd "$_self_dir/../../.." 2>/dev/null && pwd || true)"
if [ -n "$_derived_repo" ] && [ -f "$_derived_repo/ngts/scripts/allure_summary/sync_known_bugs.py" ]; then
    REPO="${REPO:-$_derived_repo}"
else
    REPO="${REPO:-/root/mars/workspace/sonic-mgmt}"
fi

PY="${PY:-$REPO/.venv/bin/python}"
SCRIPT="$REPO/ngts/scripts/allure_summary/sync_known_bugs.py"
OUT="${OUT:-/auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_baseline.json}"
DEVTS="${DEVTS:-$(dirname "$REPO")/devts}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "[$(ts)] sync_known_bugs.sh starting"

if [ -z "${REDMINE_API_TOKEN:-}" ]; then
    echo "[$(ts)] ERROR: REDMINE_API_TOKEN unset; aborting" >&2
    exit 1
fi

if [ ! -x "$PY" ]; then
    echo "[$(ts)] ERROR: $PY not executable; sonic-mgmt .venv missing?" >&2
    exit 1
fi

# Compute size of existing baseline (if any) so we can sanity-check the new one
PREV_SIZE=0
if [ -f "$OUT" ]; then
    PREV_SIZE=$(stat -c %s "$OUT")
fi

cd "$REPO"
PYPATH="$REPO"
if [ -d "$DEVTS" ]; then
    PYPATH="$REPO:$DEVTS"
fi
if ! PYTHONPATH="$PYPATH" "$PY" "$SCRIPT" --live --out "$OUT"; then
    echo "[$(ts)] ERROR: sync_known_bugs.py --live failed; previous baseline untouched" >&2
    exit 1
fi

NEW_SIZE=$(stat -c %s "$OUT")
BUGS=$($PY -c "import json; d=json.load(open('$OUT')); print(d['_meta']['ticket_count'])")

# Sanity: the file should be at least 100KB (smallest plausible baseline) and
# not shrink by more than 25% from one run to the next.
if [ "$NEW_SIZE" -lt 100000 ]; then
    echo "[$(ts)] ERROR: new baseline only ${NEW_SIZE} bytes; suspect corruption" >&2
    exit 1
fi
if [ "$PREV_SIZE" -gt 0 ]; then
    MIN=$((PREV_SIZE * 75 / 100))
    if [ "$NEW_SIZE" -lt "$MIN" ]; then
        echo "[$(ts)] WARNING: new baseline ${NEW_SIZE}B is <75% of previous ${PREV_SIZE}B"
    fi
fi

echo "[$(ts)] done: ${BUGS} bugs, ${NEW_SIZE} bytes -> $OUT"
