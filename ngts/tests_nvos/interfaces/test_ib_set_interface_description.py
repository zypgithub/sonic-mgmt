import logging
from ngts.tools.test_utils import allure_utils as allure
import pytest

from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import NvosConst

logger = logging.getLogger()


@pytest.mark.ib_interfaces
@pytest.mark.ib
def test_ib_set_interface_description(engines):
    """
    Set and unset interface description and verify the show interface output using
    command: nv show interface <name>

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name>' on selected port
    3. Validate if description is empty
    4. Run 'nv set interface <name> description abcd'
    5. Apply config
    6. Run 'nv show interface <name>' on selected port
    7. Validate interface description is updated
    8. Run 'nv unset interface <name>'
    9. Apply config
    10. Run 'nv show interface <name>'
    11. Validate if description is cleared
    """
    DESCRIPTION_EMPTY = ""
    DESCRIPTION_ABCD = "abcd"
    selected_port = Tools.RandomizationTool.select_random_port().get_returned_value()
    selected_port.update_output_dictionary()

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that description field is empty'):
        validate_interface_description_field(selected_port, DESCRIPTION_EMPTY, True)

    with allure.step('Run show command on selected port and verify that description field is set'):
        selected_port.interface.set(NvosConst.DESCRIPTION, DESCRIPTION_ABCD, apply=True).verify_result()
        selected_port.update_output_dictionary()
        validate_interface_description_field(selected_port, DESCRIPTION_ABCD, True)

    with allure.step('Run show command on selected port and verify that description field is cleared back'):
        selected_port.interface.unset(NvosConst.DESCRIPTION, apply=True).verify_result()
        selected_port.update_output_dictionary()
        validate_interface_description_field(selected_port, DESCRIPTION_EMPTY, True)


def validate_interface_description_field(selected_port, description_value, should_be_equal):
    with allure.step('Check that interface description field matches the expected value'):
        logging.info('Check that interface description field matches the expected value')
        output_dictionary = selected_port.show_output_dictionary
        if NvosConst.DESCRIPTION in output_dictionary.keys():
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary, NvosConst.DESCRIPTION,
                                                              description_value).verify_result()


# ------------ Open API tests -----------------

@pytest.mark.openapi
@pytest.mark.ib_interfaces
@pytest.mark.ib
def test_ib_set_interface_description_openapi(engines):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_ib_set_interface_description(engines)
