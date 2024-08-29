import allure
import pytest
import time
import logging

pytestmark = [
    pytest.mark.topology('any')
]

logger = logging.getLogger(__name__)
snake_start_ip = "10.5.0.1"


def test_snake(duthost, configure_switches):

    last_vrf = configure_switches

    with allure.step("Install iperf"):
        duthost.command("sudo apt update")
        duthost.command("sudo apt install -y iperf3")

    with allure.step("check if the snake is pingable from end to start"):
        try:
            duthost.command(f"sudo ip vrf exec Vrf{last_vrf} ping -c 10 {snake_start_ip}")
        except Exception as err:
            logger.warning(f"ping failed error:{err}")
            logger.warning("try run traceroute to get more debug info")
            duthost.command(f"sudo ip vrf exec Vrf{last_vrf} traceroute {snake_start_ip}")

    with allure.step("Run iperf"):
        duthost.command(f"sudo ip vrf exec Vrf0 iperf3 -s -B {snake_start_ip} -D ", module_async=True)
        time.sleep(5)
        out = duthost.command(
            f"sudo ip vrf exec Vrf{last_vrf} iperf3 -t 60 -i 10 -c {snake_start_ip} --connect-timeout 5000")

        # Apply some objective constraints here for now just check success
        assert "Done" in out["stdout"]

