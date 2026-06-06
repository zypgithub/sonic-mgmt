"""
Demo: one passing test so ``pytest_runtest_teardown`` in ``per_test_analysis_attachment`` runs and
Allure records attachments.

Uses the **production** resolver (``https://rm-via-allure.nvidia.com:9999``) by default.

Run from ``sonic-mgmt`` root::

    cd sonic-mgmt
    python3 -m pytest ngts/scripts/ai_rca/demo/ \\
        --confcutdir=ngts/scripts/ai_rca/demo \\
        --alluredir=/tmp/allure-demo-agent-analysis -q

    allure serve /tmp/allure-demo-agent-analysis

Local resolver (optional)::

    RESOLVE_DEV_HTTP=1 RESOLVE_MOCK=1 python3 -u ngts/scripts/ai_rca/server_side/allure_resolver_server.py

In the browser: open the test → **Tear down** → **Failure analysis** / **Cursor analysis prompt**.
"""


def test_demo_allure_agent_analysis_attachments():
    assert True
