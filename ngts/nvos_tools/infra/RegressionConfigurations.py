import logging

from ngts.nvos_tools.infra import ExceptionTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts

logger = logging.getLogger()


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
        "10.7.148.112": ['sw38p1', 'sw53p1'],
        "10.7.148.113": ['sw38p1', 'sw53p1'],

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

    post_install_commands = {"10.7.144.153": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply'],
                             }

    devices_to_configure_ndr_ports = ndr_ports.keys()

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

            return Configurations.default_conf
        except BaseException:
            return Configurations.default_conf


class RegressionConfigurations:

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
                            Port.wait_for_port_state(ndr_port, NvosConsts.LINK_STATE_UP)

        except BaseException as ex:
            if throw_exception:
                raise
            else:
                ExceptionTool.log_exception(ex)
