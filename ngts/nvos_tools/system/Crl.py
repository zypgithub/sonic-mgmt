import logging
from typing import Dict

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Crl(BaseComponent):

    def __init__(self, parent_obj):
        BaseComponent.__init__(self, parent_obj, path='/crl')
        self.crl_id: Dict[str, CrlId] = DefaultDict(lambda crl_id: CrlId(self, crl_id))


class CrlId(BaseComponent):
    def __init__(self, parent, crl_id):
        BaseComponent.__init__(self, parent, path=f'/{crl_id}')
        # self.dump = BaseComponent(self, path='/dump')
        # self.installed = BaseComponent(self, path='/installed')

    def action_import(self, data=None, uri=None, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action import for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_import_ca_certificate, engine,
                                                   self.get_resource_path(), data, uri)

    def action_delete(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action delete for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_delete_certificate, engine,
                                                   self.get_resource_path())
