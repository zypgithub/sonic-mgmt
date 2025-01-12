import pytest

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


@pytest.mark.ib
def test_ib0_interface_description(engines):
    """
    Configure ib0 interface description and verify the configuration applied successfully
    Relevant cli commands:
    -	nv set interface ib0 description 'ib0 description'
    -	nv show interface ib0

    flow:
    1. Set ib0 port description to ‘ib0 description’
    2. Verify the configuration applied by running “show” command
    3. UnSet ib0 port description
    4. Verify the configuration applied by running “show” command
    """
    with allure.step("Create Port object"):
        ib0_port = Port('ib0')

    with allure.step("Set description and verify"):
        ib0_port.interface.set(op_param_name='description', op_param_value='"ib0 description"',
                               apply=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            ib0_port.interface.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.DESCRIPTION,
                                                          expected_value='ib0 description').verify_result()

    with allure.step("Unset description and verify"):
        ib0_port.interface.unset(op_param='description', apply=True).verify_result()

        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            ib0_port.interface.show()).get_returned_value()

        assert IbInterfaceConsts.DESCRIPTION not in output_dictionary.keys(), \
            "Expected to have description field after unset command, but we still have this field."


# ------------ Open API tests -----------------

@pytest.mark.openapi
@pytest.mark.ib
def test_ib0_interface_description_openapi(engines):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_ib0_interface_description(engines)
