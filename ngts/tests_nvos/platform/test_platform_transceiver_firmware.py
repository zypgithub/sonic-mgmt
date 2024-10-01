import logging
import pytest
import time
import re

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

logger = logging.getLogger()


@pytest.mark.timeout(5 * MINUTE, func_only=True)
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
        platform = Platform()
        transceivers_tables_name = "TRANSCEIVER_FIRMWARE_INFO"
        transceivers_list = list(OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show()).returned_value.keys())
        number_of_transceivers = len(transceivers_list) * 2
        with allure.step("Validate for each transceiver out of {} transceivers we have the table in STATE_DB".format(number_of_transceivers)):
            tables_in_database = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=engines.dut, asic="",
                                                                          db_name=DatabaseConst.STATE_DB_NAME,
                                                                          grep_str=transceivers_tables_name).splitlines()
            assert number_of_transceivers == len(tables_in_database), "Test Failed: we expected {} transceivers tables in STATE_DB but we found only {}".format(len(number_of_transceivers), len(tables_in_database))


@pytest.mark.timeout(10 * MINUTE, func_only=True)
@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_reset_transceiver_firmware_positive(engines, test_api, start_sm):
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

    with allure.step("reset {} and verify expected behavior using show command"):
        link_output_before_reset = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
        default_output = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
        default_fw = OutputParsingTool.parse_json_str_to_dictionary(default_output).verify_result()[PlatformConsts.FW_ACTUAL]
        platform.transceiver.action_reset(random_transceiver).verify_result()

        with allure.step("sleep for 2 sec - waiting for after reset action"):
            time.sleep(2)

        with allure.step(f"verify all {random_transceiver} fields back to the same values"):
            output_after_reset = OutputParsingTool.parse_json_str_to_dictionary(output_json=platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
            _verify_expected_dict(output_after_reset, default_fw)

        with allure.step(f"verify all {random_port} link fields back to the same values"):
            start_sm
            link_output_after_reset = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
            link_output_before_reset = link_output_before_reset.pop('counters')
            link_output_after_reset = link_output_after_reset.pop('counters')
            assert link_output_after_reset == link_output_before_reset, "at least ont field has been changed, output before reset = {} , output after reset = {}".format(link_output_before_reset, link_output_after_reset)


@pytest.mark.timeout(10 * MINUTE, func_only=True)
@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_install_transceiver_firmware_positive(engines, devices, test_api, start_sm):
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
    default_fw = OutputParsingTool.parse_json_str_to_dictionary(
        platform.transceiver.show(random_transceiver + ' firmware')).verify_result()[PlatformConsts.FW_ACTUAL]

    try:
        with allure.step("Create interface object"):
            interface = Interface(parent_obj=None, port_name=random_port)

        with allure.step("Fetch 2 transceiver firmware files for {}, the actual firmware is {}".format(random_transceiver, default_fw)):
            player_engine = engines['sonic_mgmt']
            paths, bin_files = _find_transceiver_firmware_file_path(player=player_engine, default_fw=default_fw, number_of_files=2)
            scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
            fw_path_1 = f"{paths[0]}/{bin_files[0]}"
            fw_path_2 = f"{paths[1]}/{bin_files[1]}"
            platform.firmware.transceiver.action_fetch(fw_path_1, base_url=scp_path).verify_result()
            platform.firmware.transceiver.action_fetch(fw_path_2, base_url=scp_path).verify_result()

        with allure.step("run {} show link command".format(random_port)):
            show_interface_before_install = OutputParsingTool.parse_json_str_to_dictionary(
                interface.link.show()).verify_result()

        with allure.step("install new transceiver firmware - {}".format(bin_files[0])):
            platform.transceiver.action_install(random_transceiver, bin_files[0]).verify_result()
            platform.transceiver.action_reset(random_transceiver)

        with allure.step("verify show commands after install"):
            output_after_install = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
            _verify_expected_dict(command_output=output_after_install, default_fw=_get_firmware(bin_files[0]), status='OK', msg='N/A')

            show_interface_after_install = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()
            assert show_interface_before_install == show_interface_after_install, "at lease one of the link values has been change, output before install = {}, after install = {}".format(show_interface_before_install, show_interface_after_install)
    finally:
        _cleanup_step(engines.dut, engines['sonic_mgmt'], platform, random_transceiver, default_fw)


@pytest.mark.timeout(10 * MINUTE, func_only=True)
@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
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

    with allure.step("fetch firmware transceiver file {} switch".format(invalid_file)):
        player_engine = engines['sonic_mgmt']
        scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
        platform.firmware.transceiver.action_fetch(invalid_fw_path, base_url=scp_path).verify_result()
        default_fw = OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(random_transceiver + ' firmware')).verify_result()[PlatformConsts.FW_ACTUAL]

    try:
        with allure.step("Create interface object"):
            interface = Interface(parent_obj=None, port_name=random_port)
            show_interface_before_install = OutputParsingTool.parse_json_str_to_dictionary(interface.link.show()).verify_result()

        with allure.step("install new transceiver firmware - {}".format(invalid_file)):
            platform.transceiver.action_install(random_transceiver, invalid_file, expected_str=expected_error_msg)
            platform.transceiver.action_reset(random_transceiver)

        with allure.step("verify show commands after install"):
            show_interface_after_install = OutputParsingTool.parse_json_str_to_dictionary(
                interface.link.show()).verify_result()
            output_after_install = OutputParsingTool.parse_json_str_to_dictionary(platform.transceiver.show(random_transceiver + ' firmware')).verify_result()
            _verify_expected_dict(command_output=output_after_install, default_fw='N/A', status='Failed', msg=expected_error_msg)
            assert show_interface_after_install == show_interface_before_install, "at least one of the link values has been change, before_install {} after install {}".format(show_interface_before_install, show_interface_after_install)

    finally:
        _cleanup_step(engines.dut, engines['sonic_mgmt'], platform, random_transceiver, default_fw)


@pytest.mark.timeout(5 * MINUTE, func_only=True)
@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
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
        invalid_action_expected_output = "Module testing does not exist"
        invalid_show_expected_output = 'Error: The requested item does not exist'

    with allure.step("try to run transceiver commands with invalid transceiver id and non exist file"):
        platform.transceiver.action_install(invalid_transceiver, invalid_file_name, expected_str=invalid_action_expected_output)
        platform.transceiver.action_reset(invalid_transceiver, expected_str=invalid_action_expected_output)
        assert invalid_show_expected_output in platform.transceiver.show(invalid_transceiver + ' firmware', should_succeed=False), "The show firmware command succeeded when it was expected to fail"
        assert invalid_show_expected_output in platform.transceiver.show(invalid_transceiver + ' firmware files ' + invalid_file_name, should_succeed=False), "The show firmware files command succeeded when it was expected to fail"
        assert invalid_show_expected_output in platform.transceiver.show(invalid_transceiver, should_succeed=False), "The show transceiver command succeeded when it was expected to fail"


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


def _find_transceiver_firmware_file_path(player, default_fw, number_of_files=1):
    """
    :summary: example of transceiver firmware path:
    <base_path>/46_Bagheera1_2/120_10_release/rel-46_120_10010/signed/sec_issu_46_120_10010_dev_signed.bin.

    :param player:
    :param default_fw: transceiver default fw
    :param number_of_files:
    :return:
    """

    with allure.step("find {} transceiver firmware files to support transceiver with default firmware {}".format(number_of_files, default_fw)):
        base_path = "/.autodirect/sw/release/fwshared/linkx/mlnx_linkx_module_aoc_fw"

        type_id, release_id, current_version = default_fw.split('.')
        folder_name = _get_folder_name(engine=player, path=base_path, pattern=type_id, condition='S')
        path = base_path + '/' + folder_name[0]
        folder_name = _get_folder_name(player, path, release_id, 'S')
        path += '/' + folder_name[0]
        folder_name = _get_folder_name(player, path, 'rel', 'S', folders_count=number_of_files)
        paths = [path + '/' + folder + '/' + 'signed/' for folder in folder_name]
        bin_files = []
        for path in paths:
            bin_files.append(_get_folder_name(player, path, '.bin', 'E')[0])

        return paths, bin_files


def _get_folder_name(engine, path, pattern, condition, folders_count=1):
    with allure.step("trying to find {} files from {} that includes {} under condition {}".format(folders_count, path, pattern, condition)):
        types_list = engine.run_cmd('ls {}'.format(path))
        split_string = re.split(r'\n|\t| ', types_list)
        split_string = list(filter(None, split_string))
        if condition is 'S':
            matching_type_folders = [folder for folder in split_string if folder.startswith(pattern)]
        else:
            matching_type_folders = [folder for folder in split_string if folder.endswith(pattern)]

        assert matching_type_folders, "No matching {} folder found".format(pattern)
        assert len(matching_type_folders) >= folders_count, "only {} folders are exist, and we asked for {}".format(len(matching_type_folders), folders_count)

        return matching_type_folders[-folders_count:]


def _get_firmware(file_name):
    with allure.step(""):
        pattern = r"fw_(\d+)_(\d+)_(\d+)_dev_signed\.bin"
        match = re.search(pattern, file_name)

        if match:
            version_numbers = match.groups()
            version_numbers = [str(int(num)) if index == 2 else num for index, num in enumerate(version_numbers)]
            version_string = ".".join(version_numbers)
            return version_string
        else:
            return None


def _get_random_optical_module_transceiver():
    """

    :return:
    """
    with allure.step("Get random optical module transceiver"):
        with allure.step("Create platform object"):
            platform = Platform()

        with allure.step("pick random connected optical module"):
            show_transceiver = OutputParsingTool.parse_json_str_to_dictionary(
                platform.transceiver.show()).verify_result()
            random_transceiver = \
                RandomizationTool.select_random_transceiver(transceivers_output=show_transceiver, field_name=PlatformConsts.TRANSCEIVER_CABLE_TYPE,
                                                            expected_value='Optical module', number_of_transceiver_to_select=1)
            if not random_transceiver.result:
                random_transceiver = \
                    RandomizationTool.select_random_transceiver(transceivers_output=show_transceiver,
                                                                field_name=PlatformConsts.HARDWARE_TRANCEIVER_DIAGNOSTIC_STATUS,
                                                                expected_value='Diagnostic Data Available',
                                                                number_of_transceiver_to_select=1).verify_result()[0]
            else:
                random_transceiver = random_transceiver.verify_result()[0]

            random_port_name = random_transceiver + 'p1'

        return platform, random_transceiver, random_port_name


def _cleanup_step(engine, player_engine, platform, transceiver_id, default_fw):
    """
    to delete all fetched files and reinstall default fw
    - run nv show platform transceiver <transceiver_id> firmware
    - if the firmware != default_fw, then we need to install the <default_fw>
    - run nv action delete platform firmware transceiver files
    :return:
    """
    with allure.step("cleanup steps"):
        with allure.step("re-install default fw if needed"):
            current_fw = OutputParsingTool.parse_json_str_to_dictionary(
                platform.transceiver.show(transceiver_id + ' firmware')).verify_result()[PlatformConsts.FW_ACTUAL]
            if current_fw != default_fw:
                with allure.step("install the default fw {} because the current fw is {}".format(default_fw, current_fw)):
                    default_fw_path, default_bin_file = _find_transceiver_firmware_file_path(player=player_engine, default_fw=default_fw, number_of_files=1)
                    with allure.step("fetch file from {}".format(default_fw_path[0])):
                        fw_path_1 = f"{default_fw_path[0]}/{default_bin_file[0]}"
                        platform.firmware.transceiver.action_fetch(fw_path_1).verify_result()

                    with allure.step("install new transceiver firmware - {}".format(default_bin_file[0])):
                        platform.transceiver.action_install(transceiver_id, default_bin_file[0]).verify_result()
                        platform.transceiver.action_reset(transceiver_id)

        with allure.step("delete all fetched files"):
            path = "/host/fw-images/module"
            engine.run_cmd(f"sudo rm -f {path}/*")
