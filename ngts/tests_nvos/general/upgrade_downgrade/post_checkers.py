"""
System state verification module for NVOS.

This module provides a collection of checker functions that verify the system
state after various operations. Each checker focuses on a specific aspect
of the system such as network connectivity, interface status, system health, and more.

The checkers are designed to be run after a system transition to ensure that
the system is functioning correctly.
The module provides a decorator to specify which actions each checker should run for.

Usage:
* Adding a new checker:
    - create a new function with a decorator to specify which actions it should run for.
    - add the function to the _CHECKERS list.

* Running the checkers:
    ```python
        post_checkers.run_checkers(
            action=helpers.Action.UPGRADE,
            engines=engines,
            devices=devices,
            case=case,
            result_metadata=result_metadata
        )
    ```
"""

from typing import Callable, Dict, List, Any
from datetime import datetime
import functools
import logging
import json
import re
import os

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_constants.constants_nvos import HealthConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.ngts_types import EnginesT, DevicesT

from . import helpers

logger = logging.getLogger(__name__)
CheckerFn = Callable[..., None]


def _requires_action(*actions: helpers.Action):
    """ Decorator to skip checkers for certain actions. """
    def decorator(func: CheckerFn) -> CheckerFn:
        """ Decorator to skip checkers for certain actions. """
        @functools.wraps(func)
        def wrapper(action: helpers.Action, *args, **kwargs):
            """ Wrapper to skip checkers for certain actions. """
            if action in actions:
                return func(*args, action=action, **kwargs)
            logger.info(f"Skipping checker {func.__name__} for action {action}")
        return wrapper
    return decorator


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_ipv6(engines: EnginesT, devices: DevicesT, **kwargs) -> None:
    """Simple IPv6 connectivity test"""
    if not IpTool.is_dhcp_client6_has_lease(engines.dut):
        logger.warning("DHCP Client6 has no lease; cannot run this IPv6 test.")
        return

    with allure.step("Check IPv6 connectivity"):
        with allure.step("Check DHCP Client6 has lease"):
            port = Port(devices.dut.mgmt_ports[0])
            dhcp_client6 = port.interface.ip.dhcp_client6.parse_show()
            assert "yes" == dhcp_client6['has-lease'], "DHCP Client6 has no lease"

        with allure.step("Check IPv6 address"):
            ipv6_add = None
            for addr in port.interface.ip.address.parse_show():
                if "::" in addr:
                    ipv6_add = addr.split("/")[0]
                    break
            assert ipv6_add, "failed to get the ipv6 address"
            logging.info(f"ipv6 address: {ipv6_add}")

        with allure.step("Check IPv6 default routes"):
            routes = engines.dut.run_cmd("ip -6 route show default", validate=True)
            assert "default via" in routes, "No IPv6 default routes"

        with allure.step("Check IPv6 connectivity"):
            assert os.system(f"ping6 -c1 {ipv6_add}") == 0, "Failed to ping ipv6 address"


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_ipv4(engines: EnginesT, **kwargs) -> None:
    """Simple IPv4 connectivity test"""
    with allure.step("Check IPv4 connectivity"):
        engines.dut.run_cmd("ping -c1 8.8.8.8", validate=True)


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_eth0(**kwargs) -> None:
    """Simple eth0 interface test"""
    with allure.step("Check eth0 interface"):
        eth0 = Port('eth0')
        state = eth0.interface.link.parse_show('state')
        assert NvosConsts.LINK_STATE_UP in state, "eth0 interface is not up"


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_eth1(**kwargs) -> None:
    """Simple eth1 interface test"""
    with allure.step("Check eth1 interface"):
        eth1 = Port('eth1')
        state = eth1.interface.link.parse_show('state')
        assert NvosConsts.LINK_STATE_UP in state, "eth1 interface is not up"


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_system_health(**kwargs) -> None:
    with allure.step("Check system health"):
        health = System().health.parse_show()
        assert health['status'] == HealthConsts.OK, f"system health is not ok: {health}"


@_requires_action(helpers.Action.UPGRADE)
def _check_dockers(engines: EnginesT, **kwargs) -> None:
    with allure.step("Check dockers"):
        result: List[str] = engines.dut.run_cmd('docker ps --format "{{.Names}}"')
        found = set(re.findall("|".join(NvosConst.DOCKERS_LIST), result))
        assert found == set(NvosConst.DOCKERS_LIST), f"the following dockers are not running: {set(NvosConst.DOCKERS_LIST) - found}"


def _check_system_version(case: helpers.SystemVersionTransition, **kwargs) -> None:
    """
    Check that the system version is the same as the package nvos.
    """
    with allure.step("Check system version"):
        system_image = helpers.get_system_image()

        expected_versions = [case.base.nvos.name.replace("-amd64", "").replace(".bin", "")]
        if case.target:
            expected_versions.append(case.target.nvos.name.replace("-amd64", "").replace(".bin", ""))

        assert all(v in expected_versions for v in system_image), f"system version {system_image} is not equal to expected versions {expected_versions}"


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_reboot_reason(result_metadata: Dict[helpers.ResultMetadata, Any], **kwargs) -> None:
    """
    Check that the reboot reason is 'admin' and 'reboot'.
    """
    with allure.step("Check reboot reason"):
        system = System()
        output = system.reboot.reason.parse_show()
        assert 'admin' in output["user"], f"reboot user is not 'admin' as expected (actual - {output['user']})"

        expected_reason = "power cycle" if result_metadata.get(helpers.ResultMetadata.HAD_FW_UPDATE) else 'platform reset'
        assert output["reason"].lower() == expected_reason, f"reboot reason {output['reason']=!r} differ that expected reason: {expected_reason=!r}"


@_requires_action(helpers.Action.UPGRADE, helpers.Action.DOWNGRADE, helpers.Action.ROLLBACK)
def _check_curl(engines: EnginesT, **kwargs) -> None:
    """
    Simple curl test to verify API connectivity
    """
    with allure.step("Check curl"):
        curl_cmd = "curl -k -u admin:admin --request GET https://localhost/nvue_v1/system/version"
        curl_output = engines.dut.run_cmd(curl_cmd)
        curl_output = json.loads(curl_output)

    output = System().version.parse_show()
    assert curl_output == output, f"curl output {curl_output} is not equal to system version output {output}"


def _parse_timestamp(ts, current_year):
    try:
        return datetime.strptime(f"{current_year} {ts}", "%Y %b %d %H:%M:%S.%f")
    except ValueError:
        try:
            return datetime.strptime(f"{current_year} {ts}", "%Y %b %d %H:%M:%S")
        except ValueError:
            return None


@_requires_action(helpers.Action.DOWNGRADE)
def _check_ztp_server_active(engines: EnginesT, **kwargs) -> None:
    """Check if ZTP server was active during the most recent boot."""
    with allure.step("Check ZTP server active"):
        ztp: Dict[str, str] = System().ztp.parse_show()
        expected = {
            "state": ("enabled",),
            "service": ("active-discovery", 'enabled'),
            "runtime": "any",
        }
        diff = {
            k: f"found={ztp.get(k)} expected={values}"
            for k, values in expected.items()
            if k != "runtime" and ztp.get(k) in values
        }
        assert not diff, f"Mismatched keys: {diff}"


def run_checkers(*, action: helpers.Action, engines: EnginesT, devices: DevicesT, case: helpers.SystemVersionTransition,
                 result_metadata: Dict[helpers.ResultMetadata, Any]) -> List[helpers.Result]:
    """
    Run the checkers.

    Args:
        action: The action to perform.
        engines: The engines object.
        devices: The devices object.
        case: The case object.
        result_metadata: a dictionary of results metadata to be passed to the checkers.

    Returns:
        List[helpers.Result]: The list of results.
    """
    errors = []
    for checker in _CHECKERS:
        try:
            checker_name = checker.__name__
            if checker_name.startswith('_'):
                checker_name = checker_name[1:]

            with allure.step(f"Running checker: {checker_name}"):
                checker(action=action, engines=engines, devices=devices, case=case, result_metadata=result_metadata)
        except Exception as e:
            logger.error(e)
            errors.append(helpers.Result(ok=False, operation=checker_name, error_message=str(e)))
    return errors


_CHECKERS: List[CheckerFn] = [
    _check_ipv6,
    _check_ipv4,
    _check_eth0,
    _check_eth1,
    _check_system_health,
    _check_system_version,
    _check_reboot_reason,
    _check_curl,
    _check_dockers,
    _check_ztp_server_active,
]
