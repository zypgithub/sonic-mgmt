"""
Per-test Allure attachment: Allure page URL → resolver server → JSON (optional).

Each test attaches HTML that (in the browser, inside the Allure report) calls
the hardcoded resolver base in
``analysis_attachments.ALLURE_JSON_RESOLVER_SERVER_BASE`` with the current Allure URL.
The attachment calls ``/resolve?allure_url=`` and renders returned JSON text. See
:func:`analysis_attachments.attach_json_resolved_by_allure_url`.

Attachments run from ``pytest_runtest_makereport`` when ``call.when == "teardown"`` (after the
teardown ``CallInfo`` is built), with ``trylast=True`` on the hookwrapper so the post-yield block
runs **after** other ``makereport`` wrappers (notably **allure-pytest** and ``tryfirst`` conftest
wrappers). Pluggy resumes hookwrappers in reverse yield order; without ``trylast``, this plugin
could attach while Allure’s reporter stack still matched the **call** phase, so the UI showed
attachments under **Test body** instead of **Teardown**.

Using ``pytest_runtest_teardown`` attached too early (before the teardown report), so Allure still
grouped files with the **call** phase.

**Failure analysis** (resolver JSON + formatted sections) and a separate **Cursor analysis prompt**
attachment (fixed top-right copy icon). Each time either attachment is opened, the iframe calls
``GET /resolve`` again (no stale read from ``sessionStorage`` on load).

The Failure analysis HTML again uses a tall ``min-height`` and viewport growth so the Allure iframe
is comfortable to read; only the **Exception analysis** collapsible uses tighter bottom spacing.

Skip for one test::

    @pytest.mark.no_allure_import_analysis
"""
from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)


def _config_getoption(config: pytest.Config, opt: str) -> str:
    """Return stripped CLI option value, or empty if missing / unknown."""
    try:
        v = config.getoption(opt, default=None)
    except ValueError:
        return ""
    if v is None:
        return ""
    s = str(v).strip()
    return s


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "no_allure_import_analysis: disable per-test Allure→JSON resolver attachment for this test",
    )


def attach_agent_analysis_for_node(node: pytest.Node, config: pytest.Config) -> None:
    """Perform Allure HTML + API-hint attachments for the given test node."""
    if node.get_closest_marker("no_allure_import_analysis"):
        return
    from . import analysis_attachments as aa

    try:
        aa.attach_json_resolved_by_allure_url(
            setup_name=_config_getoption(config, "--setup_name"),
            session_id=_config_getoption(config, "--session_id"),
            test_nodeid=node.nodeid,
        )
        aa.attach_cursor_prompt_html(node.nodeid)
    except Exception:
        logger.exception("Per-test analysis attachment failed for %s", node.nodeid)


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_makereport(item: pytest.Item, call) -> None:
    """Attach after teardown report; trylast so we run after allure-pytest's makereport wrapper."""
    yield
    if call.when != "teardown":
        return
    if not isinstance(item, pytest.Function):
        return
    try:
        attach_agent_analysis_for_node(item, item.config)
    except Exception:
        logger.exception("Per-test analysis attachment failed for %s", item.nodeid)
