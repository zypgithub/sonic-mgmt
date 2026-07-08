#!/usr/bin/env python3
"""Weekly audit of the AI-maintained pairings cache.

For each cached pairing, cross-reference the Redmine bug's current status
(via the auto-baseline produced by sync_known_bugs.py --live) and drop
entries whose bug has been Closed / Resolved / Rejected. The next AI run
will re-derive a fresh attribution if those tests still fail.

Non-fatal: if the baseline is missing or unreadable, exits cleanly without
touching the cache. Designed to run from the nightly cron right after
sync_known_bugs.py finishes.

Usage:
    python audit_known_pairings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# Derive repo root from __file__ so this works under any user
# (developer / MARS / cron). Mirrors ai_attribute_report.py:62-64.
_REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
sys.path.insert(0, _REPO_ROOT)
from ngts.scripts.allure_summary.ai_attribute_report import (
    BASELINE_PATH, CACHE_PATH, load_cache, save_cache,
)

# Redmine statuses that mean the bug is no longer open. Same vocabulary as
# infra.tools.redmine.redmine_api.INACTIVE_STATES (kept local so we don't
# need the devts import path at audit time).
# Statuses that mean the bug is fully gone (fix shipped or duplicate of
# another ticket). Entries pointing at these are dropped from the cache.
INACTIVE_STATUSES = {
    "Closed", "Resolved", "Duplicate", "Verified", "Fixed",
}
# Rejected / Won't Fix / Cannot Reproduce are intentionally NOT in
# INACTIVE_STATUSES: when a failing test matches one of these, the dev
# team explicitly said "not a bug / work as designed", so the failure is
# usually a test or expectation issue that needs an update. We keep the
# cache entry and the matcher tags it with REJECTED_BUG_TAG so the meeting
# routes it to "update the test" instead of "wait for fix".


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be dropped without writing.")
    args = ap.parse_args()

    if not os.path.exists(BASELINE_PATH):
        print(f"WARN: baseline {BASELINE_PATH} missing; nothing to audit. Exiting.",
              file=sys.stderr)
        return 0

    try:
        with open(BASELINE_PATH) as fh:
            baseline = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: baseline unreadable: {exc}. Exiting.", file=sys.stderr)
        return 0

    # Build a status index from baseline. Any bug NOT in the baseline is
    # also stale - it dropped out of the saved query, which means closed.
    status_by_id = {}
    for bug in baseline.get("bugs", []) or []:
        status_by_id[bug.get("redmine_id")] = bug.get("status", "")

    cache = load_cache()
    before = len(cache.get("pairings", []))

    kept: list = []
    dropped: list = []
    for entry in cache.get("pairings", []) or []:
        rid = entry.get("redmine_id")
        status = status_by_id.get(rid)
        if status is None:
            dropped.append({"reason": "not in current baseline (dropped from saved query)",
                            "entry": entry})
            continue
        if status in INACTIVE_STATUSES:
            dropped.append({"reason": f"Redmine status={status!r}",
                            "entry": entry})
            continue
        kept.append(entry)

    cache["pairings"] = kept
    cache.setdefault("_meta", {})["last_audit"] = dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    cache["_meta"]["last_audit_dropped"] = len(dropped)

    print(f"audit: {before} -> {len(kept)} pairings; {len(dropped)} dropped")
    for d in dropped:
        e = d["entry"]
        print(f"  - drop #{e['redmine_id']} {e['test_name']:50s} "
              f"({d['reason']})")

    if args.dry_run:
        print("\n(dry-run, no write)")
        return 0
    save_cache(cache)
    print(f"\nwrote {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
