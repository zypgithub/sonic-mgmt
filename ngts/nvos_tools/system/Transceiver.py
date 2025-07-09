import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.Files import Files
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ActionConsts, PlatformConsts, ApiType

logger = logging.getLogger()


class Transceiver(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/transceiver')
        self.files = Files(self)

    def show_detailed(self):
        op_param = "" if self._api_to_use == ApiType.OPENAPI else 'detail'
        return self.show(op_param=op_param)

    def action_reset(self, transceiver_name, expected_str="", dut_engine=None):
        """nv action install platform transceiver firmware files <file-name> """
        return self.action_deprecated(ActionConsts.RESET, transceiver_name, expected_output=expected_str, dut_engine=dut_engine)

    def action_install(self, transceiver_name, file_name, expected_str="", dut_engine=None):
        """nv action install platform transceiver firmware files <file-name> """
        return self.action_deprecated(ActionConsts.INSTALL, transceiver_name + ' firmware files ' + file_name, expected_output=expected_str, dut_engine=dut_engine)

    def get_dict_of_transceivers(self, cable_type):
        """
        Returns a dict of transceivers according to cable_type
        :param cable_type: None / Copper / Optical
        :return: dict of transceivers according to cable_type
        """
        with allure.step('Search for transceivers that meet provided requirements'):

            logging.info("get_dict_of_transceivers - Searching for relevant transceivers")
            dict_of_transceivers = OutputParsingTool.parse_show_output_to_dict(self.show_detailed()).get_returned_value()

            if cable_type:
                dict_of_transceivers = {k: v for k, v in dict_of_transceivers.items() if v.get(PlatformConsts.TRANSCEIVER_CABLE_TYPE) == cable_type}
                logging.info(f"get_dict_of_transceivers - {dict_of_transceivers} meets the requirements of {cable_type}")
            else:
                dict_of_transceivers = {k: v for k, v in dict_of_transceivers.items() if PlatformConsts.TRANSCEIVER_CABLE_TYPE not in v}
                logging.info(f"get_dict_of_transceivers - {dict_of_transceivers} no {PlatformConsts.TRANSCEIVER_CABLE_TYPE} field therefore cable is not connected")

            return dict_of_transceivers

    def get_list_of_connected_transceivers(self):
        dict_of_transceivers = OutputParsingTool.parse_show_output_to_dict(self.show()).get_returned_value()
        return list(dict_of_transceivers.keys())
