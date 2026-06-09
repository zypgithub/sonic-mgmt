"""
Render Allure attachment HTML from on-disk templates (served by resolver).
"""
import html
import json
from pathlib import Path
from typing import Dict, Optional

from embedded_rm_modal_loader import build_rm_modal_bundle_js, escape_for_inline_script
from resolver_contract import (
    ALLURE_ANALYSIS_FEEDBACK_PATH,
    ALLURE_JSON_RESOLVER_RESOLVE_PATH,
    cursor_prompt_session_storage_key,
    get_bug_report_post_url,
    get_feedback_path,
    get_resolver_server_base,
    resolver_result_session_storage_key,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_RM_INJECT_STMT = None


def _read_template(name):
    path = _TEMPLATES_DIR / name
    if not path.is_file():
        raise FileNotFoundError("attachment template missing: {}".format(path))
    return path.read_text(encoding="utf-8")


def _apply_placeholders(template, mapping):
    out = template
    for key, value in mapping.items():
        out = out.replace(key, value)
    return out


def get_rm_inject_stmt():
    global _RM_INJECT_STMT
    if _RM_INJECT_STMT is None:
        raw = escape_for_inline_script(build_rm_modal_bundle_js())
        stmt = "s.textContent = " + json.dumps(raw) + ";"
        _RM_INJECT_STMT = stmt.replace("</script>", "<\\/script>")
    return _RM_INJECT_STMT


def render_failure_analysis_html(
    title="Failure analysis",
    setup_name="",
    session_id="",
    test_nodeid="",
    demo=False,
):
    template = _read_template("failure_analysis.html")
    mapping = {
        "__TITLE__": html.escape(title, quote=True),
        "__JS_BASE__": get_resolver_server_base(),
        "__JS_DEMO_MODE__": "true" if demo else "false",
        "__JS_RESOLVE_PATH__": json.dumps(ALLURE_JSON_RESOLVER_RESOLVE_PATH),
        "__JS_BUG_POST_URL__": json.dumps(get_bug_report_post_url()),
        "__JS_FEEDBACK_PATH__": get_feedback_path(),
        "__JS_SETUP__": json.dumps((setup_name or "").strip()),
        "__JS_SESSION__": json.dumps((session_id or "").strip()),
        "__JS_NODEID__": json.dumps((test_nodeid or "").strip()),
        "__JS_BUNDLE_KEY__": json.dumps(resolver_result_session_storage_key(test_nodeid)),
        "___SONIC_MGMT_RM_INJECT_STMT___": get_rm_inject_stmt(),
    }
    return _apply_placeholders(template, mapping)


def render_cursor_prompt_html(
    title="Cursor analysis prompt",
    test_nodeid="",
    probe_test_name="",
    demo=False,
):
    template = _read_template("cursor_prompt.html")
    load_msg = json.dumps("Loading analysis from resolver…")
    mapping = {
        "__TITLE__": html.escape(title, quote=True),
        "__JS_DEMO_MODE__": "true" if demo else "false",
        "__JS_CURSOR_KEY__": json.dumps(cursor_prompt_session_storage_key(test_nodeid)),
        "__JS_BUNDLE_KEY__": json.dumps(resolver_result_session_storage_key(test_nodeid)),
        "__JS_LOAD_MSG__": load_msg,
        "__JS_BASE__": get_resolver_server_base(),
        "__JS_RESOLVE_PATH__": json.dumps(ALLURE_JSON_RESOLVER_RESOLVE_PATH),
        "__JS_NODEID__": json.dumps((test_nodeid or "").strip()),
        "__JS_TEST_NAME__": json.dumps((probe_test_name or "").strip()),
    }
    return _apply_placeholders(template, mapping)
