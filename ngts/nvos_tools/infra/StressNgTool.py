"""
Tool for installing, running and cleaning up stress-ng on Cumulus/DUT.
Used by system health and performance stress tests.
"""

from ngts.tools.test_utils import allure_utils as allure


class StressNgTool:
    """Install and cleanup stress-ng package on DUT (e.g. Cumulus)."""

    @staticmethod
    def install_stress_ng(engines_dut, install_bc: bool = False) -> None:
        """
        Install stress-ng (and optionally bc) and enable Debian repositories if needed.

        :param engines_dut: Engine for the DUT (e.g. engines.dut).
        :param install_bc: If True, also install the bc package.
        """
        with allure.step("Install stress-ng package"):
            engines_dut.run_cmd(
                "sudo sed -i 's/#deb     http:\\/\\/deb.debian.org\\/debian/deb     http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
            engines_dut.run_cmd(
                "sudo sed -i 's/#deb-src http:\\/\\/deb.debian.org\\/debian/deb-src http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
            engines_dut.run_cmd(
                "sudo sed -i 's/# deb     http:\\/\\/deb.debian.org\\/debian/deb     http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
            engines_dut.run_cmd(
                "sudo sed -i 's/# deb-src http:\\/\\/deb.debian.org\\/debian/deb-src http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
            engines_dut.run_cmd("sudo apt-get update -y --force-yes", timeout=300)
            engines_dut.run_cmd("sudo apt-get install -y --force-yes stress-ng", timeout=300)
            if install_bc:
                engines_dut.run_cmd("sudo apt-get install -y bc", timeout=300)

    @staticmethod
    def cleanup_stress_ng(engines_dut, remove_bc: bool = False) -> None:
        """
        Stop stress-ng, remove installed packages and restore Debian repositories.

        :param engines_dut: Engine for the DUT (e.g. engines.dut).
        :param remove_bc: If True, also remove the bc package.
        """
        with allure.step("Clean up stress-ng"):
            engines_dut.run_cmd("sudo killall stress-ng", timeout=300)
            engines_dut.run_cmd("sudo apt-get remove -y --force-yes stress-ng", timeout=300)
            if remove_bc:
                engines_dut.run_cmd("sudo apt-get remove -y bc", timeout=300)
            engines_dut.run_cmd(
                "sudo sed -i 's/deb     http:\\/\\/deb.debian.org\\/debian/#deb     http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
            engines_dut.run_cmd(
                "sudo sed -i 's/deb-src http:\\/\\/deb.debian.org\\/debian/#deb-src http:\\/\\/deb.debian.org\\/debian/g' /etc/apt/sources.list",
                timeout=30,
            )
