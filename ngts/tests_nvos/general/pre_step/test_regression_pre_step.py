import logging
import datetime as dt
from ngts.constants.constants import LinuxConsts
from ngts.helpers.secure_boot_helper import SecureBootHelper
from ngts.tools.test_utils import allure_utils as allure
import subprocess
import shlex
import os
import time
import pytest
from retry import retry
from devts.infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_tools.infra.DutUtilsTool import ping_device

logger = logging.getLogger()

REBOOT_CMD_TO_RUN = "ipmitool -I lanplus -H {server_name}-ilo -U root -P 3tango11 chassis power cycle"
SONIC_MGMT_HYPERVISOR = "fit-nvos-vrt-60"


@pytest.mark.no_cli_coverage_run
def test_regression_pre_step(engines, topology_obj):
    """
    Check that dut is reachable.
    If not, will reboot and try to recover
    """
    with allure.step(f"Verify DUT {engines.dut.ip} is reachable and functional"):
        if not ping_device(engines.dut.ip):
            res = remote_reboot_dut(topology_obj)
            if res:
                with allure.step("Try to ping dut after remote reboot"):
                    logging.info("Try to ping dut after remote reboot")
                    wait_till_dut_is_up(engines)
                    res = ping_device(engines.dut.ip)

            if not res:
                info = f"dut {engines.dut.ip} is unreachable"
                logging.info(info)

                with allure.step('Generate techsupport to investigate the problem'):
                    serial_engine = SecureBootHelper.get_serial_engine(topology_obj)
                    serial_engine.run_cmd('nv action generate system tech-support')

                # with allure.step('Try to resolve issue by fixing system time'):
                #     serial_engine = SecureBootHelper.get_serial_engine(topology_obj)
                #     serial_engine.run_cmd('nv unset system ; nv config apply -y')
                #     serial_engine.run_cmd('nv unset interface ; nv config apply -y')
                #     serial_engine.run_cmd(f'sudo timedatectl set-timezone {LinuxConsts.JERUSALEM_TIMEZONE}')
                #     serial_engine.run_cmd(
                #         f'sudo timedatectl set-time "{dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"')
                #     res = ping_device(engines.dut.ip)
                #     logging.info(f'dut {engines.dut.ip} is {"still un" if res else "now "}reachable')

        assert res, info


def remote_reboot_dut(topology_obj):
    with allure.step("Remote reboot DUT"):
        cmd = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['remote_reboot']
        cmd.replace('/auto', '/.autodirect')
        logging.info(f"Running cmd: {cmd}")
        p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            std_out, std_err = p.communicate(timeout=60)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            logger.debug('Process is not responding. Sending SIGKILL.')
            p.kill()
            std_out, std_err = p.communicate()
            rc = p.returncode
            std_out = str(std_out.decode('utf-8') or '')
            std_err = str(std_err.decode('utf-8') or '')
            logging.info(f"std_out = {std_out}, std_err = {std_err}")
        return rc == 0


def wait_till_dut_is_up(engines):
    with allure.step('Waiting for switch to bring-up after reload'):
        logger.info('Waiting for switch to bring-up after reload')
        check_port_status_till_alive(should_be_alive=True, destination_host=engines.dut.ip,
                                     destination_port=engines.dut.ssh_port)
