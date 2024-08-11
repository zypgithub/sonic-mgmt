import logging

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


class Configurations:
    ndr_ports = {"10.7.148.94": ['swA1p1', 'swA2p1'],
                 "10.7.148.95": ['swA1p1', 'swA2p1'],
                 "10.7.145.61": ['swA1p1', 'swB5p1'],
                 "10.7.145.62": ['swA1p1', 'swB5p1'],
                 "10.7.148.80": ['swB7p1', 'swB7p2', 'swB8p1', 'swB8p2'],
                 "10.7.148.81": ['swB7p1', 'swB7p2', 'swB8p1', 'swB8p2'],
                 "10.7.148.88": ['swA1p1', 'swA2p1'],
                 "10.7.148.89": ['swA1p1', 'swA2p1', 'swA8p1', 'swA8p2'],
                 }

    xdr_ports = {"10.7.145.61": ['swA8p1', 'swB2p1', 'swB8p1'],
                 "10.7.145.62": ['swA8p1', 'swB2p1', 'swB8p1'],
                 "10.7.148.112": ['sw8p1', 'sw16p1', 'sw67p1'],
                 "10.7.148.113": ['sw8p1', 'sw16p1', 'sw67p1'],
                 }

    ports_by_rate = {"ndr": ndr_ports, "xdr": xdr_ports}

    post_install_commands = {"10.7.144.153": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply']}

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
                raise ex
            else:
                logging.warning(ex)
