import re
import logging
from ngts.cli_wrappers.common.chassis_clis_common import ChassisCliCommon
from ngts.cli_util.cli_parsers import generic_sonic_output_parser

logger = logging.getLogger()


class SonicChassisCli(ChassisCliCommon):
    """
    This class is for chassis cli commands for sonic only
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
        :return: the cmd output
        """
        return self.engine.run_cmd("show platform summary")

    def show_platform_syseeprom(self):
        """
        This method execute command "show platform syseeprom" on dut
        :return: the cmd output
        """
        return self.engine.run_cmd("show platform syseeprom")

    def show_mst_status(self):
        return self.engine.run_cmd("sudo mst status")

    def get_pci_conf(self):
        mst_status = self.show_mst_status()
        return re.search("(.*pciconf0)", mst_status).group(1)

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

    def show_platform_fan(self):
        """
        This method execute command "show platform fan" on dut
        :return: the cmd output
        """
        fan_status = self.engine.run_cmd("show platform fan")

        fan_status_table_dict = generic_sonic_output_parser(fan_status,
                                                            headers_ofset=0,
                                                            len_ofset=1,
                                                            data_ofset_from_start=2,
                                                            data_ofset_from_end=-0,
                                                            column_ofset=2,
                                                            output_key='FAN')

        logger.info(f"fan status:{fan_status_table_dict}")
        return fan_status_table_dict

    def show_platform_psu_status(self):
        """
        This method execute command "show platform psustatus" on dut
        :return: the cmd output
        """
        psu_status = self.engine.run_cmd("show platform psustatus")
        psu_status_table_dict = generic_sonic_output_parser(psu_status,
                                                            headers_ofset=0,
                                                            len_ofset=1,
                                                            data_ofset_from_start=2,
                                                            data_ofset_from_end=-0,
                                                            column_ofset=2,
                                                            output_key='PSU')

        logger.info(f"psu status:{psu_status_table_dict}")
        return psu_status_table_dict

    def get_platform_hwsku(self):
        """
        This method execute command "show platform summary" and return the dut hwsku
        :return: the dut hwsku
        """
        output = self.show_platform_summary()
        hwsku_pattern = r"HwSKU:\s*(.*)"

        res = re.search(hwsku_pattern, output, re.IGNORECASE)
        if res:
            hwsku = res.group(1)
            logger.info(f"hwsku is {hwsku}")
            return hwsku
        else:
            raise Exception("Could not get hwsku for switch {}".format(self.engine.ip))
