import logging

import ngts.tools.test_utils.allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst, SystemConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils.nvos_general_utils import set_base_configurations


def clear_conf(dut_engine, markers=None, set_base_config_function=set_base_configurations):
    try:
        if markers and 'system_profile_cleanup' in markers:
            clear_system_profile_config()

        with allure.step("Detach config"):
            NvueGeneralCli.detach_config(dut_engine)

        with allure.step("Get a list of 'set' components"):
            show_config_output = OutputParsingTool.parse_json_str_to_dictionary(
                NvueGeneralCli.show_config(dut_engine)).get_returned_value()

            set_comp = {k: v for comp in show_config_output for k, v in comp.get("set", {}).items()}

            with allure.step("Get the non-default set components"):
                default_conf = Configurations.get_regression_default_config(engine=dut_engine)
                """default_conf = NvosConst.DEFAULT_CONFIG
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
                }"""

                diff_config = ValidationTool.get_dictionaries_diff(set_comp, default_conf)
                logging.info(diff_config)

            if diff_config:
                active_port = None
                if NvosConst.INTERFACE in diff_config.keys():
                    result = RandomizationTool.select_random_ports(num_of_ports_to_select=1, dut_engine=dut_engine)
                    if result.result:
                        active_port = result.returned_value[-1]
                    NvueBaseCli.unset(dut_engine, NvosConst.INTERFACE)

                if NvosConst.IB in diff_config.keys():
                    NvueBaseCli.unset(dut_engine, 'ib')

                should_wait_for_nvued_after_apply = False

                if NvosConst.SYSTEM in diff_config.keys():
                    with allure.step("Unset each system 'set' command"):
                        unset_system_cli = "nv unset system"
                        should_wait_for_nvued_after_apply = NvosConst.SYSTEM_AAA in diff_config[
                            NvosConst.SYSTEM].keys() \
                            and NvosConst.SYSTEM_AUTHENTICATION in \
                            diff_config[NvosConst.SYSTEM][
                            NvosConst.SYSTEM_AAA].keys() \
                            and NvosConst.SYSTEM_AUTHENTICATION_ORDER in \
                            diff_config[NvosConst.SYSTEM][NvosConst.SYSTEM_AAA][
                            NvosConst.SYSTEM_AUTHENTICATION].keys()

                        unset_cli_cmd = ""

                        system_config = diff_config.get(NvosConst.SYSTEM, {})
                        aaa_config = system_config.get(NvosConst.SYSTEM_AAA, {})
                        user_config = aaa_config.get(NvosConst.SYSTEM_AAA_USER, {})

                        # unset system user for non-default users
                        unset_cli_cmd += " ".join([f"{unset_system_cli} {NvosConst.SYSTEM_AAA} "
                                                   f"{NvosConst.SYSTEM_AAA_USER} {user_comp}; " for user_comp in
                                                   user_config.keys() if
                                                   user_comp != NvosConst.SYSTEM_AAA_USER_ADMIN and
                                                   user_comp != NvosConst.SYSTEM_AAA_USER_MONITOR and
                                                   user_comp != NvosConst.SYSTEM_AAA_USER_CUMULUS])

                        # unset system aaa components
                        unset_cli_cmd += " ".join([f"{unset_system_cli} {NvosConst.SYSTEM_AAA} {aaa_comp}; " for
                                                   aaa_comp in aaa_config.keys() if
                                                   aaa_comp != NvosConst.SYSTEM_AAA_USER])

                        # unset other system components
                        unset_cli_cmd += " ".join([f"{unset_system_cli} {set_comp_name}; " for set_comp_name in
                                                   system_config.keys() if set_comp_name != NvosConst.SYSTEM_AAA])

                        logging.info("Execute system unset commands")
                        dut_engine.run_cmd(unset_cli_cmd)

                with allure.step("Set base configurations"):
                    set_base_config_function(dut_engine=dut_engine, apply=False)

                with allure.step("Apply configurations"):
                    NvueGeneralCli.apply_config(dut_engine, ask_for_confirmation=True, option='--assume-yes')

                if should_wait_for_nvued_after_apply:
                    DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine).verify_result()
                if active_port:
                    active_port.interface.wait_for_port_state(state='up', dut_engine=dut_engine).verify_result()
    finally:
        with allure.step("Detach config"):
            NvueGeneralCli.detach_config(dut_engine)


def clear_system_profile_config(dut_engine=None):
    with allure.step("Clear system profile"):
        system = System(None)
        system_profile_output = OutputParsingTool.parse_json_str_to_dictionary(
            system.profile.show(dut_engine=dut_engine)).get_returned_value()
        try:
            ValidationTool.validate_fields_values_in_output(SystemConsts.PROFILE_OUTPUT_FIELDS,
                                                            SystemConsts.DEFAULT_SYSTEM_PROFILE_VALUES,
                                                            system_profile_output).verify_result()
        except AssertionError:
            system.profile.action_profile_change(
                params_dict={'adaptive-routing': 'enabled', 'breakout-mode': 'disabled'}, engine=dut_engine)
