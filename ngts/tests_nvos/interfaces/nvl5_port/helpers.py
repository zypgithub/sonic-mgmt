import random
import pytest

from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.tools.test_utils import allure_utils as allure


def skip_if_no_trunk_links(devices):
    has_any_connected_transceivers = bool(ClusterTools.get_all_interfaces_with_transceivers(devices))
    if isinstance(devices.dut, JulietNonScaleoutSwitch) or not has_any_connected_transceivers:
        pytest.skip("Skipping test - no connected trunk ports")


def skip_if_no_access_links(has_loopbox, standalone_system):
    if not has_loopbox and standalone_system:
        pytest.skip("Skipping test - no connected access ports")
