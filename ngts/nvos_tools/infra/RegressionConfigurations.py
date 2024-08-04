import logging

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts

logger = logging.getLogger()


class Configurations:
    ndr_ports = {"10.7.148.94": ['swA1p1', 'swA1p2'],
                 "10.7.148.95": ['swA1p1', 'swA1p2'],
                 "10.7.145.61": ['swA1p1', 'swA1p2'],
                 "10.7.145.62": ['swA1p1', 'swA1p2'],
                 "10.7.148.88": ['swA1p1', 'swA1p2'],
                 "10.7.148.89": ['swA1p1', 'swA1p2']}

    xdr_ports = {}

    post_install_commands = {"10.7.144.153": ['nv set acl ACL_MGMT_INBOUND_CP_DEFAULT rule 120 match ip recent-list hit-count 3000',
                                              'nv config apply']}

    devices_to_configure_ndr_ports = ndr_ports.keys()

    default_conf = NvosConst.DEFAULT_CONFIG
    default_conf["interface"] = {
        "eth0": {
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
                for port in Configurations.ndr_ports[engine.ip]:
                    Configurations.default_conf["interface"][port] = \
                        {"link": {
                            "connection-mode": "ndr"
                        }}
            return Configurations.default_conf
        except BaseException:
            return Configurations.default_conf


class RegressionConfigurations:

    @staticmethod
    def configure_ports_to_legacy(engine, apply=True, throw_exception=True, wait_till_port_up=False):
        try:
            if engine.ip in Configurations.devices_to_configure_ndr_ports:
                with allure.step("Updating connection mode for ndr ports"):
                    for port in Configurations.ndr_ports[engine.ip]:
                        ndr_port = Port(port, "", "")
                        ndr_port_show = OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                            ndr_port.interface.link.show()).get_returned_value()

                        if ndr_port_show[LinkDetectionConsts.CONNECTION_MODE] != LinkDetectionConsts.CONNECTION_MODE_NDR:
                            ndr_port.interface.link.connection_mode.set(LinkDetectionConsts.CONNECTION_MODE_NDR,
                                                                        apply=False, dut_engine=engine,
                                                                        ask_for_confirmation=True).verify_result()
                    if apply:
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
