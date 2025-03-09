import logging
import json
from typing import Dict, Tuple, List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts, PlatformConsts
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


MTVR_MAMBA_06_0 = '10.245.21.54'
MTVR_MAMBA_06_1 = '10.245.21.65'
MTVR_CROC_19_0 = '10.245.21.19'
MTVR_CROC_19_1 = '10.245.21.68'
MTVR_CROC_50_0 = '10.245.21.50'
MTVR_CROC_50_1 = '10.245.21.67'


class Configurations:
    # List of NDR ports in Crocodile (for setting connection-mode to ndr)
    ndr_ports = {"10.7.148.94": ['swA1p1', 'swA2p1'],
                 "10.7.148.95": ['swA1p1', 'swA2p1'],
                 "10.7.145.61": ['swA1p1', 'swA14p1'],
                 "10.7.145.62": ['swA1p1', 'swA14p1'],
                 }

    # List of all ports connected to traffic servers
    traffic_ports = {
        # Black Mamba
        "10.7.148.248": ['sw61p1', 'sw67p1'],
        "10.7.148.249": ['sw61p1', 'sw67p1'],

        # Crocodile
        "10.7.148.94": ['swA1p1', 'swA2p1'],
        "10.7.148.95": ['swA1p1', 'swA2p1'],
        "10.7.145.61": ['swA1p1', 'swA14p1'],
        "10.7.145.62": ['swA1p1', 'swA14p1'],

        # Gorilla
        "10.7.144.153": ['sw1p1', 'sw1p2'],
        "10.7.144.154": ['sw1p1', 'sw1p2'],
        "10.7.144.58": ['sw1p1', 'sw1p2', 'sw2p1'],
    }

    juliet_systems_with_loopbox = ["NVOS_juliet_10_7_148_195", "NVOS_juliet_10_7_148_136"]

    non_standalone_systems = ['NVOS_juliet_10_7_148_148']

    compute_nodes_per_system = {
        'NVOS_juliet_10_7_148_148': [{'ip_address': '10.7.34.145', 'username': 'nvidia', 'password': 'nvidia'},
                                     {'ip_address': '10.7.34.192', 'username': 'nvidia', 'password': 'nvidia'}]}

    ports_to_disable = {'NVOS_juliet_10_7_148_148': ['acp17-20', 'acp69-72']}

    oberon_num_of_gpus = {'NVOS_juliet_10_7_148_148': '8'}

    post_install_commands = {"10.7.144.153": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply -y'],
                             "10.245.21.50": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply -y'],
                             "10.245.21.67": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply -y']
                             # "10.7.148.248": ['sudo cp /usr/share/sonic/device/x86_64-nvidia_q3450_ld-r0/platform.json /usr/share/sonic/device/x86_64-nvidia_q3400_ra-r0/platform.json',
                             #                  'sudo cp /usr/share/sonic/device/x86_64-nvidia_q3450_ld-r0/co_optics_modules.json /usr/share/sonic/device/x86_64-nvidia_q3400_ra-r0/co_optics_modules.json',
                             #                  'sudo sed -i \'s/"sfp_count"[[:space:]]*:[[:space:]]*"[0-9]*",/"sfp_count":"73",/\' /usr/share/sonic/device/x86_64-nvidia_q3400_ra-r0/platform.json']
                             }

    devices_missing_psus = {}
    devices_to_configure_ndr_ports = ndr_ports.keys()
    devices_requested_factory_reset = []  # ['10.7.148.248']

    default_conf = NvosConst.DEFAULT_CONFIG
    default_conf["interface"] = {
        "eth0-1": {
            "acl": {
                "ACL_MGMT_INBOUND_CP_DEFAULT": {
                    "inbound": {
                        "control-plane": {}
                    }
                },
                "ACL_MGMT_INBOUND_CP_DEFAULT_IPV6": {
                    "inbound": {
                        "control-plane": {}
                    }
                },
                "ACL_MGMT_INBOUND_DEFAULT": {
                    "inbound": {}
                },
                "ACL_MGMT_INBOUND_DEFAULT_IPV6": {
                    "inbound": {}
                },
                "ACL_MGMT_OUTBOUND_CP_DEFAULT": {
                    "outbound": {
                        "control-plane": {}
                    }
                },
                "ACL_MGMT_OUTBOUND_CP_DEFAULT_IPV6": {
                    "outbound": {
                        "control-plane": {}
                    }
                }
            },
            "type": "eth"
        },
        "lo": {
            "acl": {
                "ACL_LOOPBACK_INBOUND_CP_DEFAULT": {
                    "inbound": {
                        "control-plane": {}
                    }
                },
                "ACL_LOOPBACK_INBOUND_CP_DEFAULT_IPV6": {
                    "inbound": {
                        "control-plane": {}
                    }
                }
            },
            "type": "loopback"
        }
    }

    @staticmethod
    def get_regression_default_config(engine):
        try:
            if engine.ip in Configurations.devices_to_configure_ndr_ports:
                ndr_ports = ",".join(list(Configurations.ndr_ports[engine.ip]))
                Configurations.default_conf["interface"][ndr_ports] = \
                    {"link": {
                        "connection-mode": "ndr"
                    }, "type": "ib"}
        except BaseException:
            pass

        if engine.ip in Configurations.devices_missing_psus:
            if 'platform' not in Configurations.default_conf:
                Configurations.default_conf['platform'] = {}
            Configurations.default_conf['platform']['ps-redundancy'] = {
                PlatformConsts.PS_REDUNDANCY_POLICY: PlatformConsts.PS_REDUNDANCY_NO}

        return Configurations.default_conf


class RegressionConfigurations:

    @staticmethod
    def set_base_configurations(engine: LinuxSshEngine, apply=True):
        with allure.step('Set base configurations for device'):
            with allure.independent_step('Setting ps-redundancy if needed'):
                RegressionConfigurations.configure_ps_redundancy_policy(engine)
            with allure.independent_step('Setting connection-mode if needed'):
                RegressionConfigurations.configure_ports_to_legacy(engine=engine, apply=False)
            if apply:
                with allure.independent_step('Applying base configuration (if there is a diff)'):
                    config_diff = OutputParsingTool.parse_json_str_to_dictionary(NvueGeneralCli.show_config(engine)
                                                                                 ).get_returned_value()
                    if config_diff:
                        NvueGeneralCli.apply_config(engine=engine, option='-y', verify_execution=True)

    @staticmethod
    def configure_ps_redundancy_policy(engine: LinuxSshEngine):
        if engine.ip in Configurations.devices_missing_psus:
            Platform().ps_redundancy.set(PlatformConsts.PS_REDUNDANCY_POLICY, PlatformConsts.PS_REDUNDANCY_NO,
                                         dut_engine=engine)

    @staticmethod
    def configure_ports_to_legacy(engine, apply=True, throw_exception=True, wait_till_port_up=False):
        try:
            if engine.ip in Configurations.devices_to_configure_ndr_ports:
                with allure.step("Updating connection mode for ndr ports"):
                    port_updated = False
                    for port in Configurations.ndr_ports[engine.ip]:
                        ndr_port = Port(port, "", "")
                        ndr_port_show = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                            ndr_port.interface.link.show(dut_engine=engine)).get_returned_value()

                        if ndr_port_show[LinkDetectionConsts.CONNECTION_MODE] != LinkDetectionConsts.CONNECTION_MODE_NDR:
                            ndr_port.interface.link.connection_mode.set(LinkDetectionConsts.CONNECTION_MODE_NDR,
                                                                        apply=False, dut_engine=engine,
                                                                        ask_for_confirmation=True).verify_result()
                            port_updated = True

                    if apply and port_updated:
                        with allure.step("Apply configuration"):
                            output = NvueGeneralCli.apply_config(engine=engine, option='--assume-yes')
                            assert "applied" in output, "Failed to apply config"

                        if wait_till_port_up:
                            ndr_port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP)

        except BaseException as ex:
            if throw_exception:
                raise
            else:
                ExceptionTool.log_exception(ex)


class RegressionLinksConsts:
    SYSTEM_LINKS_PATH = "/auto/sw_system_project/NVOS_INFRA/verification_files/links_by_system/"
    TRANSCEIVER_TYPE = "transceiver_type"
    PORTS_LIST = "ports_list"
    IS_LOOPBACK = "is_loopback"
    CONNECTED_TO = "connected_to"
    CONNECTED_TO_SYSTEM_TYPE = "type"
    CONNECTED_TO_SYSTEM_NAME = "system"
    CONNECTED_TO_PORTS = "ports_list"
    TYPE_OPTICAL = "optical"
    TYPE_COPPER = "copper"
    TYPE_ACTIVE = "active"
    SYSTEM_TYPE_SERVER = "server"


class RegressionLinks:
    @staticmethod
    def _get_setup_links(setup_name):
        links_path = RegressionLinksConsts.SYSTEM_LINKS_PATH + setup_name + ".json"
        with allure.step(f'Read {setup_name} links info from json {links_path}'):
            with open(links_path, 'r') as file:
                connections_dict = json.load(file)
            return connections_dict

    @staticmethod
    def get_filtered_transceivers(setup_name, transceiver_type="", is_loopback=None, connected_to="") -> List[str]:
        """
        Get filtered transceivers based on the given parameters.

        :param setup_name: The setup name to filter connections by
        :param transceiver_type: Filter by the transceiver type (optional)
        :param is_loopback: Filter by loopback status (optional)
        :param connected_to: Filter by connected entity (server/setup) and its name (optional)
        :return: A list of filtered transceivers
        """
        with allure.step(f'Get filtered transceivers for {setup_name}'):
            connections = RegressionLinks._get_setup_links(setup_name)
            filtered = []

            for transceiver, transceiver_data in connections.items():
                if transceiver_type and transceiver_data[RegressionLinksConsts.TRANSCEIVER_TYPE] != transceiver_type:
                    continue
                if is_loopback is not None and transceiver_data[RegressionLinksConsts.IS_LOOPBACK] != is_loopback:
                    continue
                if connected_to:
                    system_type = transceiver_data[RegressionLinksConsts.CONNECTED_TO][
                        RegressionLinksConsts.CONNECTED_TO_SYSTEM_TYPE]
                    system_name = transceiver_data[RegressionLinksConsts.CONNECTED_TO][
                        RegressionLinksConsts.CONNECTED_TO_SYSTEM_NAME]
                    if connected_to not in [system_type, system_name]:
                        continue

                with allure.step(f"add {transceiver_data} to the filtered list"):
                    filtered.append(transceiver)

            allure.attach('filtered transceivers', filtered)
            return filtered

    @staticmethod
    def get_filtered_transceivers_and_ports(setup_name, transceiver_type="", is_loopback=None, connected_to=""
                                            ) -> Dict[str, List[str]]:
        """
        Get filtered transceivers and the ports connected to them based on the given parameters.

        :param engine: LinuxSshEngine instance
        :param setup_name: The setup name to filter connections by
        :param transceiver_type: Filter by the transceiver type (optional)
        :param is_loopback: Filter by loopback status (optional)
        :param connected_to: Filter by connected entity (server/setup) and its name (optional)
        :return: {transceiver_name: [port_name, ...], ...}
        """
        with allure.step(f'Get filtered transceivers and ports for {setup_name}'):
            filtered_with_ports = {}
            connections = RegressionLinks._get_setup_links(setup_name)
            filtered_transceivers = RegressionLinks.get_filtered_transceivers(setup_name, transceiver_type, is_loopback,
                                                                              connected_to)
            for transceiver in filtered_transceivers:
                if transceiver in connections:
                    filtered_with_ports[transceiver] = connections[transceiver][RegressionLinksConsts.PORTS_LIST]

            return filtered_with_ports

    @staticmethod
    def get_transceiver_data_and_port_index(setup_name: str, transceiver_name: str, port_name='') -> Tuple[Dict, int]:
        """
        Returns the dict describing the transceiver from the setup's json file.
        If port_name is given, returns also the position (index) of this port in the transceiver's list of ports;
        otherwise the second returned value is None.
        """
        data = RegressionLinks._get_setup_links(setup_name)[transceiver_name]
        port_index = data[RegressionLinksConsts.CONNECTED_TO_PORTS].index(port_name) if port_name else None
        return data, port_index

    @staticmethod
    def get_loopback_end(setup_name: str, transceiver_name: str, port_name: str) -> str:
        """ Given a port in loopback connection, returns the name of the port at the other end of the cable. """
        transceiver, port_index = RegressionLinks.get_transceiver_data_and_port_index(setup_name, transceiver_name,
                                                                                      port_name)
        if not transceiver[RegressionLinksConsts.IS_LOOPBACK]:
            raise ValueError(f"{transceiver_name} is not a loopback connection: {transceiver}")

        result = transceiver[RegressionLinksConsts.CONNECTED_TO][RegressionLinksConsts.CONNECTED_TO_PORTS][port_index]
        logger.info(f"Port {port_name} is connected to {result}")
        return result

    @staticmethod
    def get_connected_host_and_port(setup_name: str, transceiver_name: str, port_name: str) -> Tuple[str, str]:
        """Returns the name of the host connected to the given port, and the name of the connected port on the host."""
        transceiver, port_index = RegressionLinks.get_transceiver_data_and_port_index(setup_name, transceiver_name, port_name)
        connected_to = transceiver[RegressionLinksConsts.CONNECTED_TO]
        connected_to_type = connected_to[RegressionLinksConsts.CONNECTED_TO_SYSTEM_TYPE]
        if connected_to_type != RegressionLinksConsts.SYSTEM_TYPE_SERVER:
            raise ValueError(f"{transceiver_name} is connected to {connected_to_type}, expected {RegressionLinksConsts.SYSTEM_TYPE_SERVER}")

        host = connected_to[RegressionLinksConsts.CONNECTED_TO_SYSTEM_NAME]
        # todo: the current json format doesn't support a dual port going to two different devices
        host_port = connected_to[RegressionLinksConsts.CONNECTED_TO_PORTS][port_index]
        logger.info(f"Port {port_name} is connected to {host} port {host_port}")
        return host, host_port
