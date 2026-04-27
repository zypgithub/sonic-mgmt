import logging

from retry import retry

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli

logger = logging.getLogger(__name__)

ZTP_DATA_LOCAL_JSON = '/host/ztp/ztp_data_local.json'


def download_ztp_json_config(engines, json=''):
    engines.dut.run_cmd(f'sudo rm -f {ZTP_DATA_LOCAL_JSON}')
    return engines.dut.run_cmd(
        f'sudo curl {SystemConsts.HTTP_SERVER}{SystemConsts.VERIFICATION_ZTP_PATH}{json} '
        f'-o {ZTP_DATA_LOCAL_JSON}')


def download_file_and_run_ztp(engines, system, file='', step='', step_status_code=SystemConsts.ZTP_STATUS_SUCCESS,
                              ztp_status_code=SystemConsts.ZTP_STATUS_SUCCESS):
    with allure.step("Download json file"):
        download_ztp_json_config(engines, file)

        with allure.step("Check ztp status"):
            wait_until_ztp_step_status(system, step, step_status_code)
            wait_until_ztp_status(system, ztp_status_code)


def apply_empty_config_and_save(engines):
    """Apply empty config and save so next ZTP run is not bypassed (config already applied/saved)."""
    NvueGeneralCli.apply_config(engine=engines.dut, rev_id='empty', option='-y')
    NvueGeneralCli.save_config(engine=engines.dut)


def run_system_ztp_with_empty_config(engines, system):
    with allure.step("Run nv action run system ztp"):
        apply_empty_config_and_save(engines)
        system.ztp.action_run_ztp().verify_result()


def validate_ztp_log_file(engines, string_to_validate=''):
    output = engines.dut.run_cmd(f'cat /var/log/ztp.log | grep "{string_to_validate}"')
    assert string_to_validate in output, 'String not in ztp log'


def wait_until_ztp_status(system, ztp_status='', is_on_air: bool = False):
    @retry(Exception, tries=30, delay=5 if is_on_air else 2)
    def wait_for_ztp_status():
        ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
        assert ztp_output['status'] == ztp_status, f'ztp status not changed to {ztp_status}'

    with allure.step("Waiting for ztp status changed to status {}".format(ztp_status)):
        wait_for_ztp_status()


def wait_until_ztp_step_status(system, ztp_step='', ztp_status='', tries=30, delay=2):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(system_obj, ztp_step_name='', ztp_status_name=''):
        with allure.step("Waiting for ztp status changed to status {}".format(ztp_status_name)):
            ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system_obj.ztp.show()).get_returned_value()
            assert ztp_output['stage'][ztp_step_name]['status'] == ztp_status_name, \
                f'ztp status not changed to {ztp_status_name}'

    _retry_decorator(system, ztp_step, ztp_status)


def validate_interface_description_field(selected_port, description_value, should_be_equal=True):
    with allure.step('Check that interface description field matches the expected value'):
        output_dictionary = selected_port.show_output_dictionary
        if NvosConst.DESCRIPTION in output_dictionary.keys():
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary, NvosConst.DESCRIPTION,
                                                              description_value).verify_result(should_be_equal)


def wait_until_ztp_values_fields_changed(system, ztp_output_fields, ztp_output_values, tries=30, delay=3):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(system_obj, ztp_step_name='', ztp_status_name=''):
        with allure.step("Run show ztp and verify default values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

        with allure.step("Verify default values and fields"):
            ValidationTool.validate_fields_values_in_output(ztp_output_fields, ztp_output_values,
                                                            system_ztp_output).verify_result()

    _retry_decorator(system, ztp_output_fields, ztp_output_values)


def ztp_cleanup(engines, system):
    system.ztp.action_abort_ztp().verify_result()
    engines.dut.run_cmd(f'sudo rm -f {ZTP_DATA_LOCAL_JSON}')
    run_system_ztp_with_empty_config(engines, system)
