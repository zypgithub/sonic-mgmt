import os
import time
import logging
import pytest

logger = logging.getLogger(__name__)

TRACE_SCRIPT_LOCAL = os.path.join(os.path.dirname(__file__), "scripts", "trace_dropmon.sh")
TRACE_SCRIPT_REMOTE = "/tmp/trace_dropmon.sh"


@pytest.fixture(scope="module", autouse=True)
def trace_dropmon(request, duthost):
    if not request.module.__name__.endswith("test_wjh"):
        yield
        return

    duthost.copy(src=TRACE_SCRIPT_LOCAL, dest=TRACE_SCRIPT_REMOTE)
    duthost.shell(f"chmod +x {TRACE_SCRIPT_REMOTE}")
    duthost.shell("modprobe drop_monitor", module_ignore_errors=True)
    duthost.shell(f"nohup bash {TRACE_SCRIPT_REMOTE} > /tmp/trace_dropmon.out 2>&1 &")
    time.sleep(3)

    yield

    duthost.shell("pkill -f 'bpftrace.*dropmon' || true", module_ignore_errors=True)
    duthost.shell("pkill -f trace_dropmon.sh || true", module_ignore_errors=True)
