import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool


class Manager(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path='/manager')
        self.certificate = CertificateComponent(self, '/certificate')
        self.ca_certificate = CertificateComponent(self, '/ca-certificate')
        self.encryption = Encryption(self)
        self.crl = Crl(self)

    def action_update(self, state: str = '', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action update for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            res = SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                  self.get_resource_path(), 'state', state)
            return res

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action restore for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   self.get_resource_path())


class CertificateComponent(BaseComponent):
    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.is_ca = 'ca-certificate' in path

    def action_update(self, cert_id='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action update for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   self.get_resource_path(), f'{"ca" if self.is_ca else ""}cert-id', cert_id)

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action restore for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   self.get_resource_path())


class Encryption(BaseComponent):
    def __init__(self, parent):
        super().__init__(parent=parent, path='/encryption')

    def action_update(self, mode='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action update for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   self.get_resource_path(), 'mode', mode)

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action restore for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   self.get_resource_path())


class Crl(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path='/crl')

    def action_update(self, crl_id='', dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action update for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   self.get_resource_path(), 'crl-id', crl_id)

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action restore for {self.get_resource_path()}'):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   self.get_resource_path())
