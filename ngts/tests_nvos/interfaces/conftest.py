import logging
import pytest

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvlInterfaceConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.ngts_types import EnginesT, DevicesT
from ngts.nvos_tools.infra.Tools import Tools

from . import helpers

logger = logging.getLogger(__name__)


@pytest.fixture(scope='module')
def enable_cluster_for_mini_oberon(standalone_system: bool, setup_name: str, engines: EnginesT):
    """   Enable the cluster for mini-oberon systems, and setup the system context. """
    # this fixture will get the global variables to keep the test code clean
    helpers.set_ctx(standalone_system, setup_name)

    if not standalone_system:
        try:
            Tools.RandomizationTool.select_random_ports(
                requested_ports_state=NvosConsts.LINK_STATE_UP,
                num_of_ports_to_select=5,
                dut_engine=engines.dut,
                interface_type=NvlInterfaceConsts.ACP_PORT_TYPE,
            ).get_returned_value()
        except AssertionError:
            logger.warning("Failed to select 5 up acp ports, will try to reboot the GPUs")
            helpers.reboot_gpus()
            randome_acp_port = helpers.get_random_port(engines.dut)
            Port.wait_for_port_state(randome_acp_port, NvosConsts.LINK_STATE_UP)
    yield

    helpers.reboot_gpus()


@pytest.fixture(scope='module')
def access_ports(devices: DevicesT):
    """ Convert the access ports of the DUT to Port range object """
    # Extract numeric indices from ACP port names by removing 'acp' prefix
    port_indices = [
        int(port_name.replace(NvlInterfaceConsts.ACP_PORT_TYPE, ''))
        for port_name in devices.dut.nvl5_access_ports_list
    ]
    min_port, max_port = min(port_indices), max(port_indices)
    yield Port(f'{NvlInterfaceConsts.ACP_PORT_TYPE}{min_port}-{max_port}', '', '')


@pytest.fixture
def has_active_access_ports(standalone_system: bool, has_loopbox: bool):
    """ check if a system doesn't have active access ports, skip the test """
    if standalone_system and not has_loopbox:
        pytest.skip(reason="System doesn't have active access ports, skipping the test")
