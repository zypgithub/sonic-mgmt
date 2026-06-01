"""NVOS Hub AI-investigation auto-queue.

On test failure, fire-and-forget POST to the dashboard's `/api/queue-failure`
endpoint so a deep investigation card is auto-generated. Success is signalled
via the runner log line `NVOS Hub accepted failure for AI investigation ...`.
After the Allure upload completes (in `pytest_terminal_summary`), POST the
final report URL to the dashboard's allure-url endpoint for each queued
failure so the entries get linked to the Allure run.

All work is best-effort — failures here never affect test outcome. The
feature is ON by default; pass `--no-nvos-hub-ai-investigation` (or set
env var `NVOS_HUB_AI_INVESTIGATION` to one of `0/false/no/off`) to opt out.
"""
import datetime
import json
import logging
import os
import threading
import urllib.error
import urllib.request

import pytest

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger(__name__)

NVOS_HUB_URL = 'http://10.237.230.30:8080'
NVOS_HUB_QUEUE_PATH = '/api/queue-failure'
# Bulk-ingest endpoint introduced in Phase 2 (one POST per pytest session
# after the Allure upload finishes, instead of one per failing test +
# follow-up URL POST). Called synchronously at pytest_terminal_summary
# so it completes before pytest exits — daemon threads can be cut on the
# very last hook tick.
NVOS_HUB_BULK_PATH = '/api/investigate-allure-report'
NVOS_HUB_BULK_TIMEOUT_SEC = 15.0
NVOS_HUB_TIMEOUT_SEC = 2.0
NVOS_HUB_PROBE_TIMEOUT_SEC = 1.5
NVOS_HUB_FAILURE_MSG_MAX = 2000

# Track queue-failure IDs created during this pytest session so a later
# pytest_terminal_summary can attach the Allure URL once it's known.
# MARS runs already have the setupName->canonical-project resolver covering
# them, but local pytest runs upload to ad-hoc project IDs that the resolver
# can't find — so we POST again at terminal_summary with the URL filled in.
_NVOS_HUB_POSTED_IDS = []

# Track tests that failed this session as a list of
# `{'test_name': str, 'nodeid': str}` dicts. Populated by the autouse
# fixture's teardown (same place that fires the legacy per-failure POST),
# duplicates dropped by nodeid (unique: module+func+params) to survive setup-fail
# plus call-fail double-fire. Drained by `terminal_summary_impl` into a
# single bulk POST to the Hub's /api/investigate-allure-report endpoint —
# that replaces both the 60s resolver polling on the Hub side AND the
# per-id allure-url follow-up POSTs here. Kept side-by-side with the
# legacy path during Phase 2 so we can A/B the two before deleting the
# old one in Phase 3.
_NVOS_HUB_FAILED_TESTS = []

# Session-scoped reachability cache: None=unchecked, True=up, False=down.
# Probed once on the first failure off the test thread; subsequent failures
# in the same session short-circuit when the Hub is known down, so we don't
# pay the 2s POST timeout per failing test.
_HUB_REACHABLE = None
_HUB_REACHABLE_LOCK = threading.Lock()


def _is_hub_reachable():
    """One-shot probe of the actual queue endpoint, cached for the session.

    GETs `NVOS_HUB_URL + NVOS_HUB_QUEUE_PATH` with a short timeout (this is
    the same endpoint the feature POSTs to, so probing it exercises the
    real network path rather than the SPA fallback at `/`). The result is
    cached on the first call and returned on subsequent calls.

    Classification:
      * 2xx response          -> reachable
      * any HTTPError (4xx/5xx) -> reachable (server responded; network is fine)
      * URLError / Timeout / OSError -> unreachable (cannot reach the host)

    Called from the daemon worker (never the test thread) so a slow probe
    cannot delay teardown.
    """
    global _HUB_REACHABLE
    if _HUB_REACHABLE is not None:
        return _HUB_REACHABLE
    with _HUB_REACHABLE_LOCK:
        if _HUB_REACHABLE is not None:
            return _HUB_REACHABLE
        probe_url = f'{NVOS_HUB_URL}{NVOS_HUB_QUEUE_PATH}'
        try:
            req = urllib.request.Request(probe_url, method='GET')
            with urllib.request.urlopen(req, timeout=NVOS_HUB_PROBE_TIMEOUT_SEC):
                _HUB_REACHABLE = True
                logger.info('NVOS Hub reachable at %s — failures will be queued for AI investigation',
                            probe_url)
        except urllib.error.HTTPError as e:
            # Server responded with a non-2xx; the network path is fine, so the
            # actual POST may still succeed (or fail loudly on its own).
            _HUB_REACHABLE = True
            logger.info('NVOS Hub responded at %s (HTTP %s) — failures will be queued',
                        probe_url, e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            _HUB_REACHABLE = False
            logger.warning('NVOS Hub unreachable at %s (%s) — failures will not be queued this session',
                           probe_url, e)
    return _HUB_REACHABLE


def is_enabled(config):
    """On by default. Off when --no-nvos-hub-ai-investigation is passed
    or when the NVOS_HUB_AI_INVESTIGATION env var is set to one of
    0/false/no/off. Any other value of the env var (including unset)
    leaves the feature on."""
    try:
        if config.getoption('--no-nvos-hub-ai-investigation', default=False):
            return False
    except (ValueError, AttributeError):
        pass
    return os.environ.get('NVOS_HUB_AI_INVESTIGATION', '').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )


def _post_queue_failure(payload):
    """Fire-and-forget POST to the NVOS Hub. Runs on a daemon thread; never raises.

    On success appends the assigned entry id to `_NVOS_HUB_POSTED_IDS` so
    pytest_terminal_summary can supply the Allure URL once it's known.
    """
    def _worker():
        if not _is_hub_reachable():
            return
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f'{NVOS_HUB_URL}{NVOS_HUB_QUEUE_PATH}',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=NVOS_HUB_TIMEOUT_SEC) as resp:
                body = resp.read().decode('utf-8', errors='replace')
                logger.info(
                    'NVOS Hub accepted failure for AI investigation (HTTP %s): test=%s — '
                    'investigation queued at %s',
                    resp.status, payload.get('test_name'), NVOS_HUB_URL,
                )
                try:
                    parsed = json.loads(body) if body else {}
                    entry_id = parsed.get('id')
                    if entry_id:
                        _NVOS_HUB_POSTED_IDS.append({
                            'id': entry_id,
                            'test_name': payload.get('test_name'),
                        })
                except Exception:
                    pass
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            logger.warning('NVOS Hub queue-failure unreachable (%s) — test outcome unaffected', e)

    threading.Thread(target=_worker, name='nvos-hub-queue-failure', daemon=True).start()


def _post_allure_url(entry_id, allure_url):
    """Set the Allure URL on a queue-failure entry after the upload completes.
    Used at pytest_terminal_summary to make local pytest runs work — without
    this the dashboard's setup->project resolver can't find the ad-hoc per-
    session project IDs that local runs upload to."""
    def _worker():
        if not _is_hub_reachable():
            return
        try:
            data = json.dumps({'allure_url': allure_url}).encode('utf-8')
            req = urllib.request.Request(
                f'{NVOS_HUB_URL}{NVOS_HUB_QUEUE_PATH}/{entry_id}/allure-url',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=NVOS_HUB_TIMEOUT_SEC) as resp:
                logger.info('NVOS Hub allure-url POST: HTTP %s for entry %s', resp.status, entry_id)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            logger.warning('NVOS Hub allure-url POST unreachable (%s) — test outcome unaffected', e)

    threading.Thread(target=_worker, name='nvos-hub-allure-url', daemon=True).start()


def _post_investigate_allure_report(config, report_url, failed_tests):
    """Phase-2 bulk POST. Synchronous (not threaded) because it runs in
    `pytest_terminal_summary` — the last hook before pytest exits, where
    daemon threads can be cut mid-request.

    The Hub endpoint walks the report's `suites.json` once to map each
    test name/nodeid -> uid, then per entry creates a QueuedFailure with
    the Allure URL already filled in and spawns the deep-investigation
    pipeline. Idempotent via cluster-key dedupe — re-posting the same
    report is a no-op.

    `failed_tests` is a list of `{'test_name': ..., 'nodeid': ...}`
    dicts. Both fields are sent so the Hub can disambiguate when the
    same function name exists in multiple modules (nodeid is unique;
    test_name is kept for older Hub builds that key by name).

    Failures here NEVER raise — pytest is finalizing, no test outcome
    can be affected, and the per-failure path is still in place.
    """
    if not _is_hub_reachable():
        return
    session_id = None
    try:
        session_id = config.getoption('--session_id', default=None)
    except (ValueError, AttributeError):
        pass
    runner = os.environ.get('USER') or None
    payload = {
        'allure_url': report_url,
        'failed_test_names': [t.get('test_name') for t in failed_tests if t.get('test_name')],
        'failed_node_ids': [t.get('nodeid') for t in failed_tests if t.get('nodeid')],
    }
    if session_id:
        payload['session_id'] = str(session_id)
    if runner:
        payload['runner'] = runner
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f'{NVOS_HUB_URL}{NVOS_HUB_BULK_PATH}',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=NVOS_HUB_BULK_TIMEOUT_SEC) as resp:
            body = resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        logger.warning('NVOS Hub bulk POST failed (%s) — test outcome unaffected', e)
        return

    # Response parsing/logging is best-effort: a malformed body (non-JSON,
    # non-dict, error entries that aren't dicts) must NEVER raise out of
    # this function, since the caller runs in pytest_terminal_summary
    # where an unhandled exception would break finalization.
    try:
        try:
            parsed = json.loads(body) if body else {}
        except (ValueError, TypeError):
            logger.debug('NVOS Hub bulk: non-JSON response body=%r', body[:200])
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        queued = parsed.get('queued') if isinstance(parsed.get('queued'), list) else []
        skipped = parsed.get('skipped') if isinstance(parsed.get('skipped'), list) else []
        missing = parsed.get('missing_names') if isinstance(parsed.get('missing_names'), list) else []
        errors = parsed.get('errors') if isinstance(parsed.get('errors'), list) else []
        logger.info(
            'NVOS Hub bulk investigation queued: %d test(s) accepted, '
            '%d skipped, %d missing-from-report, %d error(s) — report=%s',
            len(queued), len(skipped), len(missing), len(errors), report_url,
        )
        for e in errors:
            if isinstance(e, dict):
                logger.warning('NVOS Hub bulk: %s -> %s', e.get('test_name'), e.get('error'))
            else:
                logger.warning('NVOS Hub bulk: %s', e)
    except Exception as e:
        logger.debug('NVOS Hub bulk: response parse failed (%s) — ignored', e)


def terminal_summary_impl(config):
    """After Allure upload completes, POST the final report URL to each
    queued failure's allure-url endpoint (legacy path), AND fire the
    Phase-2 bulk POST so the Hub gets the whole session's failures in
    one shot with the URL already filled in. Cheap when there were no
    failures (early-out)."""
    if not is_enabled(config):
        return
    if not _NVOS_HUB_POSTED_IDS and not _NVOS_HUB_FAILED_TESTS:
        return
    try:
        from tests.common.plugins.allure_server import ALLURE_REPORT_URL
        report_url = config.cache.get(ALLURE_REPORT_URL, None)
    except Exception as e:
        logger.debug('NVOS Hub terminal_summary: could not read Allure cache: %s', e)
        return
    if not report_url:
        return
    # Legacy per-id allure-url POSTs. Kept side-by-side with the bulk call
    # during Phase 2 so we can A/B the two before retiring this path in
    # Phase 3. The cached URL is the base report (no #suites/_/<uid>/ fragment).
    # The dashboard's /allure-url handler tolerates that — it parses
    # project_id + report_id, then looks up the UID for each test in the
    # project's suites.json. We pass the same base URL for every entry of
    # this session.
    for entry in _NVOS_HUB_POSTED_IDS:
        _post_allure_url(entry['id'], report_url)

    # Phase-2 bulk POST: tells the Hub the report is up and which tests
    # failed, in one call. Hub spawns N deep investigations with URLs
    # already filled in (no resolver polling, no per-id follow-up).
    if _NVOS_HUB_FAILED_TESTS:
        _post_investigate_allure_report(config, report_url, _NVOS_HUB_FAILED_TESTS)


@pytest.fixture(autouse=True)
def nvos_hub_ai_investigation(request):
    """On test failure, queue an AI investigation in the NVOS Hub (dashboard).

    Fire-and-forget POST with short timeout — best-effort, never affects test
    outcome. On success the worker logs `NVOS Hub accepted failure for AI
    investigation ...` so the runner output makes it obvious the Hub picked
    up the failure and is working on it. Enabled by default; opt out with
    --no-nvos-hub-ai-investigation or NVOS_HUB_AI_INVESTIGATION=0.
    """
    yield

    if not is_enabled(request.config):
        return

    # Resolve phase reports defensively: rep_call is absent when the test
    # errors/skips in setup, so dereferencing it unguarded would itself
    # break the "best-effort" guarantee.
    rep_call = getattr(request.node, 'rep_call', None)
    rep_setup = getattr(request.node, 'rep_setup', None)

    setup_failed = rep_setup is not None and rep_setup.failed
    call_failed = rep_call is not None and rep_call.failed
    if not (setup_failed or call_failed):
        return  # passed, skipped, or no report — nothing to queue
    if rep_call is not None and getattr(rep_call, 'wasxfail', None) is not None:
        return  # xfail — expected to fail, don't queue

    session_id = request.config.getoption('--session_id', default=None)
    setup_name = request.config.getoption('--setup_name', default=None)
    test_name = request.node.name

    rep = rep_call if call_failed else rep_setup
    failure_msg = (getattr(rep, 'longreprtext', '') or str(getattr(rep, 'longrepr', '')))[:NVOS_HUB_FAILURE_MSG_MAX]

    payload = {
        'session_id': session_id,
        'setup_name': setup_name,
        'test_name': test_name,
        'nodeid': request.node.nodeid,
        'failure_msg': failure_msg,
        'branch': getattr(TestToolkit, 'branch', '') or '',
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    }
    _post_queue_failure(payload)

    # Stash for the Phase-2 bulk POST in `terminal_summary_impl`. Key the
    # dedupe on nodeid (globally unique: module path + function + params)
    # rather than test_name, which collides when the same function name
    # appears in different modules.
    nodeid = request.node.nodeid
    if not any(t.get('nodeid') == nodeid for t in _NVOS_HUB_FAILED_TESTS):
        _NVOS_HUB_FAILED_TESTS.append({
            'test_name': test_name,
            'nodeid': nodeid,
        })
