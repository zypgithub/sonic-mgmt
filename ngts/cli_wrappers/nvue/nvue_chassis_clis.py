from ngts.cli_wrappers.common.chassis_clis_common import ChassisCliCommon
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool


class NvueChassisCli(ChassisCliCommon):
    """
    This class is for chassis cli commands for NVOS only
    """

    def __init__(self, engine):
        self.engine = engine

    def show_platform_summary(self):
        """
        This method execute command "show platform summary" on dut
        :param engine: ssh engine object
        :return: the cmd output
        """
        return self.engine.run_cmd("cat /etc/sonic/config_db.json")

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
        platform_summary = OutputParsingTool.parse_json_str_to_dictionary(
            self.show_platform_summary()).get_returned_value()["DEVICE_METADATA"]['localhost']
        platform_summary['Platform'] = platform_summary.pop('platform')
        platform_summary['HwSKU'] = platform_summary.pop('hwsku')
        return platform_summary
