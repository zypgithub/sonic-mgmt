"""
Shared resolver URLs, paths, and helpers for pytest client stubs.

Lives under ``tests/common/plugins/allure_wrapper/ai_rca/`` (sonic-mgmt production).
The resolver server deploy script copies this file next to server code on rm-via-allure.
"""
import hashlib
import json
import os

ALLURE_JSON_RESOLVER_SERVER_BASE = "https://rm-via-allure.nvidia.com:9999"
ALLURE_JSON_RESOLVER_RESOLVE_PATH = "/resolve"

# Synthetic Allure URL when ALLURE_ATTACHMENT_DEMO=1 (browser skips window.top).
ALLURE_DEMO_ALLURE_URL = "http://demo/allure/local"

ALLURE_ANALYSIS_FEEDBACK_PATH = "/analysis_feedback"
ALLURE_ATTACHMENT_FAILURE_PATH = "/attachment/failure"
ALLURE_ATTACHMENT_CURSOR_PATH = "/attachment/cursor"

ALLURE_BUG_REPORT_POST_DEFAULT = "https://rm-via-allure.nvidia.com:8443/"

CURSOR_PROMPT_STORAGE_KEY = "sonic_mgmt_cursor_prompt_plain"
RESOLVER_RESULT_STORAGE_PREFIX = "sonic_mgmt_resolve_result"


def cursor_prompt_session_storage_key(test_nodeid=None):
    dig = hashlib.sha256((test_nodeid or "").encode("utf-8", errors="replace")).hexdigest()[:24]
    return "{}:{}".format(CURSOR_PROMPT_STORAGE_KEY, dig)


def resolver_result_session_storage_key(test_nodeid=None):
    dig = hashlib.sha256((test_nodeid or "").encode("utf-8", errors="replace")).hexdigest()[:24]
    return "{}:{}".format(RESOLVER_RESULT_STORAGE_PREFIX, dig)


def _resolver_base_for_attach():
    override = (os.environ.get("ALLURE_JSON_RESOLVER_SERVER_BASE") or "").strip()
    return (override or ALLURE_JSON_RESOLVER_SERVER_BASE).rstrip("/")


def get_resolver_server_base():
    """JavaScript string literal for resolver base (for ``<script>`` embed)."""
    return json.dumps(_resolver_base_for_attach())


def get_feedback_path():
    """JavaScript string literal for feedback POST path."""
    return json.dumps(ALLURE_ANALYSIS_FEEDBACK_PATH)


def get_bug_report_post_url():
    override = (os.environ.get("ALLURE_BUG_REPORT_POST_URL") or "").strip()
    url = override or ALLURE_BUG_REPORT_POST_DEFAULT
    if not url.endswith("/"):
        url += "/"
    return url
