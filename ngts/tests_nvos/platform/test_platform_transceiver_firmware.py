import logging
import pytest
import time
import re
from typing import Type
import random
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.tools.test_utils import allure_utils as allure
from retry import retry
from ngts.nvos_constants.constants_nvos import DatabaseConst
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_constants.constants_nvos import ApiType, SystemConsts, PlatformConsts
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.tests_nvos.platform.test_platform_transceiver import _get_ports_for_module
from ngts.tests_nvos.platform.constants import *
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_transceiver_database_tables(engines, devices, test_api):
    """
    Test Flow:
        1. get device transceiver list save as <transceivers_list>
        2. for each transceiver verify we have "TRANSCEIVER_FIRMWARE_INFO|InfiniBand<id>" under STATE_DB
    :param engines:
    :param test_api:
    :return:
    """
    with allure.step("Create platform object"):
        transceivers_tables_name = devices.dut.transceivers_tables_name
        number_of_transceivers = devices.dut.number_of_transceivers
        with allure.step("Validate for each transceiver out of {} transceivers we have the table in STATE_DB".format(number_of_transceivers)):
            tables_in_database = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=engines.dut, asic="",
                                                                          db_name=DatabaseConst.STATE_DB_NAME,
                                                                          grep_str=transceivers_tables_name).splitlines()
            assert number_of_transceivers == len(tables_in_database), \
                f"Test Failed: we expected {number_of_transceivers} transceivers tables in STATE_DB but we found {len(tables_in_database)}"


@pytest.mark.platform
@pytest.mark.transceiver
def test_reset_transceiver_firmware_positive(engines, test_api):
    """
        after reset transceiver firmware we expect the next behavior:
            1. for the physical-state of the interface link: LinkUp, Polling, LinkUp
            2. for the logical-state of the interface link: N/A, Down, Active
            3. for the transceiver firmware: No Data, [3 expected fields]

    Test Flow:
        1. Pick random connected module save as <random_sw> [nv show interface sw16p1 link -> cable-type:Optical module]
        2. Run nv action reset platform transceiver <random_sw>
        3. Run nv show platform transceiver <random_sw> firmware validate output = {}
        4. Run nv show interface <random_sw_p1> - validate: physical-state = LinkUp, logical-state = Down
        5. wait 1 seconds
        6. Run nv show platform transceiver <random_sw> firmware validate output includes all expected fields
        7. Run nv show interface <random_sw_p1> - validate: physical-state = Polling, logical-state = Down
        8. wait 1 seconds
        9. Run nv show interface <random_sw_ports>	Verify:"physical-state": "LinkUp", logical-state = up

    :param engines:
    :param test_api:
    :return:
    """
    platform, random_transceiver, random_port = _get_random_optical_module_transceiver()

    with allure.step("Create interface object"):
        interface = Interface(parent_obj=None, port_name=random_port)

    with allure.step(f"reset {random_transceiver} and verify expected behavior using show command"):
        link_output_before_reset = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
        default_output = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
        default_fw = OutputParsingTool.parse_json_str_to_dictionary(default_output).verify_result()[PlatformConsts.FW_ACTUAL]
        platform.transceiver.action_reset(random_transceiver).verify_result()

        with allure.step("sleep for 5 sec - waiting for after reset action"):
            time.sleep(8)

        with allure.step(f"verify all {random_transceiver} fields back to the same values"):
            output_after_reset = OutputParsingTool.parse_json_str_to_dictionary(output_json=platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
            _verify_expected_dict(output_after_reset, default_fw)

        with allure.step(f"verify all {random_port} link fields back to the same values"):
            link_output_after_reset = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
            link_output_before_reset = link_output_before_reset.pop('counters')
            link_output_after_reset = link_output_after_reset.pop('counters')
            check_counters(link_output_before_reset, link_output_after_reset)


@pytest.mark.timeout(30 * MINUTE, func_only=True)
@pytest.mark.platform
@pytest.mark.transceiver
def test_install_transceiver_firmware_positive(engines, devices, test_api, test_name):
    """
    Test Flow:
        1. Fetch 2 module FW images. Save as <FW1>و <FW2>
        2. Pick random connected module  	Save as <random_sw>
        3. Run nv action install platform transceiver <random_sw> firmware files <FW1>  	Action executing ... Action succeeded
        4. Verify Total installing Time	Between 1-2 min[using logs]
        5. Run nv show platform transceiver <random_sw> firmware	actual-firmware   <fw1>  fw-upgrade-status OK  fw-upgrade-error  N/A
        6. Run nv action install platform transceiver <random_sw> firmware files <FW2>  	Action executing ...  Action succeeded
        7. Run nv show platform transceiver <random_sw> firmware	actual-firmware   <fw2>  fw-upgrade-status OK  fw-upgrade-error  N/A
        8. Run nv show platform transceiver firmware files	fw1.bin    /host/fw-images/modules/fw1.bin  fw2.bin    /host/fw-images/modules/fw2.bin
        9. Run nv show platform transceiver <random_sw>  firmware files	fw1.bin    /host/fw-images/modules/fw1.bin  fw2.bin    /host/fw-images/modules/fw2.bin
        10. Pick randomly on of 1 or 2	<random_fw>
        11. Run nv show platform transceiver <random_sw> firmware <random_fw>	<random_fw>.bin    /host/fw-images/modules/<random_fw>.bin
        12. Run nv action reset platform transceiver <transceiver-id> Action executing ...  Action succeeded
        13. Run nv show platform transceiver <random_sw> firmware	actual-firmware   <default>  fw-upgrade-status OK  fw-upgrade-error  N/A
        14. Run nv show platform transceiver firmware	Fw1 ..
        15. Run nv show platform transceiver <random_sw>  firmware files
        16. Run nv show interface <random_sw_ports>	Verify: Verify:"physical-state": "LinkUp", logical-state = up
        17.  check all dict still the same
        18. Run nv action reset system factory-default
        19. Run nv show platform transceiver <random_sw>  firmware
        20. validate expected output
        21. Run nv show platform transceiver <random_sw>  firmware files
        22. validate expected output

    :param engines:
    :param test_api:
    :return:
    """

    platform, random_transceiver, random_port = _get_random_optical_module_transceiver()

    with allure.step(f"get the mst device for transceiver {random_transceiver}"):
        output_dictionary = OutputParsingTool.parse_show_interface_output_to_dictionary(
            Port.show_interface(fae_param='fae', port_names=random_port)).get_returned_value()
        pci_conf = output_dictionary[IbInterfaceConsts.PRIMARY_ASIC_DEVICE].split("/")
        mst_dev_name = IbInterfaceTool.get_mst_cable_name(engines.dut, random_transceiver, pci_conf[-1])

    default_fw = OutputParsingTool.parse_json_str_to_dictionary(
        platform.transceiver.show(random_transceiver + ' firmware')).verify_result()[PlatformConsts.FW_ACTUAL]

    with allure.step("Create interface object"):
        interface = Interface(parent_obj=None, port_name=random_port)

    with allure.step("Fetch 2 transceiver firmware files for {}, the actual firmware is {}".format(random_transceiver, default_fw)):
        player_engine = engines['sonic_mgmt']
        scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
        transceiver_id = default_fw.split('.')[0]
        transceiver_obj: Transceiver = TransceiversConsts.TRANSCEIVERS_DETAILS[transceiver_id]

        with allure.step("check module security level and update versions if needed"):
            if not IbInterfaceTool.is_dev_module(engines.dut, mst_dev_name):
                transceiver_obj.update_versions()

        downgrade_version_path = transceiver_obj.test_versions_path + transceiver_obj.downgrade_version_name
        upgrade_version_path = transceiver_obj.test_versions_path + transceiver_obj.upgrade_version_name

    with allure.step(f"try to downgrade and upgrade firmware for transceiver of type {transceiver_obj.transceiver_type}"):
        try:
            with allure.independent_step("fetch and downgrade transceiver firmware"):
                platform.firmware.transceiver.action_fetch(downgrade_version_path, base_url=scp_path).verify_result()
                result_obj, duration = OperationTime.save_duration("transceiver firmware installation",
                                                                   random_transceiver, test_name, platform.transceiver.action_install,
                                                                   random_transceiver, transceiver_obj.downgrade_version_name)
                OperationTime.verify_operation_time(duration, "transceiver firmware installation", transceiver_obj.installation_time).verify_result()

            with allure.step("run {} show link command".format(random_port)):
                show_interface_before_install = OutputParsingTool.parse_json_str_to_dictionary(
                    interface.link.show()).verify_result()

            with allure.step("verify show commands after install"):
                output_after_install = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
                _verify_expected_dict(command_output=output_after_install, default_fw=transceiver_obj.downgrade_version_number, status='OK', msg='N/A')
                show_interface_after_install = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
                link_output_before_reset = show_interface_before_install.pop('counters')
                link_output_after_reset = show_interface_after_install.pop('counters')
                check_counters(link_output_before_reset, link_output_after_reset)
        finally:
            with allure.independent_step("fetch and upgrade transceiver firmware"):
                platform.firmware.transceiver.action_fetch(upgrade_version_path, base_url=scp_path).verify_result()
                platform.transceiver.action_install(random_transceiver, transceiver_obj.upgrade_version_name).verify_result()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_install_reset_transceiver_firmware_negative_flow(engines, test_api):
    """
    Test flow:
        1. Pick random connected module  	Save as <random_sw>
        2. Generate bad FW.bin file – after fetch …   	Save as <bad_FW>
        3. Run nv action install platform transceiver <random_sw> firmware files <bad_FW>	Action executing ...  Resetting module <random_sw>  ... Failed  Action failed
        4. Pick random unconnected module  	Save as <bad_random_sw>
        5. Run nv action install platform transceiver <bad_random_sw> firmware files <bad_FW>	Action executing ...  Resetting module <random_sw>  ... Failed  Action failed
        6. Run nv show platform transceiver <random_sw>  firmware files
        7. Run nv show interface <random_sw_ports>	Verify: physical-state": "LinkUp", logical-state = up

    :param engines:
    :param test_api:
    :return:
    """
    invalid_file = "invalid_fw.bin"
    invalid_fw_path = f"{SystemConsts.GENERAL_TRANSCEIVER_FIRMWARE_FILES}/{invalid_file}"
    expected_error_msg = 'Failed to complete download of FW image to EEPROM'

    platform, random_transceiver, random_port = _get_random_optical_module_transceiver()

    with allure.step(f"Run nv show platform transceiver {random_transceiver}"):
        output_before_install = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()

    with allure.step("fetch firmware transceiver file {} switch".format(invalid_file)):
        player_engine = engines['sonic_mgmt']
        scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
        platform.firmware.transceiver.action_fetch(invalid_fw_path, base_url=scp_path).verify_result()

    with allure.step("Create interface object"):
        interface = Interface(parent_obj=None, port_name=random_port)
        show_interface_before_install = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()

    with allure.step("install new transceiver firmware - {}".format(invalid_file)):
        platform.transceiver.action_install(random_transceiver, invalid_file, expected_str=expected_error_msg).verify_result(should_succeed=False)

    with allure.step("verify show commands after install"):
        time.sleep(20)
        show_interface_after_install = OutputParsingTool.parse_json_str_to_dictionary(
            interface.link.show()).verify_result()
        output_after_install = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()

        show_interface_before_install.pop('counters')
        show_interface_after_install.pop('counters')

        with allure.independent_step("validate the output of transceiver firmware command"):
            assert output_before_install == output_after_install, f"at elast one of the transceiver fields has been change, before installaion {output_before_install}, after instalaaion {output_after_install}"
        with allure.independent_step("validate the output of interface links command"):
            assert show_interface_after_install == show_interface_before_install, "at least one of the link values has been change, before_install {} after install {}".format(show_interface_before_install, show_interface_after_install)


@pytest.mark.platform
@pytest.mark.transceiver
def test_install_reset_invalid_transceiver_id(engines, test_api):
    """
    Test flow:
        1. Run nv action reset platform transceiver <Invalid_transceiver-id >.
        2. Run nv show platform transceiver <Invalid_Transceiver-id > firmware.
        3. Run nv show platform transceiver <Invalid_Transceiver-id > firmware files.
        4. Run nv show platform transceiver <Invalid_Transceiver-id> firmware files <Invalid_filename>
        5. Run nv action install platform transceiver <Invalid_transceiver-id -id> firmware files <Invalid_filename>
        6. verify all commands failed with the expected error message

    :param engines:
    :param test_api:
    :return:
    """
    with allure.step("Create platform object"):
        platform = Platform()
        invalid_transceiver = 'testing'
        invalid_file_name = 'no_file'
        invalid_transceiver_expected_output = "'testing' is not a 'transceiver-name'"
        invalid_file_expected_output = "no_file not found"

    with allure.step("try to run transceiver commands with invalid transceiver id and non exist file"):
        with allure.independent_step("Install non exist file"):
            platform, random_transceiver, random_port = _get_random_optical_module_transceiver()
            platform.transceiver.action_install(random_transceiver, invalid_file_name, expected_str=invalid_file_expected_output).verify_result()
        with allure.independent_step("Install invalid transceiver and non exist file"):
            platform.transceiver.action_install(invalid_transceiver, invalid_file_name, expected_str=invalid_transceiver_expected_output).verify_result()
        with allure.independent_step("Reset invalid transceiver"):
            platform.transceiver.action_reset(invalid_transceiver, expected_str=invalid_transceiver_expected_output).verify_result()
        with allure.independent_step("Show invalid_transceiver firmware"):
            assert invalid_transceiver_expected_output in platform.transceiver.show(invalid_transceiver + ' firmware', should_succeed=False), "The show firmware command succeeded when it was expected to fail"
        with allure.independent_step("Show invalid_transceiver and non exist file"):
            assert invalid_transceiver_expected_output in platform.transceiver.show(invalid_transceiver + ' firmware files ' + invalid_file_name, should_succeed=False), "The show firmware files command succeeded when it was expected to fail"
        with allure.independent_step("Show invalid_transceiver"):
            assert invalid_transceiver_expected_output in platform.transceiver.show(invalid_transceiver, should_succeed=False), "The show transceiver command succeeded when it was expected to fail"


@retry(Exception, tries=60, delay=1)
def _wait_until_linkup(interface):
    show_interface_output = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
    _verify_logic_and_physical_state(show_interface_output, IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE,
                                     IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP)


def _verify_logic_and_physical_state(show_interface_output, link_state, physical_state):
    """
    :param show_interface_output:
    :param link_state:
    :param physical_state:
    :return:
    """
    with allure.step("verify  {} = {}, {} = {}".format(IbInterfaceConsts.LINK_LOGICAL_PORT_STATE, link_state,
                                                       IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE, physical_state)):
        assert show_interface_output[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE] == link_state, "the {} is {} not {} as expected".format(IbInterfaceConsts.LINK_LOGICAL_PORT_STATE, show_interface_output[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE], link_state)
        assert show_interface_output[IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE] == physical_state, "the {} is {} not {} as expected".format(IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE, show_interface_output[IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE], physical_state)


def _verify_expected_dict(command_output, default_fw, status='N/A', msg='N/A'):
    """
    :param command_output:
    :param default_fw:
    :param status:
    :param msg:
    :return:
    """
    with allure.step("verify actual-firmware = {}, status = {}, error_msg = {}".format(default_fw, status, msg)):
        expected_dict = {
            PlatformConsts.FW_ACTUAL: default_fw,
            PlatformConsts.FW_UPGRADE_STATUS: status,
            PlatformConsts.FW_UPGRADE_ERROR_MSG: msg
        }

        assert command_output == expected_dict, "at least one of the values is not as expected {}".format(command_output)


def _get_random_optical_module_transceiver():
    """

    :return:
    """
    with allure.step("Get random optical module transceiver"):
        with allure.step("Create platform object"):
            platform = Platform()

        with allure.step("pick random connected optical module"):
            show_transceiver = OutputParsingTool.parse_json_str_to_dictionary(
                platform.transceiver.show_detailed()).verify_result()
            random_transceiver = \
                RandomizationTool.select_random_transceiver(transceivers_output=show_transceiver, field_name=PlatformConsts.TRANSCEIVER_CABLE_TYPE,
                                                            expected_value='Optical module', number_of_transceiver_to_select=1).ignore_result()
            if not random_transceiver.result:
                random_transceiver = \
                    RandomizationTool.select_random_transceiver(transceivers_output=show_transceiver,
                                                                field_name=PlatformConsts.HARDWARE_TRANCEIVER_DIAGNOSTIC_STATUS,
                                                                expected_value='Diagnostic Data Available',
                                                                number_of_transceiver_to_select=1).ignore_result()

            if not random_transceiver.result:
                pytest.skip(f"No optical modules available for the setup")
            else:
                random_transceiver = random_transceiver.verify_result()[0]

            if IbInterfaceConsts.FNM_PORT_TYPE in random_transceiver:
                return platform, random_transceiver, random_transceiver + random_transceiver

            temp = _get_ports_for_module(random_transceiver)
            random_port_name = random.choice(temp)

        return platform, random_transceiver, random_port_name.name


def check_counters(counters_before, counters_after):
    """

    :param counters_before:
    :param counters_after:
    :return:
    """
    changes = []
    err_msg = ""
    with allure.step("Verify that no keys are missing after action"):
        assert counters_before.keys() == counters_after.keys()

    with allure.step("Validate that none of the counters have changed by more than 20%"):
        for key, before_value in counters_before.items():
            if counters_before[key] and counters_after[key] - counters_before[key] > counters_before[key] * 0.2:
                changes.append({
                    'key': key,
                    'before': counters_before[key],
                    'after': counters_after[key],
                })

        if changes:
            for change in changes:
                err_msg += f"Key: {change['key']}, Before: {change['before']}, After: {change['after']}"

        assert not changes, err_msg
