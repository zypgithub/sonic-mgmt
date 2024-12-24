import logging
from typing import Dict

import allure

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class CaCertificate(BaseComponent):

    def __init__(self, parent_obj):
        BaseComponent.__init__(self, parent_obj, path='/ca-certificate')
        self.cert_id: Dict[str, CaCertId] = DefaultDict(lambda cert_id: CaCertId(self, cert_id))


class CaCertId(BaseComponent):
    def __init__(self, parent, cert_id):
        BaseComponent.__init__(self, parent, path=f'/{cert_id}')
        self.dump = BaseComponent(self, path='/dump')

    def action_import(self, data=None, uri=None, dut_engine=None, external: bool = False) -> ResultObj:
        with allure.step(f'Execute action import for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_import_ca_certificate, engine,
                                                   self.get_resource_path(), data, uri, external)

    def action_delete(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action import for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_delete_certificate, engine,
                                                   self.get_resource_path())
