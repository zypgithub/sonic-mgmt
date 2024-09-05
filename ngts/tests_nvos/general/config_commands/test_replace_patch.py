import time
import pytest
import os
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst, OutputFormat
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts


@pytest.mark.cumulus
@pytest.mark.general
@pytest.mark.simx
def test_replace_empty_file(engines):
    """
    Test flow:
        1. run nv set system hostname <new_hostname>
        2. create empty file <file.yaml>
        3. run nv config replace <file.yaml>
        4. run nv config diff save as diff_1
        5. verify diff_1 is empty
    """
    file_name = 'replace'
    file_type = 'yaml'
    try:
        system = System()
        new_hostname_value = 'TestingConfigCmds1'
        with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
            system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

        with allure.step("Check pending config before replacing with empty file"):
            OutputParsingTool.parse_json_str_to_dictionary(NvueGeneralCli.diff_config(engines.dut)).get_returned_value()

        with allure.step("Create empty yml file and replace config using it"):
            file = create_empty_file(engines.dut, file_name, file_type)
            TestToolkit.GeneralApi[TestToolkit.tested_api].replace_config(engines.dut, file)

        with allure.step("Check pending config"):
            diff_after_hostname_change = OutputParsingTool.parse_json_str_to_dictionary(
                NvueGeneralCli.diff_config(engines.dut)).get_returned_value()

        with allure.step('Verify the pending config'):
            set_comp = {k: v for comp in diff_after_hostname_change for k, v in comp.get("set", {}).items()}
            assert not set_comp, "Set should not be found in pending config after replacing with an empty config file"
    finally:
        engines.dut.run_cmd('sudo rm {file}.{type}'.format(file=file_name, type=file_type))


@pytest.mark.general
@pytest.mark.simx
def test_replace_positive(engines, devices):
    """

    Test flow:
        - run nv set system hostname <new_hostname> without apply
        - run nv config diff -o=yaml and save as <file_1>
        - run nv system hostname <new_hostname_1> without apply
        - run nv set interface ib0 description <new_description>
        - run nv config diff save as <diff_1>
        - run nv config replace <file_1>
        - run nv config diff save as <diff_2>
        - run nv config apply
        - verify hostname = <new_hostname_1>
        - verify ib0 description is empty (default value)
        - run unset hostname + apply
    """
    system = System()

    first_hostname = 'TestingConfigCmds2'
    with allure.step('set hostname to be {hostname} - without apply'.format(hostname=first_hostname)):
        system.set(SystemConsts.HOSTNAME, first_hostname, apply=False)
        config_after_hostname_change = NvueGeneralCli.show_config(engines.dut)

    new_hostname_value = 'TestingConfigReplace'
    with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
        system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

    ib0_port = MgmtPort('ib0')
    OutputParsingTool.parse_show_interface_output_to_dictionary(ib0_port.interface.show()).get_returned_value()

    new_ib0_description = '"ib0description"'
    with allure.step('set ib0 description to be {description} - with apply'.format(
            description=new_ib0_description)):
        ib0_port.interface.set(NvosConst.DESCRIPTION, new_ib0_description, apply=True, ask_for_confirmation=True).verify_result()

    with allure.step("Replace config"):
        config_after_hostname_change = config_after_hostname_change.replace('"password": "*"',
                                                                            '"password": "{passw}"'.format(passw=devices.dut.default_password))
        file = create_file_with_content(engines.dut, 'replace', 'yaml', config_after_hostname_change)
        output = TestToolkit.GeneralApi[TestToolkit.tested_api].replace_config(engines.dut, file)
        expected_message = "Loading config file: replace.yaml from current directory."
        assert expected_message in output, "Failed to replace config"

    with allure.step("Delete created yaml file: {}".format(file)):
        engines.dut.run_cmd('sudo rm {file}'.format(file=file))

    with allure.step('verify the hostname is not{hostname} and ib0 description is not {description}'.format(hostname=new_hostname_value, description=new_ib0_description)):
        diff_json = OutputParsingTool.parse_json_str_to_dictionary(NvueGeneralCli.diff_config(engines.dut)).get_returned_value()
        set_diff = next((sub_d for sub_d in diff_json if "set" in sub_d), None)
        assert not set_diff or not ValidationTool.has_key_with_value(set_diff, 'hostname',
                                                                     new_hostname_value), "Set system hostname can't be found in pending config"
        assert not set_diff or not ValidationTool.has_key_with_value(set_diff, "description",
                                                                     new_ib0_description), "Set ib0 description can't be found in pending config"


@pytest.mark.cumulus
@pytest.mark.general
@pytest.mark.simx
def test_replace_negative(engines):
    """

    Test flow:
        - run nv set system hostname <new_hostname> without apply
        - run nv config diff -o=yaml and save as <file>
        - create invalid yaml files using <file>
        - run nv config replace <file_1> (Failed to parse YAML)
        - verify expected error message
        - run nv config replace <file_2> (NVUE file must contain a list of operation objects)
        - verify expected error message
        - run nv config replace <file_3> (bad path)
        - verify expected error message
    """
    system = System()

    file_name = 'replace'
    file_type = 'yaml'

    new_hostname_value = 'TestingConfigCmds3'
    with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
        system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

        content = NvueGeneralCli.diff_config(engines.dut, output_type=OutputFormat.yaml)

    parsing_issue, bad_file = create_list_of_bad_files(engines.dut, file_name, file_type, content)
    output1 = engines.dut.run_cmd('nv config replace {file}'.format(file=parsing_issue))
    output2 = engines.dut.run_cmd('nv config replace {file}'.format(file=bad_file))

    engines.dut.run_cmd('sudo rm {file}'.format(file=parsing_issue))
    engines.dut.run_cmd('sudo rm {file}'.format(file=bad_file))

    assert 'Failed to parse YAML' in output1, 'the replace should fail'
    assert 'must contain a list of operation objects' in output2, 'the replace should fail'


@pytest.mark.cumulus
@pytest.mark.general
@pytest.mark.simx
def test_patch_empty_file(engines):
    """
    Test flow:
        1. run nv set system hostname <new_hostname>
        2. run nv config diff save as diff_1
        2. create empty file <file.yaml>
        3. run nv config patch <file.yaml>
        4. run nv config diff save as diff_2
        5. verify diff_1 is equal to diff_2
    """
    with allure.step('Run show system command and verify that each field has a value'):
        system = System()
        new_hostname_value = 'TestingConfigPatchCmds4'
        with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
            system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

        diff_after_hostname_change = OutputParsingTool.parse_json_str_to_dictionary(
            NvueGeneralCli.diff_config(engines.dut)).get_returned_value()

        file_name = 'patch'
        file_type = 'yaml'
        file = create_empty_file(engines.dut, file_name, file_type)
        engines.dut.run_cmd('nv config patch {file}'.format(file=file))

        diff_after_patch = OutputParsingTool.parse_json_str_to_dictionary(NvueGeneralCli.diff_config(engines.dut)) \
            .get_returned_value()

        engines.dut.run_cmd('sudo rm {file}.{type}'.format(file=file_name, type=file_type))

        with allure.step('verify the pending file does not change'):
            assert diff_after_hostname_change == diff_after_patch, "pending revision should not change"


@pytest.mark.general
@pytest.mark.simx
def test_patch_positive(engines):
    """

        Test flow:
            - run nv set system hostname <new_hostname> without apply
            - run nv config diff -o=yaml and save as <file_1>
            - run nv system hostname <new_hostname_1> without apply
            - run nv set interface ib0 description <new_description>
            - run nv config diff save as <diff_1>
            - run nv config replace <file_1>
            - run nv config diff save as <diff_2>
            - run nv config apply
            - verify hostname = <new_hostname_1>
            - verify ib0 description is empty (default value)
            - run unset hostname + apply
        - case1 : maybe it's good to create empty yaml file and verify the nv config diff is empty
        """
    with allure.step('Run nv config replace and verify that the pending list is changed'):
        system = System()

        first_hostname = 'TestingConfigCmds5'
        with allure.step('set hostname to be {hostname} - without apply'.format(hostname=first_hostname)):
            system.set(SystemConsts.HOSTNAME, first_hostname, apply=False)

        diff_after_hostname_change = NvueGeneralCli.diff_config(engines.dut)

        new_hostname_value = 'TestingConfigPatch'
        with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
            system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

        ib0_port = MgmtPort('ib0')
        new_ib0_description = 'TEST'
        with allure.step('set ib0 description to be {description} - with apply'.format(
                description=new_ib0_description)):
            ib0_port.interface.set(NvosConst.DESCRIPTION, new_ib0_description, apply=True, ask_for_confirmation=True).verify_result()

        file_name = 'patch'
        file_type = 'yaml'
        file = create_file_with_content(engines.dut, file_name, file_type, diff_after_hostname_change)
        TestToolkit.GeneralApi[TestToolkit.tested_api].patch_config(engines.dut, file)

        engines.dut.run_cmd('sudo rm {file}'.format(file=file))
        NvueGeneralCli.apply_config(engines.dut, True)
        time.sleep(3)
        with allure.step('verify the hostname is {hostname} and ib0 description is {description}'.format(hostname=new_hostname_value, description=new_ib0_description)):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, SystemConsts.HOSTNAME,
                                                        first_hostname).verify_result()

            output_dictionary = OutputParsingTool.parse_show_interface_output_to_dictionary(
                ib0_port.interface.show()).get_returned_value()

            ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                        field_name=NvosConst.DESCRIPTION,
                                                        expected_value=new_ib0_description).verify_result()
            ib0_port.interface.unset(NvosConst.DESCRIPTION, apply=False).verify_result()
            system.unset(SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.general
@pytest.mark.simx
def test_patch_negative(engines):
    """

    Test flow:
        - run nv set system hostname <new_hostname> without apply
        - run nv config diff -o=yaml and save as <file>
        - create invalid yaml files using <file>
        - run nv config replace <file_1> (Failed to parse YAML)
        - verify expected error message
        - run nv config replace <file_2> (NVUE file must contain a list of operation objects)
        - verify expected error message
        - run nv config replace <file_3> (bad path)
        - verify expected error message
    """
    system = System()

    file_name = 'patch'
    file_type = 'yaml'

    new_hostname_value = 'TestingConfigPatchCmds6'
    with allure.step('set hostname to be {hostname} - without apply'.format(hostname=new_hostname_value)):
        system.set(SystemConsts.HOSTNAME, new_hostname_value, apply=False)

        content = NvueGeneralCli.diff_config(engines.dut, output_type=OutputFormat.yaml)

    parsing_issue, bad_file = create_list_of_bad_files(engines.dut, file_name, file_type, content)

    output1 = engines.dut.run_cmd('nv config replace {file}'.format(file=parsing_issue))
    output2 = engines.dut.run_cmd('nv config patch {file}'.format(file=bad_file))

    engines.dut.run_cmd('sudo rm {file}'.format(file=parsing_issue))
    engines.dut.run_cmd('sudo rm {file}'.format(file=bad_file))

    assert 'Failed to parse YAML' in output1, 'the replace should fail'
    assert 'must contain a list of operation objects' in output2, 'the replace should fail'


def create_empty_file(engine, file_name, file_type):
    with allure.step('create empty file {file_name}.{file_type}'.format(file_name=file_name, file_type=file_type)):
        f = '{file_name}.{file_type}'.format(file_name=file_name, file_type=file_type)
        engine.run_cmd('sudo touch ' + f)
        return f


def create_file_with_content(engine, file_name, file_type, content):
    with allure.step('creating yaml file with content'):
        engine.run_cmd('echo "{content}" | tee -a {file_name}.{file_type}'.format(content=content, file_type=file_type,
                                                                                  file_name=file_name))
        return '{file_name}.{file_type}'.format(file_type=file_type, file_name=file_name)


def create_list_of_bad_files(engine, file_name, file_type, content):
    """

    :param engine:
    :param file_name:
    :param file_type:
    :param content:
    :return:
    """
    with allure.step('create bad yaml files for replace and patch'):
        parssing_issue = create_file_with_content(engine, file_name + '_1', file_type, content + ' \n \n AAAAA')
        content = ' {}  '
        non_operation = create_file_with_content(engine, file_name + '_2', file_type, content)
        return parssing_issue, non_operation
