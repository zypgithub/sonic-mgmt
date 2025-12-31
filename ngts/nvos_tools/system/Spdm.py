from typing import Dict, List

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure


class SPDMComponents:
    NVSWITCH_SMA_COUNT = 2
    JULIET_NVSWITCH_COUNT = 2
    ROSALIND_NVSWITCH_COUNT = 4
    BMC = "ERoT_BMC_0"
    CPU = "ERoT_CPU_0"
    FPGA = "ERoT_FPGA_0"
    NVSWITCH_SMA_0 = "IRoT_NVSwitch_SMA_0"
    NVSWITCH_SMA_1 = "IRoT_NVSwitch_SMA_1"
    NVSWITCH_0 = "ERoT_NVSwitch_0"
    NVSWITCH_1 = "ERoT_NVSwitch_1"
    ALL_SUPPORTED_COMPONENTS = [BMC, CPU, FPGA, NVSWITCH_0, NVSWITCH_1]

    @classmethod
    def nvswitch_sma(cls, index: int) -> str:
        """Get IRoT NVSwitch SMA (MCU) component name by index."""
        return f"IRoT_NVSwitch_SMA_{index}"

    @classmethod
    def rosalind_nvswitch(cls, index: int) -> str:
        """Get Rosalind NVSwitch component name by index."""
        return f"NVSwitch_{index}"

    @classmethod
    def juliet_nvswitch(cls, index: int) -> str:
        """Get Juliet ERoT NVSwitch component name by index."""
        return f"ERoT_NVSwitch_{index}"

    @classmethod
    def juliet_components(cls) -> List[str]:
        """All SPDM components for Juliet devices."""
        return cls.ALL_SUPPORTED_COMPONENTS

    @classmethod
    def rosalind_components(cls) -> List[str]:
        """All SPDM components for Rosalind devices."""
        return (
            [cls.BMC, cls.CPU] +
            [cls.nvswitch_sma(i) for i in range(cls.NVSWITCH_SMA_COUNT)] +
            [cls.rosalind_nvswitch(i) for i in range(cls.ROSALIND_NVSWITCH_COUNT)]
        )


class SpdmComponentFields:
    CERTIFICATES = "certificates"
    MEASUREMENTS = "measurements"
    ALL_FIELDS = [CERTIFICATES, MEASUREMENTS]


class Spdm(BaseComponent):
    """
    SPDM component supporting both Juliet and Rosalind devices.

    Access components via get_component(component_name):
        spdm.get_component('ERoT_BMC_0')           # Juliet/Rosalind BMC
        spdm.get_component('ERoT_NVSwitch_0')      # Juliet NVSwitch
        spdm.get_component('NVSwitch_0')           # Rosalind NVSwitch
        spdm.get_component('IRoT_NVSwitch_SMA_0')  # Rosalind MCU

    Component names come from device.get_spdm_components().
    """

    def __init__(self, parent):
        super().__init__(parent=parent, path="/spdm")
        self._components: Dict[str, "SpdmComponent"] = {}

    def get_component(self, component_name: str) -> "SpdmComponent":
        """
        Get SPDM component by its actual component name.

        Args:
            component_name: SPDM component name from get_spdm_components()

        Returns:
            SpdmComponent with the correct path for this component
        """
        if component_name not in self._components:
            self._components[component_name] = SpdmComponent(self, f"/{component_name}")
        return self._components[component_name]


class SpdmComponent(BaseComponent):
    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.certificates = BaseComponent(self, path=f"/{SpdmComponentFields.CERTIFICATES}")
        self.measurements = BaseComponent(self, path=f"/{SpdmComponentFields.MEASUREMENTS}")

    def action_generate(self, nonce=None, dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action generate for {self.get_resource_path()}"):
            engine = dut_engine if dut_engine else TestToolkit.get_engine()
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_generate_spdm_measurements, engine, self.get_resource_path(), nonce
            )
