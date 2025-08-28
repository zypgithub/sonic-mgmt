import allure
import logging

from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.platform.Voltage import Voltage


class Environment(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/environment')
        self.voltage = Voltage(self)
        self.fan = BaseComponent(self, self.api_obj, '/fan')
        self.led = BaseComponent(self, self.api_obj, '/led')
        self.psu = BaseComponent(self, self.api_obj, '/psu')
        self.leakage = BaseComponent(self, self.api_obj, '/leakage')
        self.temperature = BaseComponent(self, self.api_obj, '/temperature')

    def unset(self, op_param=""):
        raise Exception("unset is not implemented")

    def set(self, op_param_name="", op_param_value={}):
        raise Exception("set is not implemented")

    def get_available_psus(self, invert=False):
        """Returns a list of all PSUs (as strings) whose status is 'ok'. If invert=True return all other PSUs instead"""
        try:
            output = OutputParsingTool.parse_json_str_to_dictionary(self.psu.show()).get_returned_value()
            return list(psu for psu, fields in output.items() if (
                fields[PlatformConsts.INV_STATE] == PlatformConsts.INV_OK) != invert)
        except Exception as e:
            logging.error(f"Error getting available PSUs: {e}")
            return []
