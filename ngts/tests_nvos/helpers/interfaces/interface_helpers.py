import time

from ngts.nvos_tools.ib.InterfaceConfiguration import Port, nvos_consts as ib_consts
from ngts.tests_nvos.interfaces.nvl_port import helpers as nvl_port_helpers
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active


ARE_BUGS_ACTIVE: bool = (
    is_bug_active(5034554) or
    is_bug_active(5041195) or
    is_bug_active(5044735) or
    True  # TODO: remove when is_bug_active works
)


def wait_and_verify_link(
    ports: list[Port.Port],
    timeout: int,
) -> None:
    if ARE_BUGS_ACTIVE:
        src_timeout = timeout
        timeout *= 2
    port_names: list[str] = [port.name for port in ports]
    with allure.step(f"Wait for port state to be up on ports {port_names} (timeout={timeout}s)"):
        for port in ports:
            port.interface.wait_for_port_state(
                ib_consts.NvosConsts.LINK_STATE_UP, timeout=timeout,
            ).verify_result()
    if ARE_BUGS_ACTIVE:
        time.sleep(src_timeout)
    with allure.step(f"Verify link diagnostics on ports {port_names}"):
        nvl_port_helpers.verify_link_diagnostic(ports)
