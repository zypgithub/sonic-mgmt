import json
import logging
import re
import random
import time
import os

from ngts.tools.test_utils import allure_utils as allure
import pytest
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.Devices.IbDevice import JulietNonScaleoutSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.ResultObj import ResultObj
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.general.security.conftest import create_ssh_login_engine
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()


@pytest.mark.ib_interfaces
@pytest.mark.nvos_ci
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface(engines, devices, test_api):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface <name>

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name>' on selected port
    3. Verify the required fields are presented in the output
    """
    TestToolkit.tested_api = test_api
    try:
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()
    except Exception:
        pytest.skip("Device does not have any connectivity")

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        with allure.step('run show interface'):
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                selected_port.interface.show()).get_returned_value()
        with allure.step('validate fields values'):
            validate_one_port_show_output(output_dictionary, devices.dut.switch_type.lower(), devices.dut.asic_type in NvosConst.QTM3_AND_NEWER)

    with allure.step(f'Check interface primary ASIC for port {selected_port.name}'):
        fae = Fae(port_name=selected_port.name)
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            fae.interface.show()).get_returned_value()
        assert IbInterfaceConsts.PRIMARY_ASIC in output_dictionary.keys(), \
            f"{IbInterfaceConsts.PRIMARY_ASIC} field not found for port {selected_port.name}"
        assert int(output_dictionary[IbInterfaceConsts.PRIMARY_ASIC]) in range(0, devices.dut.asic_amount), \
            f"IbInterfaceConsts.PRIMARY_ASIC should be in range of 0-{devices.dut.asic_amount}, " \
            f"but for port {selected_port.name} - " \
            f"{IbInterfaceConsts.PRIMARY_ASIC}={output_dictionary[IbInterfaceConsts.PRIMARY_ASIC]}"


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', [ApiType.OPENAPI])
def test_ib_show_interface_all_state_up(engines, devices, start_sm, test_api):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface

    flow:
    1. Run 'nv show interface'
    2. Select a random port from the output in 'up' state
    3. Verify the required fields are presented in the output
    4. Change the port state to 'down'
    5. Verify the port state as down
    6. Change the port state to 'up'
    7. Verify the port state as up

    """
    TestToolkit.tested_api = test_api

    output_dictionary = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).get_returned_value()

    result = Tools.RandomizationTool.select_random_port(requested_ports_state="up",
                                                        requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE,
                                                        requested_ports_type=devices.dut.switch_type.lower())
    if not result.result:
        return

    selected_port = result.returned_value

    TestToolkit.update_tested_ports([selected_port])

    assert selected_port.name in output_dictionary.keys(), "selected port can't be found in the output"

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
        selected_port.interface.show()).get_returned_value()

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower())

    try:
        with allure.step('Set the state of selected port to "down"'):
            selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                                                   ask_for_confirmation=True).verify_result()
            selected_port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_DOWN).verify_result()

            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                selected_port.interface.show()).get_returned_value()

            with allure.step('Run show command on selected port and verify that each field has an appropriate '
                             'value according to the state of the port'):
                validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), False)

            with allure.step('Set the state of selected port to "up"'):
                selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                       ask_for_confirmation=True).verify_result()
                selected_port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP,
                                                            logical_state='Active').verify_result()
            time.sleep(5)
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
                selected_port.interface.show()).get_returned_value()

            with allure.step('Run show command on selected port and verify that each field has an appropriate '
                             'value according to the state of the port'):
                validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), True)
    finally:
        with allure.step('Set the state of selected port to "up"'):
            selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                   ask_for_confirmation=True).verify_result()
            selected_port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP,
                                                        logical_state='Active').verify_result()


@pytest.mark.ib_interfaces
@pytest.mark.simx
@pytest.mark.nvos_chipsim_ci
def test_ib_show_interface_all_state_down(engines, devices, has_loopbox, setup_name):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface

    flow:
    1. Run 'nv show interface'
    2. Select a random port from the output in 'down' state
    3. Verify the required fields are presented in the output
    """

    if has_loopbox and isinstance(devices.dut, JulietNonScaleoutSwitch):
        pytest.skip("Cannot run test for Juliet NonScaleout system with loopbox")

    output_dictionary = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).get_returned_value()

    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state="down",
                                                               requested_ports_logical_state=None,
                                                               requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()
    TestToolkit.update_tested_ports([selected_port])

    assert selected_port.name in output_dictionary.keys(), "selected port can't be found in the output"

    output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
        selected_port.interface.show()).get_returned_value()

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        validate_one_port_in_show_all_ports(output_dictionary, devices.dut.switch_type.lower(), False)
        link_physical_port_state = output_dictionary[IbInterfaceConsts.LINK][IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE]
        assert link_physical_port_state in [IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING,
                                            IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_DISABLED,
                                            IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING_XDR], \
            "Link physical port state {} isn't as we expected".format(link_physical_port_state)


@pytest.mark.ib_interfaces
@pytest.mark.nvos_ci
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface_name_link(engines, devices, test_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> link

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name> link' on selected port
    3. Verify the required fields are presented in the output
    4. Verify state based on logical & physical state
    """
    TestToolkit.tested_api = test_api

    try:
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()
    except Exception:
        pytest.skip("Device does not have any connectivity")

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()

        validate_link_fields(output_dictionary, devices.dut.switch_type.lower())
        verify_expected_link_state(output_dictionary)


@pytest.mark.ib_interfaces
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ib_show_interface_name_stats(engines, devices, test_api):
    """
    Run show interface command and verify the required fields exist
    Command: nv show interface <name> link stats

    flow:
    1. Select a random port (status of which is up)
    2. Run 'nv show interface <name> link stats' on selected port
    3. Verify the required fields are presented in the output
    """
    try:
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type=devices.dut.switch_type.lower()).get_returned_value()
    except Exception:
        pytest.skip("Device does not have any connectivity")

    TestToolkit.update_tested_ports([selected_port])

    with allure.step('Run show command on selected port and verify that each field has an appropriate '
                     'value according to the state of the port'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_stats_output_to_dictionary(
            selected_port.interface.link.stats.show()).get_returned_value()

        validate_stats_fields(output_dictionary, devices.dut.asic_type in NvosConst.QTM3_AND_NEWER)


@pytest.mark.ib_interfaces
@pytest.mark.ib
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_show_interface_filter(engines, test_api):
    """
    Run show interface command with filter flag and verify the required fields are exist
    command: nv show interface -- filter "<filter>=<value>"

    flow:
    1. Run show interface without filter
    2. Select filter type and value from existing output
    3. Create expected dictionary according to the selected filter
    4. Run show interface with the selected filter
    5. Compare between filtered output dictionary to expected dictionary (at least one should be found)
    6. Run show interface with an empty filter (returns all data)
    7. Compare between filtered output dictionary to the full dictionary
    8. Run show interface with existing filter but value not exist
    9. Run show interface with a filter that does not exist
    """
    interface = Interface(parent_obj=None)
    TestToolkit.tested_api = test_api

    with allure.step('Run show interface without filter'):
        output_dict = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show()).get_returned_value()

    with allure.step('Select filter type and value from existing output'):
        random_key = RandomizationTool.select_random_value(list(output_dict.keys())).get_returned_value()
        filter_name = RandomizationTool.select_random_value(list(output_dict[random_key].keys())).get_returned_value()
        value = output_dict[random_key][filter_name]

    with allure.step('Create expected dictionary according to the selected filter'):
        filtered_expected = {}
        for key in output_dict.keys():
            if filter_name in output_dict[key].keys():
                if value == output_dict[key][filter_name]:
                    filtered_expected.update({key: output_dict[key]})

    with allure.step('Run show interface with the selected filter'):
        output_dict_filtered = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.filter(filter_name=filter_name, value=value).get_returned_value()).verify_result()

    with allure.step('Compare between filtered output dictionary to expected dictionary'
                     '(at least one should be found)'):
        res_obj = ValidationTool.compare_nested_dictionary_content(output_dict_filtered, filtered_expected)
        if is_redmine_issue_active([4235573])[0] and test_api == ApiType.OPENAPI:
            res_obj.ignore_result()
        else:
            res_obj.verify_result()

    with allure.step('Run show interface with an empty filter (returns all data)'):
        output_dict_filtered = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.filter().get_returned_value()).get_returned_value()

    with allure.step('Run show interface without filter'):
        output_dict = Tools.OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
            interface.show()).get_returned_value()

    with allure.step('Compare between filtered output dictionary to the full dictionary'):
        res_obj = ValidationTool.compare_nested_dictionary_content(output_dict_filtered, output_dict)
        if is_redmine_issue_active([4235573])[0] and test_api == ApiType.OPENAPI:
            res_obj.ignore_result()
        else:
            res_obj.verify_result()

    with allure.step('Run show interface with existing filter but value not exist'):
        value = 'value_not_exists'
        output_dict_filtered = interface.filter(filter_name=filter_name, value=value).verify_result()
        assert output_dict_filtered.startswith('{}'), f"expected empty dict - got {output_dict_filtered}"

    with allure.step('Run show interface with a filter that does not exist'):
        filter_name = 'filter_not_exist'
        output_dict_filtered = interface.filter(filter_name=filter_name, value=value).verify_result(False)
        assert re.search(r'No match found for filter depth of \d+\.', output_dict_filtered)


@pytest.mark.ib_interfaces
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_validate_discard_counters_fields(engines, test_api):
    """
    Run show interface command and verify the required fields are exist
    command: nv show interface <name>

    flow:
    1. Select a random port
    2. Get the OID of the port
    3. Validate that in-drops and out-drops fields are present in show output
    4. Validate that in-drops and out-drops fields are present in Sonic DB
    5. Validate that in-drops and out-drops fields are present in GNMI
    """
    TestToolkit.tested_api = test_api
    server = 'fit-build-240'
    server_user = os.getenv("BUILD_SERVER_USER")
    server_password = os.getenv("BUILD_SERVER_PASSWORD")
    gnmi_engine = LinuxSshEngine(server, server_user, server_password)
    system = System()
    system_show = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
    host = system_show['hostname']
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    TestToolkit.update_tested_ports([selected_port])
    port = selected_port.name
    port_oid = get_port_oid(engines, port)
    logging.info("Selected Port:{}, OID:{}".format(port, port_oid))

    with allure.step('Validate that in-drops and out-drops fields are present in show output'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            selected_port.interface.show()).get_returned_value()
        assert IbInterfaceConsts.LINK_STATS_IN_DROPS in output_dictionary["link"]["counters"].keys(), \
            "{} field not available in show interface".format(IbInterfaceConsts.LINK_STATS_IN_DROPS)
        assert IbInterfaceConsts.LINK_STATS_OUT_DROPS in output_dictionary["link"]["counters"].keys(), \
            "{} field not available in show interface".format(IbInterfaceConsts.LINK_STATS_OUT_DROPS)

    with allure.step('Validate that in-drop counter fields are present in Sonic-DB'):
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.PC_VL15_DROPPED_F)
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.RCV_DISCARD_EXTERNAL_CONTAIN)
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_IN_DROPS)

    with allure.step('Validate that out-drop counter fields are present in Sonic-DB'):
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.PC_XMT_DISCARDS_F)
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.XMT_DISCARD_EXTERNAL_CONTAIN)
        validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_OUT_DROPS)

    with allure.step('Validate that total-in-drops and total-out-drops fields are present via GNMI'):
        validate_field_from_gnmi(gnmi_engine, host, port, "in-discards")
        validate_field_from_gnmi(gnmi_engine, host, port, "out-discards")


@pytest.mark.ib_interfaces
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_validate_total_counters_in_out_drops(engines, test_api):
    """
    Validate that total in and out drops counters are a sum of two other counters

    flow:
    1. Select a random port (status of which is up)
    2. Get the OID of the port
    3. Validate total in drop counters are a sum of two counters in Sonic-DB
    4. Validate total out drop counters are a sum of two counters in Sonic-DB
    """
    TestToolkit.tested_api = test_api

    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    TestToolkit.update_tested_ports([selected_port])
    port = selected_port.name
    port_oid = get_port_oid(engines, port)
    logging.info("Selected Port:{}, OID:{}".format(port, port_oid))

    with allure.step('Validate total in drop counters are a sum of two counters in Sonic-DB'):
        pc_vl15_dropped_f = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.PC_VL15_DROPPED_F)
        rcv_discard_ext_cont = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.
                                                            RCV_DISCARD_EXTERNAL_CONTAIN)
        total_in_drops = pc_vl15_dropped_f + rcv_discard_ext_cont

        output = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_IN_DROPS)
        assert total_in_drops == output, f"Total in drops is not equal to sum of " \
            f"{IbInterfaceConsts.PC_VL15_DROPPED_F} and " \
            f"{IbInterfaceConsts.RCV_DISCARD_EXTERNAL_CONTAIN}"

    with allure.step('Validate total out drop counters are a sum of two counters in Sonic-DB'):
        pc_xmt_discards_f = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.PC_XMT_DISCARDS_F)
        xmt_discard_ext_cont = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.
                                                            XMT_DISCARD_EXTERNAL_CONTAIN)
        total_out_drops = pc_xmt_discards_f + xmt_discard_ext_cont

        output = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_OUT_DROPS)
        assert total_out_drops == output, f"Total out drops is {output} instead of {total_out_drops} which is not " \
            f"equal to sum of {IbInterfaceConsts.PC_XMT_DISCARDS_F} and " \
            f"{IbInterfaceConsts.XMT_DISCARD_EXTERNAL_CONTAIN}"


@pytest.mark.ib_interfaces
@pytest.mark.ib
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_validate_total_in_out_counters_show_db_gnmi(engines, test_api):
    """
    Validate total in drop and out drop counters are same across show, Sonic DB and GNMI

    flow:
    1. Select a random port
    2. Get the OID of the port
    3. Retrieve the required fields: in-drops and out-drops are present from the show output
    4. Retrieve the required fields: in-drops and out-drops are present from the sonic DB
    5. Retrieve the required fields: in-drops and out-drops are present from GNMI
    6. Compare in/out drops counters across show CLI, Sonic DB and GNMI server
    """
    TestToolkit.tested_api = test_api
    server = 'fit-build-240'
    server_user = os.getenv("BUILD_SERVER_USER")
    server_password = os.getenv("BUILD_SERVER_PASSWORD")
    gnmi_engine = LinuxSshEngine(server, server_user, server_password)
    system = System()
    system_show = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
    host = system_show['hostname']
    in_drop_mismatch_err = ""
    out_drop_mismatch_err = ""
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    TestToolkit.update_tested_ports([selected_port])
    port = selected_port.name
    logging.info("Selected Port:{}".format(port))
    port_oid = get_port_oid(engines, selected_port.name)

    with allure.step('Retrieve in-drops and out-drops fields from show output'):
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            selected_port.interface.show()).get_returned_value()
        in_drops_show = output_dictionary["link"]["counters"][IbInterfaceConsts.LINK_STATS_IN_DROPS]
        out_drops_show = output_dictionary["link"]["counters"][IbInterfaceConsts.LINK_STATS_OUT_DROPS]

    with allure.step('Retrieve in-drops and out-drops fields from Sonic-DB'):
        in_drops_sonic_db = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_IN_DROPS)
        out_drops_sonic_db = validate_field_from_sonic_db(engines, port_oid, IbInterfaceConsts.TOTAL_OUT_DROPS)

    with allure.step('Validate that in-drops and out-drops fields are present via GNMI'):
        in_drops_gnmi = validate_field_from_gnmi(gnmi_engine, host, port, "in-discards")
        out_drops_gnmi = validate_field_from_gnmi(gnmi_engine, host, port, "out-discards")

    with allure.step('Compare in/out drops counters across show CLI, Sonic DB and GNMI server'):
        if (in_drops_show != in_drops_sonic_db) or (in_drops_show != in_drops_gnmi):
            in_drop_mismatch_err = "In drop counter mismatch: show:{}, DB:{}, GNMI:{}".format(
                in_drops_show, in_drops_sonic_db, in_drops_gnmi)
        if (out_drops_show != out_drops_sonic_db) | (out_drops_show != out_drops_gnmi):
            out_drop_mismatch_err = "Out drop counter mismatch: show:{}, DB:{}, GNMI:{}".format(
                out_drops_show, out_drops_sonic_db, out_drops_gnmi)
        assert not ((in_drop_mismatch_err != "") or (out_drop_mismatch_err != "")), "{}, {}".format(
            in_drop_mismatch_err, out_drop_mismatch_err)


def get_port_oid(engines, port_name):
    fae = Fae(port_name=f'{port_name}')
    output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
        fae.interface.show()).get_returned_value()
    port_key = output_dictionary["plan-ports"][port_name]["key"]
    port_to_oid_cmd = f'sonic-db-cli COUNTERS_DB hgetall "COUNTERS_PORT_NAME_MAP"'
    output = engines.dut.run_cmd(port_to_oid_cmd)
    # change output string to match json format
    output = output.replace("'", '"')
    port_oid_details_dict = json.loads(output)
    output = port_oid_details_dict[f'{port_key}']
    port_oid = output.split(":")[1]
    return port_oid


def validate_field_from_sonic_db(engines, port_oid, field_name):
    output_sonic_db = engines.dut.run_cmd(f'sonic-db-cli COUNTERS_DB hget "COUNTERS:oid:{port_oid}" "{field_name}"')
    assert output_sonic_db != "", f"Field {field_name} not present in sonic db for port oid {port_oid}"
    value = int(output_sonic_db)
    logger.info(f"Sonic DB Port OID:{port_oid}, Field:{field_name}, Value:{value}")
    return value


def validate_field_from_gnmi(gnmi_engine, host, port, field):
    gnmi_cmd = f'gnmic -a {host} --port 9339 subscribe --path "interfaces/interface[name={port}]/state/' \
        f'counters/{field}" --target nvos -u admin -p admin --mode once --skip-verify --format flat'
    output = gnmi_engine.run_cmd(gnmi_cmd)
    value = int(output.split(":")[-1].strip())
    logging.info("Port: {}, Field {}: {}".format(port, field, value))
    return value


def validate_interface_fields(output_dictionary):
    with allure.step('Check that the following fields exist in the output: type, link'):
        logging.info('Check that the following fields exist in the output: type, link')
        field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK]
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()


def validate_link_fields(output_dictionary, switch_type, port_up=True):
    with allure.step('Check that all expected fields under link field exist in the output'):
        logging.info('Check that all expected fields under link field exist in the output')
        field_to_check = [IbInterfaceConsts.LINK_STATE,
                          # IbInterfaceConsts.LINK_IB_SUBNET,
                          IbInterfaceConsts.LINK_SUPPORTED_LANES,
                          IbInterfaceConsts.LINK_MAX_SUPPORTED_MTU,
                          # IbInterfaceConsts.LINK_SUPPORTED_IB_SPEEDS,
                          # IbInterfaceConsts.LINK_SUPPORTED_SPEEDS,
                          IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
                          IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                          IbInterfaceConsts.LINK_VL_ADMIN_CAPABILITIES,
                          IbInterfaceConsts.LINK_CONNECTION_MODE]
        if switch_type == "ib":
            field_to_check.insert(1, IbInterfaceConsts.LINK_IB_SUBNET)  # Insert at the desired position

        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

        field_to_check = [IbInterfaceConsts.LINK_MTU,
                          # IbInterfaceConsts.LINK_SPEED,
                          # IbInterfaceConsts.LINK_IB_SPEED,
                          IbInterfaceConsts.LINK_OPERATIONAL_VLS]

        if output_dictionary[IbInterfaceConsts.LINK_CONNECTION_MODE] == IbInterfaceConsts.XDR and \
           output_dictionary[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE] == IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE:
            field_to_check.insert(1, IbInterfaceConsts.LINK_SPEED)

        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary,
                                                               field_to_check, port_up).verify_result()
        # Will be changed
        field_to_check = [IbInterfaceConsts.LINK_LANES]
        res = Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check, port_up)
        logging.warning(res.info)


def validate_stats_fields(output_dictionary, is_qtm3_or_newer=False):
    with allure.step('Check that all expected fields under link-stats field exist in the output'):
        logging.info('Check that all expected fields under link-stats field exist in the output')
        fields_to_check = [IbInterfaceConsts.LINK_STATS_IN_BYTES,
                           IbInterfaceConsts.LINK_STATS_IN_DROPS,
                           IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                           IbInterfaceConsts.LINK_STATS_IN_SYMBOL_ERRORS,
                           IbInterfaceConsts.LINK_STATS_IN_PKTS,
                           IbInterfaceConsts.LINK_STATS_OUT_BYTES,
                           IbInterfaceConsts.LINK_STATS_OUT_DROPS,
                           IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
                           IbInterfaceConsts.LINK_STATS_OUT_PKTS,
                           IbInterfaceConsts.LINK_STATS_OUT_WAIT]
        if is_qtm3_or_newer:
            logging.info('Add expected fields for Quantum3 device')
            fields_to_check.extend(IbInterfaceConsts.LINK_STATS_QNT3)
            verify_non_negative_counters({IbInterfaceConsts.LINK_STATS_RCV_ICRC_ERRORS: output_dictionary[IbInterfaceConsts.LINK_STATS_RCV_ICRC_ERRORS],
                                         IbInterfaceConsts.LINK_STATS_TX_PARITY_ERRORS: output_dictionary[IbInterfaceConsts.LINK_STATS_TX_PARITY_ERRORS]})
        Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, fields_to_check).verify_result()


def validate_one_port_show_output(output_dictionary, switch_type, is_qtm3_or_newer=False):
    validate_interface_fields(output_dictionary)

    validate_link_fields(output_dictionary[IbInterfaceConsts.LINK], switch_type)

    validate_stats_fields(output_dictionary[IbInterfaceConsts.LINK][IbInterfaceConsts.LINK_STATS], is_qtm3_or_newer)


def validate_one_port_in_show_all_ports(output_dictionary, switch_type, port_up=True):
    field_to_check = [IbInterfaceConsts.TYPE, IbInterfaceConsts.LINK]
    Tools.ValidationTool.verify_field_exist_in_json_output(output_dictionary, field_to_check).verify_result()

    validate_link_fields(output_dictionary[IbInterfaceConsts.LINK], switch_type, port_up)


def verify_expected_link_state(output_dictionary):
    link_physical_port_state = output_dictionary[IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE]
    link_logical_port_state = output_dictionary[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE]
    if link_physical_port_state in \
            [IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING,
             IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_DISABLED]:

        Tools.ValidationTool.validate_fields_values_in_output(
            output_dict=output_dictionary,
            expected_fields=[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE, IbInterfaceConsts.LINK_STATE],
            expected_values=[IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_DOWN, NvosConsts.LINK_STATE_DOWN]) \
            .verify_result()

    elif link_physical_port_state == IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP:

        Tools.ValidationTool.verify_field_value_in_output(
            output_dictionary=output_dictionary,
            field_name=IbInterfaceConsts.LINK_STATE,
            expected_value=NvosConsts.LINK_STATE_UP).verify_result()

        assert link_logical_port_state in [IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE,
                                           IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_INITIALIZE], \
            "Link logical port state {} isn't as we expected".format(link_logical_port_state)

    else:
        raise Exception("Link physical port state {} isn't as we expected".format(link_physical_port_state))


def verify_non_negative_counters(link_stats_dict):
    for field, counter in link_stats_dict.items():
        assert counter >= 0, f"counter isn't as we expected.\n we got: {field}={counter}"


def extract_non_dict_keys(output_dict):
    keys = []

    for key, value in output_dict.items():
        if not isinstance(value, dict):  # Only add key if value is not a dict
            keys.append(key)

    return keys
