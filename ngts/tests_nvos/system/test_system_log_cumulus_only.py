import allure
import pytest
import logging
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.SudoScope import sudo_scope_if

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.cumulus_only
def test_show_log_component_file_viewing(engines, devices):
    """
    Test flow:
        1. Run nv show system log file syslog.1 to view rotated log and verify output
        2. Run component file viewing (default) and verify output
        3. Run component file brief mode and verify output
        4. Run component file follow mode (timeout) and verify output (skipped for boot - not supported)
        5. Run component file list and view all files
        6. Run component file <file-name> and view a specific log file
    """

    with allure.step("Create System object"):
        system = System(None)

    test_components = _get_available_components(system)

    use_sudo = TestToolkit.is_eth_dut()

    with allure.step("Run nv show system log file syslog.1 to view rotated log and verify output"):
        system.log.rotate_logs()
        with sudo_scope_if(devices.dut.is_eth()):
            output = system.log.file.show_log(param='syslog.1', exit_cmd='q')
            ValidationTool.verify_expected_output(output, 'cumulus').verify_result()

    for component_name in test_components:
        component_file = system.log.component.component_id[component_name].file
        with allure.step(f"Run nv show system log component {component_name} file to view default log and verify output"):
            with sudo_scope_if(devices.dut.is_eth()):
                output = component_file.show_log(exit_cmd='q', expected_str='cumulus')
                ValidationTool.verify_expected_output(output, 'cumulus').verify_result()

        with allure.step(f"Run nv show system log component {component_name} file brief to view log and verify output"):
            with sudo_scope_if(devices.dut.is_eth()):
                output = component_file.show_log(exit_cmd='q', expected_str='cumulus', param='brief')
                ValidationTool.verify_expected_output(output, 'cumulus').verify_result()

        # Boot component does not support 'file follow' - show_log returns error; skip follow step for boot
        if component_name != 'boot':
            with allure.step(f"Run nv show system log component {component_name} file follow to view logs and verify output"):
                with sudo_scope_if(devices.dut.is_eth()):
                    output = component_file.show_log(param='follow', exit_cmd='\x03')
                    ValidationTool.verify_expected_output(output, 'cumulus').verify_result()

        with allure.step(f"Run nv show system log component {component_name} file list and verify output"):
            output = component_file.show(op_param='list')
            output = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
            if component_name != 'audit':
                for file_name in output.keys():
                    with allure.step(f"Run nv show system log component {component_name} file {file_name} and verify output"):
                        with sudo_scope_if(devices.dut.is_eth()):
                            output = component_file.show_log(param=file_name, exit_cmd='q')
                            ValidationTool.verify_expected_output(output, 'cumulus').verify_result()


@pytest.mark.system
@pytest.mark.cumulus_only
def test_log_idle_component(engines):
    """
    Test nv action rotate system log component <component-name> command specifically for Cumulus/ETH devices
    Commands tested:
    - nv action rotate system log component <component-name>

    Test flow:
        1. Get available components dynamically
        2. Test log rotation for each component
        3. Verify rotation was successful
    """
    with allure.step("Create System object"):
        system = System(None)

    test_components = _get_available_components(system)

    with allure.step("Rotate logs"):
        for component_name in test_components:
            with allure.step(f"Rotate logs for component: {component_name}"):
                if component_name not in ['audit', 'ifupdown2', 'installer', 'platform-thermal', 'stp']:
                    system.log.component.component_id[component_name].rotate_logs()


@pytest.mark.system
@pytest.mark.cumulus_only
def test_delete_log_component(engines, devices):
    """
    Test flow:
        1. Get available components dynamically
        2. Find components that actually have log files (via component file list API)
        3. Test file deletion only for components with files using action_delete API
        4. Verify deletion was successful by re-showing file list
    """
    with allure.step("Create System object"):
        system = System(None)

    test_components = _get_available_components(system)

    components_with_files = {}
    for component_name in test_components:
        with allure.step(f"Get file list for component: {component_name}"):
            component_file = system.log.component.component_id[component_name].file
            with sudo_scope_if(devices.dut.is_eth()):
                list_output = component_file.show(op_param='list')
                file_dict = OutputParsingTool.parse_json_str_to_dictionary(list_output).get_returned_value()
                # Endpoints return key -> value; use actual location from value['path'], not the key.
                file_entries = []
                for key, val in (file_dict or {}).items():
                    if isinstance(val, dict) and val.get('path'):
                        actual_path = val['path']
                        file_entries.append((key, actual_path))

                if file_entries:
                    components_with_files[component_name] = file_entries
                    logger.info("Found %d files for %s: %s", len(file_entries), component_name, [e[1] for e in file_entries])

    for component_name, file_entries in components_with_files.items():
        with allure.step(f"Test log file deletion for component: {component_name}"):
            component_file = system.log.component.component_id[component_name].file
            for list_key, file_identifier in file_entries:
                with allure.step(f"Delete file: {file_identifier}"):
                    component_file.file_id[file_identifier].action_delete()

                with allure.step(f"Verify {file_identifier} was deleted"):
                    with sudo_scope_if(devices.dut.is_eth()):
                        list_after = component_file.show(op_param='list')
                        files_after = OutputParsingTool.parse_json_str_to_dictionary(list_after).get_returned_value()
                        assert list_key not in (files_after or {}), (
                            f"File {list_key} was not actually deleted from component {component_name}"
                        )


def _get_available_components(system):
    components_output = system.log.component.show()
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(components_output).get_returned_value()
    return list(output_dictionary.keys())