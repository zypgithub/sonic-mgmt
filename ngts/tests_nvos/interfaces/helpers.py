from __future__ import annotations

import dataclasses
import logging

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvlInterfaceConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.cluster import cluster_tools
from ngts.nvos_tools.infra.Tools import Tools
from ngts.ngts_types import EnginesT

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Context:
    is_standalone_system: bool = True
    setup_name: str = ''

    @property
    def has_gpus(self) -> bool:
        return not self.is_standalone_system and self.setup_name != ''


def get_random_port(dut_engines: EnginesT, /, *,
                    port_type: str = NvlInterfaceConsts.NVL_PORT_TYPE,
                    ports_state: str = NvosConsts.LINK_STATE_UP,
                    interface_type: str = NvlInterfaceConsts.ACP_PORT_TYPE) -> Port:
    ''' get a random nvl access port from the system '''
    return get_random_ports(
        dut_engines,
        num_of_ports_to_select=1,
        port_type=port_type,
        ports_state=ports_state,
        interface_type=interface_type
    )[0]


def get_random_ports(dut_engines: EnginesT, /, *,
                     num_of_ports_to_select: int = 5,
                     port_type: str = NvlInterfaceConsts.NVL_PORT_TYPE,
                     ports_state: str = NvosConsts.LINK_STATE_UP,
                     interface_type: str = NvlInterfaceConsts.ACP_PORT_TYPE) -> tuple[Port, list[Port]]:
    ''' get a random range of nvl access ports from the system '''
    with allure.step(f'Get random {num_of_ports_to_select} NVL ports'):
        ports: list[Port] = Tools.RandomizationTool.select_random_ports(
            requested_ports_type=port_type,
            requested_ports_state=ports_state,
            num_of_ports_to_select=num_of_ports_to_select,
            interface_type=interface_type,
            dut_engine=dut_engines,
        ).get_returned_value()

    port_range_names = cluster_tools.summarize_ports([p.name for p in ports])
    return Port(port_range_names, '', ''), ports


def reboot_gpus() -> None:
    ''' reboot the GPUs and validate that the cluster is enabled only if it's NOT a standalone system '''
    if ctx.has_gpus:  # like mini-oberon
        with allure.step("Reboot the GPUs"):
            cluster_tools.ClusterTools.reboot_compute_nodes_gpus(ctx.setup_name)


def set_ctx(is_standalone_system: bool, setup_name: str) -> None:
    global ctx
    ctx = Context(is_standalone_system, setup_name)


ctx = Context()
