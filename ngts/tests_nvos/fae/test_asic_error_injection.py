import logging
import pytest
import re

from retry import retry
from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.fae
def test_asic_error_injection(engines):
    """
        1. Check fae platform asic error-injection disabled by default
        2. Enable asic error-injection and verify show command
        3. Run PTER register cmd and check output exist
        4. Disable asic error-injection and verify show command
        5. Run PTER register cmd and check no output
    """
    fae = Fae()
    mst_path = "/dev/mst/"
    mst_devices = engines.dut.run_cmd(f"ls {mst_path} | grep -i pciconf").splitlines()

    try:
        with allure.step("Run show asic error-injection and check default values"):
            _wait_until_error_injection_status(fae, status=NvosConst.DISABLED, tries=0)

        with allure.step("Run action enable for asic error-injection"):
            fae.platform.asic.error_injection.action_deprecated(ActionConsts.ENABLE)

        with allure.step("Run show asic error-injection and check value changed"):
            _wait_until_error_injection_status(fae, status=NvosConst.ENABLED)

        with allure.step("Run PTER register access command"):
            output = RegisterTool.get_mst_register_value(engines.dut, mst_path + mst_devices[0], "PTER",
                                                         '--indexes "plane_ind=0,lp_msb=0,local_port=5,pnat=0,error_page=0"', 'local_port')
            assert re.search(r'local_port',
                             output), f"Expected to find 'local_port' in output. Got: {output}"

    finally:
        with allure.step("Disable asic error-injection"):
            fae.platform.asic.error_injection.action_deprecated(ActionConsts.DISABLE)

        with allure.step("Run show asic error-injection and check default values"):
            _wait_until_error_injection_status(fae, status=NvosConst.DISABLED)

        with allure.step("Run PTER register access command"):
            output = RegisterTool.get_mst_register_value(engines.dut, mst_path + mst_devices[0], "PTER",
                                                         '--indexes "plane_ind=0,lp_msb=0,local_port=5,pnat=0,error_page=0"', 'local_port')
            assert not re.search(r'local_port',
                                 output), f"Expected to not find 'local_port' in output. Got: {output}"


def _wait_until_error_injection_status(fae, status='', tries=8, delay=2):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(fae, status=''):
        with allure.step("Waiting for error injection status changed to status {}".format(status)):
            output_dictionary = OutputParsingTool.parse_show_output_to_dict(
                fae.platform.asic.error_injection.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary['ASIC1'],
                                                        field_name='error-injection',
                                                        expected_value=status).verify_result()
    _retry_decorator(fae, status)
