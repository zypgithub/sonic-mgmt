import logging
import pytest
import allure
import os
import time
from retry import retry

from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tools.test_utils.nvos_config_utils import set_base_configurations
from ngts.tests_nvos.conftest import devices

logger = logging.getLogger()

path_to_source_code = "/auto/sw_system_project/NVOS_INFRA/ChipSim/nvos/scripts"
chipsim_script_file_name = "run_nvos_in_chipsim.py"


def test_run_nvos_simx_docker(topology_obj, target_version, devices):
    dut_engine = topology_obj.players['dut']['engine']

    server_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['serial_conn_command'].split()[1]
    server_engine = ConnectionTool.create_ssh_conn(server_name, os.getenv("TEST_SERVER_USER"), os.getenv("TEST_SERVER_PASSWORD")).returned_value

    dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']

    with allure.step("Check existence of relevant files"):
        assert os.path.isdir(path_to_source_code), "Relevant script files can't be found in " + path_to_source_code

    with allure.step("Start the NVOS simx docker"):
        start_simx_docker(target_version, dut_engine, server_engine, devices)

    with allure.step("Wait until the switch is ready (~5 min)"):
        wait_till_the_switch_is_ready(dut_engine.ip)

    with allure.step("Wait until ssh is ready"):
        wait_till_ssh_is_ready(dut_engine)

    with allure.step("Apply basic config"):
        set_base_configurations(dut_engine=dut_engine, apply=True)


def start_simx_docker(target_version, dut_engine, server_engine, devices):
    cmd = f"sudo {path_to_source_code}/{chipsim_script_file_name} --ip {dut_engine.ip} --nos-image {target_version} "

    if devices.dut.switch_class == NvosConst.JULIET_SWITCH:
        cmd += ("--pelican-tag 2014_3104 --chipsim-version master-1.2.206 "
                "--docker-image nbu-harbor.gtm.nvidia.com/chipsim/master/ib:1.2.206")

    output = server_engine.run_cmd(cmd)

    time.sleep(5)
    assert "NOS installed successfully" in output, "Failed to start simx docker"


def wait_till_the_switch_is_ready(switch_ip):
    try:
        switch_is_ready = ConnectionTool.ping_device(switch_ip)
    except BaseException:
        raise Exception("Timeout during simx docker initiation")

    assert switch_is_ready, "Failed to initiate simx docker components"
    logging.info("All simx docker components are active")


@retry(Exception, tries=10, delay=5)
def wait_till_ssh_is_ready(dut_engine):
    dut_engine.run_cmd('nv show system version')
