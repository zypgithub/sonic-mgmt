# Demo-only: loads the per-test Allure analysis plugin without importing ``tests/conftest.py``.
# Run from the ``sonic-mgmt`` repo root with ``--confcutdir`` set to this directory.
from __future__ import annotations

import os
import sys
import types

import pytest

_demo_dir = os.path.dirname(os.path.abspath(__file__))

_repo_root = _demo_dir
for _ in range(12):
    if os.path.isdir(os.path.join(_repo_root, "tests", "common")):
        break
    parent = os.path.dirname(_repo_root)
    if parent == _repo_root:
        raise RuntimeError(
            f"Could not find sonic-mgmt repo root from demo dir: {_demo_dir}"
        )
    _repo_root = parent


def _ensure_lightweight_tests_common() -> None:
    m = sys.modules.get("tests.common")
    if m is not None and getattr(m, "__file__", None):
        return
    pkg = types.ModuleType("tests.common")
    pkg.__path__ = [os.path.join(_repo_root, "tests", "common")]
    sys.modules["tests.common"] = pkg


_ensure_lightweight_tests_common()

pytest_plugins = ("tests.common.plugins.allure_wrapper.ai_rca.per_test_analysis_attachment",)


def pytest_configure(config: pytest.Config) -> None:
    # Demo stubs add demo=1; HTML + /resolve are served by ALLURE_JSON_RESOLVER_SERVER_BASE
    # (default https://rm-via-allure.nvidia.com:9999). Override that env var for a local resolver.
    os.environ.setdefault("ALLURE_ATTACHMENT_DEMO", "1")
