import logging
import pytest

from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.tools.test_utils import allure_utils as allure
import subprocess

logger = logging.getLogger()


@pytest.mark.platform
def test_checklist_ipv6(engines):
    """
    ipv6

    - ping
    - ssh connection
    - openapi
    """
    if not IpTool.is_dhcp_client6_has_lease(engines.dut):
        pytest.skip("DUT DHCP client6 has no lease; cannot run this IPv6 test.")

    try:
        with allure.step("Get ipv6 address for switch " + engines.dut.ip):
            logging.info("Running 'nv show interface eth0 ip address'")
            output = engines.dut.run_cmd("nv show interface eth0 ip address")
            assert output, "The output is empty"
            addresses = output.split()
            assert len(addresses) >= 4, "The output is invalid"
            for add in addresses:
                if "::" in add:
                    ipv6_add = add.split("/")[0]
                    break
            assert ipv6_add, "failed to get the ipv6 address"
            logging.info("ipv6 address: " + ipv6_add)

        with allure.step("Verify ping to ipv6 address " + ipv6_add):
            logging.info("Verify ping to ipv6 address " + ipv6_add)
            ping_switch(ipv6_add)

        with allure.step("Verify ssh connection using ipv6 address " + ipv6_add):
            logging.info("Verify ssh connection using ipv6 address " + ipv6_add)
            _check_ssh_connection(ipv6_add, engines.dut.username, engines.dut.password)

        with allure.step("Verify OpenApi command using ipv6 address " + ipv6_add):
            logging.info("Verify OpenApi command using ipv6 address " + ipv6_add)
            _send_open_api_request(ipv6_add, engines.dut)

    except BaseException as ex:
        ExceptionTool.log_traceback()
        raise AssertionError(str(ex))


def ping_switch(ipv6_add):
    try:
        cmd = "ping6 -c 3 {}".format(ipv6_add)
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()
        logging.info("output: " + str(output))
        logging.info("error: " + str(error))
        if "0% packet loss" in str(output):
            logging.info("Reachable using ipv6 address: " + ipv6_add)
        if error:
            logging.error("Unreachable using ipv6 address: " + ipv6_add)
            raise Exception("ipv6 address is unreachable")

        assert output, "Failed to ping ipv6 address " + ipv6_add
    except BaseException as ex:
        logging.error(str(ex))
        assert "ipv6 address is unreachable"


def _check_ssh_connection(ipv6_add, username, password):
    try:
        cmd = "sshpass -p '{password}' -v ssh -6 -o StrictHostKeyChecking=no  {username}@{ip}".format(
            password=password, username=username, ip=ipv6_add)
        logging.info("cmd: " + cmd)
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()
        logging.info("output: " + str(output))
        logging.info("error: " + str(error))
        if error:
            logging.error("SSH is unreachable using ipv6 address: " + ipv6_add)
            raise Exception("SSH to Ipv6 address is unreachable")
        logging.info("SSH is reachable using ipv6 address: " + ipv6_add)
    except BaseException as ex:
        logging.error(str(ex))
        assert "SSH connection using ipv6 was failed"


def _send_open_api_request(ipv6_add, dut_engine):
    try:
        url = "curl -k -g -6 -u {user_name}:{password} --request GET https://[{ipv6_add}]/nvue_v1/system/version".format(
            user_name=dut_engine.username, password=dut_engine.password, ipv6_add=ipv6_add)
        logging.info("url: " + url)
        output = dut_engine.run_cmd(url)
        assert "build-date" in output and "image" in output, "API request failed using ipv6 address"
    except BaseException as ex:
        logging.error(str(ex))
        assert "API request failed using ipv6 address"
