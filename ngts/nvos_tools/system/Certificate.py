import logging
from typing import Dict

import allure

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Certificate(BaseComponent):

    def __init__(self, parent_obj):
        BaseComponent.__init__(self, parent_obj, path='/certificate')
        self.cert_id: Dict[str, CertId] = DefaultDict(lambda cert_id: CertId(self, cert_id))


class CertId(BaseComponent):
    def __init__(self, parent, cert_id):
        BaseComponent.__init__(self, parent, path=f'/{cert_id}')
        self.dump = BaseComponent(self, path='/dump')
        self.installed = BaseComponent(self, path='/installed')

    def action_import(self, data=None, passphrase=None, uri_bundle=None, uri_private_key=None, uri_public_key=None,
                      dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action import for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.get_engine()
            return SendCommandTool.execute_command(self._cli_wrapper.action_import_certificate, engine,
                                                   self.get_resource_path(), data, passphrase, uri_bundle,
                                                   uri_private_key, uri_public_key)

    def action_delete(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action import for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.get_engine()
            return SendCommandTool.execute_command(self._cli_wrapper.action_delete_certificate, engine,
                                                   self.get_resource_path())
