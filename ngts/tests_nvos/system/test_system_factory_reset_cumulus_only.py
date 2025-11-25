import base64
import random
import re
import time

import pytest
import logging

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.factory_reset.helpers import (KEEP_BASIC,
                                                          update_timezone,
                                                          validate_health_status_report,
                                                          verify_cleanup_done,
                                                          verify_the_setup_is_functional,
                                                          verify_services_status)
from ngts.tests_nvos.system.factory_reset.post_steps import factory_reset_system_message_post_steps
from ngts.tests_nvos.system.factory_reset.pre_steps import (factory_reset_general_pre_steps,
                                                            factory_reset_system_message_pre_steps)
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType, CumulusConsts
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli
from ngts.tests_nvos.system.aaa.helpers import create_new_user
from ngts.tests_nvos.helpers.general_helpers import run_ssh_cmd_with_rc

logger = logging.getLogger()

# Factory reset command run as a given user to check permission (SSIM3 test08-alike)
FACTORY_RESET_CMD = "nv action reset system factory-default force"
PERMISSION_DENIED_SUBSTRINGS = (
    "permission", "denied", "forbidden", "not allowed", "cannot", "error",
    "must be system-admin", "sudo access", "to reset system to factory",
    "unauthorized", "not authorized", "insufficient", "privilege", "rbac",
    "not permitted", "access denied", "failed", "invalid",
)


def verify_user_can_run_factory_reset(ip, username, password, port=22):
    """
    Run factory reset as the given user over SSH. Returns True if the user is allowed
    to run it (command accepted or device reboots), False if permission denied.
    Aligns with SSIM3 verify_user_permission_factory_reset.
    """
    result_obj = ConnectionTool.create_ssh_conn(ip, username, password, port=port)
    if not result_obj.result:
        logger.info("Could not connect as %s: %s", username, result_obj.info)
        return False
    conn = result_obj.get_returned_value()
    out = ""
    exit_code = 0
    try:
        out, exit_code = run_ssh_cmd_with_rc(conn, FACTORY_RESET_CMD)
        out = out or ""
    except Exception as e:
        # Connection drop (e.g. reboot) means command was accepted
        logger.info("Command as %s led to connection close: %s", username, e)
        return True
    finally:
        try:
            if hasattr(conn, "connection") and conn.connection:
                conn.connection.close()
        except Exception:
            pass
    out_lower = (out or "").lower()
    denied = any(s in out_lower for s in PERMISSION_DENIED_SUBSTRINGS)
    return not denied


def get_initial_yaml(engine):
    """Read initial.yaml from the DUT (Cumulus cue_config_v1)."""
    return engine.run_cmd("sudo cat /usr/lib/python3/dist-packages/cue_config_v1/initial.yaml")


def replace_hostname(data, old_content, new_content):
    """Replace whole-word old_content with new_content in data."""
    return re.sub(rf"\b{re.escape(old_content)}\b", new_content, data)


def write_yaml_to_system(engine, content, path):
    """Write content to path on the DUT (uses base64 to avoid shell escaping issues)."""
    b64 = base64.b64encode(content.encode()).decode()
    engine.run_cmd(f"echo '{b64}' | base64 -d | sudo tee {path} > /dev/null")


@pytest.mark.timeout(50 * MINUTE)
@pytest.mark.cumulus_only
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reset_factory_system_message(engines, devices, test_api, test_name, serial_log_analyzers):
    serial_analyzer, = serial_log_analyzers.values()
    TestToolkit.tested_api = test_api
    system = System()

    with allure.step('pre factory reset steps'):
        health_status, current_time, username = factory_reset_system_message_pre_steps(engines, devices, system)

    with allure.step("Run reset factory with system message params"):
        with serial_analyzer.stage('Reset-factory'):
            duration = execute_reset_factory(engines, devices, system, devices.dut.reset_factory, "keep basic", current_time, test_name=test_name)

    with allure.step('post factory reset system message steps'):
        factory_reset_system_message_post_steps(engines, devices, system)

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)


@pytest.mark.cumulus_only
@pytest.mark.system
@pytest.mark.checklist
def test_reset_factory_after_service_restart(engines, devices, topology_obj, test_name):
    """
    This test is for test
    Test flow:
        1. Restart services
        2. Run reset factory after service restart
        3. Verify the setup is functional
        4. Verify the cleanup done successfully
        5. Verify the services are active and running
        6. Verify the setup is functional
    """
    services = ['frr', 'syslog', 'switchd']
    with allure.step('Create System object'):
        system = System()
    with allure.step('pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, username = factory_reset_general_pre_steps(engines, devices, system)
    with allure.step("Restart services"):
        for service in services:
            logging.info('Restarting service {0}'.format(service))
            engines.dut.run_cmd(f"sudo systemctl restart {service}")
            time.sleep(30)
        verify_services_status(engines, services)

    with allure.step("Run reset factory after service restart"):
        duration = execute_reset_factory(engines, devices, system, devices.dut.reset_factory, "", current_time, test_name=test_name)

    update_timezone(system)

    with allure.step("Validate health status and report"):
        validate_health_status_report(system, health_status)

    with allure.step("Verify the services are active and running"):
        services = ['nvued.service', 'nginx-authenticator.service', 'switchd.service', 'frr', 'syslog', 'switchd']
        verify_services_status(engines, services)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param="")

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)


@pytest.mark.cumulus_only
@pytest.mark.system
@pytest.mark.checklist
def test_reset_factory_without_nvue(engines, devices, test_name):
    """
    Validate reset factory without nvue
    """
    with allure.step('Create System object'):
        system = System()

    with allure.step('pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, username = factory_reset_general_pre_steps(engines, devices, system)

    with allure.step("Run reset factory without nvue"):
        # Verify "nv action reset system factory-default" functionality
        engines.dut.run_cmd('sudo systemctl reset-failed')
        engines.dut.run_cmd("nohup sudo systemctl restart factory-reset.service > /dev/null 2>&1 &")
        logging.info("Waiting for factory-reset.service to restart to complete")
        time.sleep(240)

    with allure.step('wait for os to be functional'):
        devices.dut.wait_for_os_to_become_functional(engines.dut)
        devices.dut.post_reload_actions(engines.dut)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param="")

    update_timezone(system)
    with allure.step("Verify the setup is operational"):
        verify_the_setup_is_functional(system, engines)


@pytest.mark.cumulus_only
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_factory_reset_default_non_auth_users(engines, devices, test_name, test_api):
    """
    Validate that nvue-monitor and nvue-admin cannot run factory reset (requires system-admin/root/sudo).
    Then run factory reset via the test framework (cumulus/sudo) and verify reboot and cleanup.
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System object'):
        system = System()

    with allure.step('Pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, pre_username = factory_reset_general_pre_steps(engines, devices, system)

    with allure.step('Add users: nvue-admin (user1) and nvue-monitor (user2)'):
        user1_name, user1_pass = create_new_user(role=CumulusConsts.ROLE_NVUE_ADMIN, apply=True)
        user2_name, user2_pass = create_new_user(role=CumulusConsts.ROLE_NVUE_MONITOR, apply=True)

    with allure.step('Verify user2 (nvue-monitor) cannot execute factory reset'):
        can_run = verify_user_can_run_factory_reset(engines.dut.ip, user2_name, user2_pass)
        assert not can_run, "nvue-monitor user must not be able to run factory reset"
    with allure.step('Verify user1 (nvue-admin) cannot execute factory reset'):
        can_run = verify_user_can_run_factory_reset(engines.dut.ip, user1_name, user1_pass)
        assert not can_run, "nvue-admin user must not be able to run factory reset"

    with allure.step("Run reset factory with keep basic flag cumulus user"):
        duration = execute_reset_factory(engines, devices, system, devices.dut.reset_factory, "", current_time, test_name=test_name)

    update_timezone(system)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, pre_username, param="")

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)


@pytest.mark.cumulus_only
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.parametrize('test_api', ['NVUE'])
def test_factory_reset_modified_initial_yaml(engines, devices, test_name, test_api):
    """
    Validate factory reset modified initial yaml
    """
    TestToolkit.tested_api = test_api
    with allure.step('Create System object'):
        system = System()

    with allure.step("Getting hostname"):
        hostname = engines.dut.run_cmd('hostname')
        logger.info(f"Hostname: {hostname}")
    with allure.step("Getting initial YAML configuration"):
        data_list = get_initial_yaml(engines.dut)
        logger.info(data_list)

    with allure.step('pre factory reset steps'):
        health_status, current_time, apply_and_save_port, description, just_apply_port, \
            not_apply_port, username = factory_reset_general_pre_steps(engines, devices, system)

    with allure.step("Modifying initial YAML hostname"):
        old_hostname = f'hostname: {hostname}'
        new_hostname = 'hostname: cumulus1'
        # rewrite initial.yaml file with new hostname cumulus1
        new_init = replace_hostname(data_list, old_content=old_hostname, new_content=new_hostname)
        # write_initial_yaml(engines.dut, new_init)
        write_yaml_to_system(engines.dut, new_init, "/usr/lib/python3/dist-packages/cue_config_v1/initial.yaml")
    with allure.step("Verifying modified initial YAML"):
        out = get_initial_yaml(engines.dut)
        logger.info(out)

    with allure.step("Run reset factory modified initial yaml"):
        duration = execute_reset_factory(engines, devices, system, devices.dut.reset_factory, "", current_time, test_name=test_name)
    update_timezone(system)

    with allure.step("Verify the cleanup done successfully"):
        verify_cleanup_done(engines.dut, current_time, system, username, param="")

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)

    with allure.step("Verify the hostname is changed after the reset factory"):
        out = engines.dut.run_cmd("hostname")
        logger.info(f"Hostname details: {out}")
        hostname = (out or "").strip()
        assert hostname == "cumulus", (
            f"hostname_verification FAILED: expected short hostname 'cumulus', got {hostname}"
        )


def execute_reset_factory(engines, devices, system, operation, flag, current_time, topology_obj=None, test_name=''):
    logging.info("Current time: " + str(current_time))
    topology_obj = topology_obj or (TestToolkit.topology_obj if TestToolkit else None)
    result_obj = system.factory_default.action_reset(operation=operation, param=flag, topology_obj=topology_obj, test_name=test_name)
    result_obj.verify_result()
    return result_obj.duration
