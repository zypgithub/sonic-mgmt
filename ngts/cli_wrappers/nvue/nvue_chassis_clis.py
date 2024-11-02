import re
from ngts.cli_wrappers.common.chassis_clis_common import ChassisCliCommon


class NvueChassisCli(ChassisCliCommon):
    """
    This class is for chassis cli commands for NVOS only
    """

    def __init__(self, engine):
        self.engine = engine

    def get_platform(self):
        """
        This method execute command "show platform summary" and return the dut platform type
        :return: the dut platform type
        """
        output = self.show_platform_summary()
        pattern = r"Platform:\s*(.*)"
        try:
            platform = re.search(pattern, output, re.IGNORECASE).group(1)
            return platform
        except Exception:
            raise AssertionError("Could not match platform type for switch {}".format(self.engine.ip))

    def show_platform_summary(self):
        """
        This method execute command "show platform summary" on dut
        :param engine: ssh engine object
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo show platform summary")

    def get_hostname(self):
        """
        This method is abstractmethod and should be implemented in child classes
        """
        pass

    def parse_platform_summary(self):
        """
        Parse the output of "show platform summary"
        :return: dict, example: {'HwSKU': 'ACS-MSN4410', 'ASIC Count': '1', 'ASIC': 'mellanox'...}
        """
        platform_summary_dict = {}
        platform_summary = self.show_platform_summary()
        for line in platform_summary.splitlines():
            split_line = line.split(": ")
            platform_summary_dict.update({split_line[0]: split_line[1]})
        return platform_summary_dict
