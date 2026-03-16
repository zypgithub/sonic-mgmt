import logging
import re
from typing import Dict, List, TypedDict

from ngts.ngts_types.engines_T import EnginesT
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger(__name__)


class PortInfoT(TypedDict):
    port_num: int
    remote_switch_guid: str
    remote_port_num: int


class SwitchInfoT(TypedDict):
    switch_guid: str
    order: int
    ports: List[PortInfoT]


class IbnetdiscoverTool:
    """Static utility class for running and parsing ibnetdiscover output."""

    @staticmethod
    def run_ibnetdiscover(engines: EnginesT = None) -> List[SwitchInfoT]:
        """
        Run ibnetdiscover command and parse the output.

        Args:
            engines: Device engines to run the command on. If None, uses TestToolkit.engines.dut

        Returns:
            List[SwitchInfoT]: List of dictionaries, one per switch containing:
                - switch_guid (str): Switch GUID
                - order (int): Switch order
                - ports (List[PortInfoT]): List of port info, each port contains:
                    - port_num (str): Port number
                    - remote_switch_guid (str): Remote switch GUID
                    - remote_port_num (int): Remote port number
        """
        if engines is None:
            engines = TestToolkit.engines

        logger.info('Running ibnetdiscover to discover IB topology')
        output: str = engines.dut.run_cmd('sudo ibnetdiscover', validate=True)
        output_switches_list = re.split(r'vendid=.+\ndevid=.+', output)
        switches_list: List[SwitchInfoT] = []
        for switch_output in output_switches_list[1:]:
            tmp_switch: SwitchInfoT = {}
            m = re.search(r"Switch\s+74\s*\"\w+-([^\"]+)[^/]+/U(\d+)\"", switch_output)
            tmp_switch['switch_guid'] = m.group(1)
            tmp_switch['order'] = int(m.group(2))
            logger.info(f"Parsing ports for switch {tmp_switch['switch_guid']}")
            tmp_switch['ports'] = []
            for port_match in re.finditer(r"\[(\d+)\][^\"]*\"S-([^\"]+)\"\s*\[(\d+)\]", switch_output):
                port_info: PortInfoT = {
                    'port_num': int(port_match.group(1)),
                    'remote_switch_guid': port_match.group(2),
                    'remote_port_num': int(port_match.group(3)),
                }
                tmp_switch['ports'].append(port_info)
            switches_list.append(tmp_switch)
        switches_list.sort(key=lambda x: x['order'])
        return switches_list
