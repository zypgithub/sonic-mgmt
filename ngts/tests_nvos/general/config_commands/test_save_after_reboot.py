import logging
import time

import pytest
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_constants.constants_nvos import FastRecoveryConsts
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst, ApiType, AclConsts, IpConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools

logger = logging.getLogger()


@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.general
def test_save_reboot(engines, devices):
    """
        Test flow:
            1. run nv set system hostname <new_hostname> with apply
            2. Run 'nv set fae fast-recovery state disabled' and apply config
            3. Run 'nv system contact "contact_info_1"' and apply config
            4. Run 'nv system location "location_info_1"' and apply config
            5. run nv config save
            6. Run 'nv system contact "contact_info_2"' and apply config
            7. Run 'nv system location "location_info_2"' and apply config
            8. run nv set interface eth0 description <new_description> with apply
            9. Run 'nv set fast-recovery trigger credit-watchdog event warning' and apply config
            10. run nv action reboot system
            11. run nv show system after reload
            12. verify hostname is new_hostname
            13. Verify fast-recovery state is Disabled
            14. Run nv show interface eth0
            15. Verify the applied description value is ''
            16. Verify that applied system contact is "contact_info_1"
            17. Verify that applied system location is "location_info_1"
            18. Verify fast-recovery trigger event for trigger-id is Error
            19. cleanup - run nv unset system hostname & reboot
    """

    nmx_log_stream_test = False
    if hasattr(devices.dut, "cluster_app_nmx_controller"):
        nmx_log_stream_test = True

    with allure.step('Run show system command and verify that each field has a value'):
        system = System()
        sys_info = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        old_hostname = sys_info[SystemConsts.HOSTNAME]
        new_hostname_value = 'TestingConfigCmds'

        # TODO: Fix fae recovery
        '''with allure_step('Run set fae fast-recovery state command to set to disable and apply config'):
            fae.fast_recovery.set(FastRecoveryConsts.STATE,
                                  FastRecoveryConsts.STATE_DISABLED, apply=True, dut_engine=engines.dut)'''

        with allure.step('Set system events table-size to 600 and validate'):
            system.events.set(op_param_name='table-size', op_param_value=600, apply=True, dut_engine=engines.dut).\
                verify_result()
            output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output, SystemConsts.EVENTS_TABLE_SIZE, '600').verify_result()

        with allure.step('Simulate 10 system events'):
            output = engines.dut.run_cmd('docker exec eventd events_publish_test.py -c 10')
            assert output == '', 'Error in executing simulate command: {}'.format(output)
            time.sleep(10)

        with allure.step('Extract last system event to verify post reboot'):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show_events_last_recent_entries(SystemConsts.SYSTEM_LAST_EVENT, '1')).get_returned_value()
            event_id = str(list(output.keys())[0])
            event_time = output[event_id]["time-created"]

        with allure.step('Run set system contact contact_info_1 command and apply config'):
            system.set(op_param_name=SystemConsts.CONTACT, op_param_value="contact_info_1", apply=True,
                       dut_engine=engines.dut).verify_result()

        with allure.step('Run set system location location_info_1 command and apply config'):
            system.set(op_param_name=SystemConsts.LOCATION, op_param_value="location_info_1", apply=True,
                       dut_engine=engines.dut).verify_result()

        with allure.step('Run set system dns server ipv4 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=SystemConsts.DNS_SERVER_IDS["ipv4"],
                           apply=True, dut_engine=engines.dut).verify_result()
        with allure.step('Run set acl <acl_name> rule <rule_id> action set dscp'):
            acl_id = 'ACL_TO_BE_SAVED'
            rule_id = 1
            acl_type = IpConsts.IPV4
            acl_obj = Acl()
            acl_obj.set(acl_id).verify_result()
            acl_id_obj = acl_obj.acl_id[acl_id]
            acl_id_obj.set(AclConsts.TYPE, acl_type).verify_result()
            acl_id_obj.rule.set(rule_id).verify_result()
            rule_id_obj = acl_id_obj.rule.rule_id[rule_id]
            rule_id_obj.action.dscp.set(1, apply=True)
        with allure.step("Validate dscp configuration with show commands"):
            output = OutputParsingTool.parse_dscp_value_from_acl(engines, acl_obj, acl_id, rule_id)
            ValidationTool.verify_field_value_in_output(output, AclConsts.DSCP, 1).verify_result()

        if nmx_log_stream_test:
            with allure.step("Start Cluster"):
                cluster = Cluster()
                cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled',
                                                                 nmx_c_expected_state='up')

            with allure.step("Set NMX-C log stream configuration"):
                player = engines.sonic_mgmt
                url = f'{player.username}:{player.password}@{player.ip}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
                url_show = f'{player.username}:********@{player.ip}:{ClusterConsts.NMXC_LOG_STREAM_DEFAULT_PORT}'
                stream = f'{ClusterConsts.PROTOCOL_RSYSLOG} {url}'
                cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.action_update_cluster_log_stream(stream=stream)

        with allure.step('set hostname to be {hostname} - with apply'.format(hostname=new_hostname_value)):
            system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=True, ask_for_confirmation=True)
            TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

        with allure.step('Run set system dns server ipv6 command and apply config'):
            system.dns.set(op_param_name=SystemConsts.DNS_SERVER, op_param_value=SystemConsts.DNS_SERVER_IDS["ipv6"],
                           apply=True, dut_engine=engines.dut).verify_result()

        try:
            eth0_port = Port('eth0')
            new_eth0_description = 'eth0_test_desc'
            trigger_id = FastRecoveryConsts.TRIGGER_CREDIT_WATCHDOG

            with allure.step(
                    'set eth0 description to be {description} - with apply'.format(description=new_eth0_description)):
                eth0_port.interface.set(NvosConst.DESCRIPTION, new_eth0_description, apply=True).verify_result()

            # TODO: Fix fae recovery
            '''with allure_step('Run set fae fast-recovery trigger trigger-id event command and apply config'):
                fae.fast_recovery.trigger.set(trigger_id + ' ' + FastRecoveryConsts.TRIGGER_EVENT,
                                              FastRecoveryConsts.SEVERITY_WARNING, apply=True,
                                              dut_engine=engines.dut).verify_result()'''

            with allure.step('Run set system contact contact_info_2 command and apply config'):
                system.set(op_param_name=SystemConsts.CONTACT, op_param_value="contact_info_2", apply=True,
                           dut_engine=engines.dut).verify_result()

            with allure.step('Run set system location location_info_2 command and apply config'):
                system.set(op_param_name=SystemConsts.LOCATION, op_param_value="location_info_2", apply=True,
                           dut_engine=engines.dut).verify_result()

            with allure.step('Run nv action reboot system'):
                system.action_reboot(send_user_confirmation='y').verify_result()

            with allure.step('verify the hostname is {hostname}'.format(hostname=new_hostname_value)):
                system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
                ValidationTool.verify_field_value_in_output(system_output, SystemConsts.HOSTNAME,
                                                            new_hostname_value).verify_result()

            with allure.step('Verify that system events table-size config was saved'):
                output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).get_returned_value()
                ValidationTool.verify_field_value_in_output(output, SystemConsts.EVENTS_TABLE_SIZE, '600').\
                    verify_result()

            with allure.step('Verify that the system event before the reboot is present post reboot as well'):
                output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show(event_id)).get_returned_value()
                assert event_time == output.get("time-created"), 'Event {} removed from system events table post reboot'.format(event_time)

            # TODO: Fix fae recovery
            '''with allure_step('Verify fae fast-recovery state is Disabled'):
                fast_recovery_output = OutputParsingTool.parse_json_str_to_dictionary(
                    fae.fast_recovery.show()).get_returned_value()
                ValidationTool.verify_field_value_in_output(fast_recovery_output, FastRecoveryConsts.STATE,
                                                            FastRecoveryConsts.STATE_DISABLED).verify_result()'''

            with allure.step('Verify DNS server ipv4, configured before save, is in show system dns server output'):
                dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)). \
                    get_returned_value()
                assert SystemConsts.DNS_SERVER_IDS["ipv4"] in dns_output, \
                    "The configured DNS server {} is not present in show system dns". \
                    format(SystemConsts.DNS_SERVER_IDS["ipv4"])

            with allure.step("Validate dscp configuration with show commands after reboot"):
                output = OutputParsingTool.parse_dscp_value_from_acl(engines, acl_obj, acl_id, rule_id)
                ValidationTool.verify_field_value_in_output(output, AclConsts.DSCP, 1).verify_result()

            with allure.step('Verify DNS server ipv6, configured after save, is not in show system dns server output'):
                dns_output = OutputParsingTool.parse_json_str_to_dictionary(system.dns.show(SystemConsts.DNS_SERVER)). \
                    get_returned_value()
                assert SystemConsts.DNS_SERVER_IDS["ipv6"] not in dns_output, \
                    "The configured DNS server {} is unexpectedly present in show system dns".\
                    format(SystemConsts.DNS_SERVER_IDS["ipv6"])

            with allure.step('verify the eth0 description was not saved after reboot'):
                output_dictionary = OutputParsingTool.parse_show_interface_output_to_dictionary(
                    eth0_port.interface.show()).get_returned_value()
                assert IbInterfaceConsts.DESCRIPTION not in output_dictionary.keys() or \
                    output_dictionary[IbInterfaceConsts.DESCRIPTION] != new_eth0_description, \
                    "Description should not be saved after reboot"

            if not is_bug_active(4362872):
                with allure.step('Verify system contact is set to contact_info_1'):
                    ValidationTool.verify_field_value_in_output(system_output, SystemConsts.CONTACT, "contact_info_1").\
                        verify_result()

                with allure.step('Verify system location is set to location_info_1'):
                    ValidationTool.verify_field_value_in_output(system_output, SystemConsts.LOCATION, "location_info_1").\
                        verify_result()

            with allure.step("verify dscp option is loaded back after reboot"):
                dscp_output = OutputParsingTool.parse_json_str_to_dictionary(rule_id_obj.action.show()).\
                    get_returned_value()
                assert dscp_output['set']['dscp'] == 1, \
                    "The configured dscp is not present after reboot"

            if nmx_log_stream_test:
                with allure.step("Verify cluster is enabled"):
                    output = OutputParsingTool.parse_show_output_to_dict(cluster.show()).get_returned_value()
                    assert output[SystemConsts.STATE] == 'enabled', "Cluster was disabled instead of enabled"

                with allure.step("Validate NMX-Controller log stream configuration is {}".format(stream)):
                    output = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER].logstream.show(exempted_err_msgs="Error")
                    output_dict = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
                    assert output_dict["protocol"] == ClusterConsts.PROTOCOL_RSYSLOG, \
                        "Protocol is {} instead of {}".format(output_dict["protocol"], ClusterConsts.PROTOCOL_RSYSLOG)
                    assert output_dict["remote-url"] == url_show, \
                        "Remote-url is {} instead of {}".format(output_dict["remote-url"], url_show)

        finally:
            with allure.step('Cleanup - Run unset system DNS server and apply config'):
                system.dns.unset(SystemConsts.DNS_SERVER, apply=True, dut_engine=engines.dut).verify_result()

            with allure.step('Cleanup - set hostname to be {hostname} - with apply'.format(hostname=old_hostname)):
                system.unset(SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True)
                TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
                with allure.step('Run nv action reboot system'):
                    system.reboot.action_reboot()


@pytest.mark.cumulus
@pytest.mark.simx
@pytest.mark.general
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_general_auto_save(engines, devices, test_api):
    system = System()
    eth0_port = Port('eth0')
    TestToolkit.tested_api = test_api
    new_eth0_description = 'TestingAutoSave'

    try:
        with allure.step('verify auto-save state is disabled'):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.config.auto_save.show()).verify_result()
            assert SystemConsts.AUTO_SAVE_STATE_DISABLED == output[
                SystemConsts.AUTO_SAVE_STATE], "state should be disabled"

        with allure.step('set auto-save state to enabled'):
            system.config.auto_save.set(op_param_name=SystemConsts.AUTO_SAVE_STATE,
                                        op_param_value=SystemConsts.AUTO_SAVE_STATE_ENABLED).verify_result()

        with allure.step(
                'set eth0 description to be {description} - with apply'.format(description=new_eth0_description)):
            eth0_port.interface.set(NvosConst.DESCRIPTION, new_eth0_description, apply=True).verify_result()

        assert new_eth0_description in TestToolkit.GeneralApi[test_api].show_config(engine=engines.dut,
                                                                                    revision='startup'), \
            "Expected to have new description field after set command, but we do not have it."

    finally:

        with allure.step("Unset description and verify"):
            eth0_port.interface.unset(op_param='description').verify_result()

        with allure.step('unset auto-save state'):
            system.config.auto_save.unset(op_param=SystemConsts.AUTO_SAVE_STATE, apply=True).verify_result()

        with allure.step('verify auto-save state is disabled'):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.config.auto_save.show()).verify_result()
            assert SystemConsts.AUTO_SAVE_STATE_DISABLED == output[
                SystemConsts.AUTO_SAVE_STATE], "state should be disabled"

            TestToolkit.GeneralApi[test_api].save_config(engine=engines.dut)
