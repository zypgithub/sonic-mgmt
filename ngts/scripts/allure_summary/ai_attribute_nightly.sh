#!/bin/bash
# Nightly MARS wrapper for ai_attribute_report.py.
#
# Reads the just-generated Allure URL from the standard verification_files
# location and runs the AI agent against it with production settings
# (--loose --feedback). Non-fatal: exits 0 on any failure so MARS does
# not break the regression.
#
# The MARS step passes the bare setup name (e.g. NVOS_bm_10_7_148_150).
# allure_reporter.py stores the URL under
#   nvos-bm-10-7-148-150-session-reports.txt
# (lowercase + underscores->dashes + suffix). This wrapper does that
# conversion to find the URL file.
#
# Canonical install location (what MARS invokes):
#   /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_attribute_nightly.sh
# A copy lives in the repo at
#   ngts/scripts/allure_summary/ai_attribute_nightly.sh
# for recovery / source-of-truth. Edits should go to the repo copy and be
# re-deployed to the shared location.
#
# Usage (MARS step):
#   /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_attribute_nightly.sh <setup_name>
#
# Optional env overrides (defaults shown):
#   REPO_ROOT  - sonic-mgmt checkout. Defaults to the repo containing this
#                script if it looks like a sonic-mgmt tree, otherwise falls
#                back to /root/mars/workspace/sonic-mgmt (the MARS path).
#   PY         - python interpreter (defaults to /ngts_venv/bin/python on
#                MARS players, falls back to $REPO_ROOT/.venv/bin/python)
#   DEVTS      - devts checkout added to PYTHONPATH if it exists. Defaults
#                to /devts; silently skipped when absent.
#   FEEDBACK   - ai_feedback.json path (shared NVOS_INFRA location by default)
#   CACHE      - ai_known_pairings.json path (shared NVOS_INFRA location by default)

set -u

SETUP="${1:?setup name required}"
SHARED_URLS=/auto/sw_system_project/NVOS_INFRA/verification_files

# Resolve REPO_ROOT: derive from script location if it looks like a sonic-mgmt
# checkout (so the in-repo recovery copy "just works" during testing), else
# fall back to the MARS canonical path.
_self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_derived_repo="$(cd "$_self_dir/../../.." 2>/dev/null && pwd || true)"
if [ -n "$_derived_repo" ] && [ -f "$_derived_repo/ngts/scripts/allure_summary/ai_attribute_report.py" ]; then
    REPO_ROOT="${REPO_ROOT:-$_derived_repo}"
else
    REPO_ROOT="${REPO_ROOT:-/root/mars/workspace/sonic-mgmt}"
fi

# Pick python: explicit env override, then MARS venv, then repo .venv.
if [ -z "${PY:-}" ]; then
    if [ -x /ngts_venv/bin/python ]; then
        PY=/ngts_venv/bin/python
    elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        PY="$REPO_ROOT/.venv/bin/python"
    else
        PY=/ngts_venv/bin/python  # report the canonical path in the error below
    fi
fi

DEVTS="${DEVTS:-/devts}"
FEEDBACK="${FEEDBACK:-/auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_feedback.json}"
CACHE="${CACHE:-/auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_known_pairings.json}"

# Convert MARS setup name -> Allure project id (same convention as
# allure_reporter.py:195).
PROJECT_BASE=$(echo "$SETUP" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

echo "========================================================================"
echo "ai_attribute_nightly: starting"
echo "  setup name      : $SETUP"
echo "  allure project  : ${PROJECT_BASE}-session-reports  (derived)"
echo "  feedback file   : $FEEDBACK"
echo "  cache file      : $CACHE"
echo "========================================================================"

# Sanity: required files exist?
for f in "$FEEDBACK" "$CACHE"; do
    if [ ! -f "$f" ]; then
        echo "WARN: $f missing - agent may bootstrap fresh"
    fi
done

# Locate the URL file. Try the -session-reports suffix first (canonical for
# full regressions) then the bare project name (older / one-off runs).
URL_FILE="${SHARED_URLS}/${PROJECT_BASE}-session-reports.txt"
if [ ! -f "$URL_FILE" ]; then
    URL_FILE_ALT="${SHARED_URLS}/${PROJECT_BASE}.txt"
    echo "  url file (try1) : $URL_FILE  -> missing"
    if [ ! -f "$URL_FILE_ALT" ]; then
        echo "  url file (try2) : $URL_FILE_ALT  -> also missing"
        echo ""
        echo "ai_attribute_nightly: no Allure URL file found for setup '$SETUP'"
        echo "  expected at one of:"
        echo "    ${URL_FILE}"
        echo "    ${URL_FILE_ALT}"
        echo "  (this typically means the 'Generate final Allure report' step"
        echo "  before this one did not run or did not produce a URL.)"
        echo "  skipping AI attribution; not breaking the regression."
        exit 0
    fi
    URL_FILE="$URL_FILE_ALT"
fi

URL=$(head -1 "$URL_FILE" | tr -d '\r\n ')
if [ -z "$URL" ]; then
    echo "ai_attribute_nightly: URL file empty ($URL_FILE); skipping"
    exit 0
fi

echo "  url file        : $URL_FILE"
echo "  url             : $URL"
echo ""

# Required env
if [ -z "${INFERENCE_HUB_API_KEY:-}" ]; then
    echo "ai_attribute_nightly: INFERENCE_HUB_API_KEY unset; skipping"
    exit 0
fi

if [ ! -x "$PY" ]; then
    echo "ai_attribute_nightly: $PY not executable; skipping"
    exit 0
fi

# Show cache state before
if [ -f "$CACHE" ]; then
    BEFORE=$($PY -c "import json; print(len(json.load(open('$CACHE')).get('pairings', [])))" 2>/dev/null || echo "?")
    echo "  cache entries (before): $BEFORE"
fi

echo ""
echo "------------------------- agent stdout ---------------------------------"
cd "$REPO_ROOT"
PYPATH="$REPO_ROOT"
if [ -d "$DEVTS" ]; then
    PYPATH="$REPO_ROOT:$DEVTS"
fi
PYTHONPATH="$PYPATH" "$PY" \
    ngts/scripts/allure_summary/ai_attribute_report.py \
    "$URL" \
    --loose \
    --feedback "$FEEDBACK" \
    --variant nightly
AGENT_RC=$?
echo "------------------------- agent stdout end -----------------------------"
echo ""

if [ "$AGENT_RC" -ne 0 ]; then
    echo "ai_attribute_nightly: agent exited rc=$AGENT_RC (non-fatal)"
fi

# Show cache state after
if [ -f "$CACHE" ]; then
    AFTER=$($PY -c "import json; print(len(json.load(open('$CACHE')).get('pairings', [])))" 2>/dev/null || echo "?")
    echo "  cache entries (after) : $AFTER"
fi

# Find and surface the just-written session JSON (the agent prints its path
# already, but echo it again here so the MARS log has a clear pointer).
LATEST_SESSION=$(ls -1t /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_session_${PROJECT_BASE}*_nightly_*.json 2>/dev/null | head -1)
if [ -n "$LATEST_SESSION" ]; then
    echo "  session report  : $LATEST_SESSION"
    # Quick summary from session JSON
    SUMMARY=$($PY -c "
import json
d = json.load(open('$LATEST_SESSION'))
n_picks = sum(1 for e in d['audit'] if e['verdict'].get('redmine_id'))
n_refuse = sum(1 for e in d['audit'] if e['verdict'].get('redmine_id') is None and e['verdict'].get('reason') != 'no candidates from baseline')
n_nocand = sum(1 for e in d['audit'] if e['verdict'].get('reason') == 'no candidates from baseline')
n_amb = len(d.get('ambiguities_for_review', []))
print(f'  attributions    : {n_picks} picks / {n_refuse} refused / {n_nocand} no-candidates')
print(f'  ambiguities     : {n_amb} flagged for human review')
" 2>/dev/null)
    [ -n "$SUMMARY" ] && echo "$SUMMARY"
fi

echo "========================================================================"
echo "ai_attribute_nightly: done"
echo "========================================================================"

exit 0
