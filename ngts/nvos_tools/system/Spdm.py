from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure


class SPDMComponents:
    BMC = 'ERoT_BMC_0'
    CPU = 'ERoT_CPU_0'
    FPGA = 'ERoT_FPGA_0'
    NVSWITCH_0 = 'ERoT_NVSwitch_0'
    NVSWITCH_1 = 'ERoT_NVSwitch_1'
    ALL_SUPPORTED_COMPONENTS = [BMC, CPU, FPGA, NVSWITCH_0, NVSWITCH_1]


COMPONENT_TO_SPDM_OBJ_FIELD: Dict[str, str] = {
    SPDMComponents.BMC: 'bmc',
    SPDMComponents.CPU: 'cpu',
    SPDMComponents.FPGA: 'fpga',
    SPDMComponents.NVSWITCH_0: 'nvswitch_0',
    SPDMComponents.NVSWITCH_1: 'nvswitch_1',
}


class SpdmComponentFields:
    CERTIFICATES = 'certificates'
    MEASUREMENTS = 'measurements'
    ALL_FIELDS = [CERTIFICATES, MEASUREMENTS]


class Spdm(BaseComponent):
    def __init__(self, parent):
        super().__init__(parent=parent, path='/spdm')
        self.bmc = SpdmComponent(self, f'/{SPDMComponents.BMC}')
        self.cpu = SpdmComponent(self, f'/{SPDMComponents.CPU}')
        self.fpga = SpdmComponent(self, f'/{SPDMComponents.FPGA}')
        self.nvswitch_0 = SpdmComponent(self, f'/{SPDMComponents.NVSWITCH_0}')
        self.nvswitch_1 = SpdmComponent(self, f'/{SPDMComponents.NVSWITCH_1}')


class SpdmComponent(BaseComponent):
    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.certificates = BaseComponent(self, path=f'/{SpdmComponentFields.CERTIFICATES}')
        self.measurements = BaseComponent(self, path=f'/{SpdmComponentFields.MEASUREMENTS}')

    def action_generate(self, nonce=None, dut_engine=None) -> ResultObj:
        with allure.step(f'Execute action generate for {self.get_resource_path()}'):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_generate_spdm_measurements, engine,
                                                   self.get_resource_path(), nonce)
