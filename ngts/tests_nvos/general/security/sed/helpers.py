from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.TpmTool import TpmTool


def sed_password_factory_reset_check(engines=None, devices=None):
    engines = engines or TestToolkit.engines
    dut_device: BaseSwitch = devices or TestToolkit.devices.dut
    tpm_tool = TpmTool(engines.dut)

    yield  # do factory reset

    dut_device.verify_sed_password(tpm_tool)

    yield  # to prevent StopIteration on the 2nd next() call
