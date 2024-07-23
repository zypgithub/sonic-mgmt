from ngts.tools.test_utils import allure_utils as allure
import logging
from ngts.tools.test_utils.allure_utils import step
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.tests_nvos.general.security.conftest import *

logger = logging.getLogger()


@pytest.mark.init_flow
@pytest.mark.nvos_ci
def test_system_init_done_default_values(engines, test_name):
    """
    Test flow:
        1. Run nv show system
        2. validate Status = System is ready
        3. Run nv show fae system ready
        4. validate state = enabled
        5. Run nv action reboot system - will ends after catching "system is ready message" and CLI is up
        6. Run nv show system ready
        7. validate Status = System is ready
    """

    with allure.step("test the default values of system init done"):
        system = System(None)
        fae = Fae()

        with step("verify the system is ready using nv show system"):
            ValidationTool.verify_field_value_in_output(OutputParsingTool.parse_json_str_to_dictionary(system.show()).verify_result(), SystemConsts.STATUS, SystemConsts.STATUS_DEFAULT_VALUE).verify_result()

        with step("verify the fae system default values using nv show fae system"):
            ValidationTool.verify_field_value_in_output(OutputParsingTool.parse_json_str_to_dictionary(fae.system.show('ready')).verify_result(), SystemConsts.FAE_SYSTEM_STATE, SystemConsts.FAE_SYSTEM_STATE_DEFAULT_VALUE).verify_result()


@pytest.mark.init_flow
def test_fae_system_ready_invalid_value():
    """

    Test flow:
        1. run nv set fae system ready <invalid> - <invalid> not in {enabled, disabled}
        2. validate the error message
    """
    err_message = "Error: At state: '{}' is not one of ['enabled', 'disabled']".format('INVALID')
    with step("test the invalid value of system init done"):
        fae = Fae()
        with step("verify the fae default values using nv show fae system"):
            assert err_message in fae.system.set('ready state INVALID').info, "Invalid value message is not as expected: {expected}".format(expected=err_message)


@pytest.mark.init_flow
def test_system_status_with_down_docker(engines, devices):
    """
    Test flow:
        1. run sudo systemctl stop [swss-ibv00] if marlin
        2. run nv show system
        3. validate status = system is ok
        1. run sudo systemctl start swss-ibv0 [swss-ibv00] if marlin
    """
    with allure.step('test system status after killing swss docker'):
        with allure.step('pick a docker to kill'):
            docker_to_kill = [i for i in devices.dut.available_dockers if i.startswith('swss')][0]

        try:
            with allure.step('kill docker {}'.format(docker_to_kill)):
                engines.dut.run_cmd('sudo systemctl stop {}'.format(docker_to_kill))

            with step("verify the system is still ready using nv show system"):
                system = System(None)
                ValidationTool.verify_field_value_in_output(OutputParsingTool.parse_json_str_to_dictionary(system.show()).verify_result(), SystemConsts.STATUS, SystemConsts.STATUS_DEFAULT_VALUE).verify_result()

        finally:
            with allure.step('start docker {} as a cleanup step'.format(docker_to_kill)):
                engines.dut.run_cmd('sudo systemctl start {}'.format(docker_to_kill))
