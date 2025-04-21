import logging
import pytest
import random

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Transceivers import Transceiver
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.infra.ResultObj import ResultObj


logger = logging.getLogger()


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_maintenance_state_show_cmd(test_api, setup_name):
    """
    Test the SDN maintenance state show commands functionality.

    This test verifies:
    1. The 'nv show sdn transceivers' command output format and content
    2. The 'nv show sdn transceivers <transceiver-id>' command output matches the general show output
    3. The maintenance state appears in interface link output
    """
    TestToolkit.tested_api = test_api
    sdn = Sdn()
    cluster = Cluster()
    ClusterTools.start_cluster(cluster, setup_name)

    with allure.step("Validate show sdn transceivers command output"):
        transceivers_output = OutputParsingTool.parse_show_output_to_dict(sdn.transceivers.show()).get_returned_value()
        transceivers_names_list = list(transceivers_output.keys())
        assert len(transceivers_names_list) > 0, "No transceivers shown in the show transceivers output cmd"
        assert len(transceivers_names_list[0].split('.')) == 3, "transceiver output is not in the correct format of chassis-sn.slot-id.transceiver-id"
        transceiver_id = transceivers_names_list[0]
        logger.info(f"The chosen transceiver id: {transceiver_id}")
        logger.info(f"The chosen transceiver id output: {transceivers_output[transceiver_id]}")
        assert ClusterConsts.MAINTENANCE_STATE in transceivers_output[transceiver_id], f"{ClusterConsts.MAINTENANCE_STATE} does not appear in the transceivers output"

    with allure.step("Validate show sdn transceivers transceiver-id command output"):
        transceiver_id_output = OutputParsingTool.parse_show_output_to_dict(sdn.transceivers.show(transceiver_id)).get_returned_value()
        logger.info(f"transceiver id output: {transceiver_id_output}")
        assert transceivers_output[transceiver_id] == transceiver_id_output, "The transceivers output for specific id is not the same as the transceiver id output"

    with allure.step("Validate maintenance state appears in the show interface command output"):
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type='nvl', requested_ports_state=None, interface_type='sw').get_returned_value()
        output_dictionary = Tools.OutputParsingTool.parse_show_output_to_dict(selected_port.interface.link.show()).get_returned_value()
        assert ClusterConsts.MAINTENANCE_STATE in output_dictionary, f"{ClusterConsts.MAINTENANCE_STATE} does not appear in the interface link output"


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_change_maintenance_state(test_api):
    """
    Test the ability to change and restore maintenance state for SDN transceivers.

    This test:
    1. Selects two transceivers from different chassis
    2. For each transceiver:
       - Changes maintenance state to each possible option (up, down, diag)
       - Verifies the state change is successful
       - Restores the maintenance state
       - Verifies the state is restored to 'up'
    """
    TestToolkit.tested_api = test_api
    sdn = Sdn()
    transceivers_amount = 2    # same as rack number, to use transceiver from each rack

    with allure.step(f"Choose {transceivers_amount} transceivers from different chassis"):
        transceivers_output = OutputParsingTool.parse_show_output_to_dict(sdn.transceivers.show()).get_returned_value()
        transceivers_list = list(transceivers_output.keys())
        assert len(transceivers_list) > 0, "No transceivers shown in the show transceivers output cmd"
        assert len(transceivers_list[0].split('.')) == 3, "transceiver output is not in the correct format of chassis-sn.slot-id.transceiver-id"
        chassis_sn_set = set(transceiver_id.split('.')[0] for transceiver_id in transceivers_list)
        assert len(chassis_sn_set) >= transceivers_amount, f"Not enough transceivers with different chassis serial numbers, \
                                                      expect to have at least {transceivers_amount} transceivers with different chassis serial numbers"
        slot_id_set = set(transceiver_id.split('.')[1] for transceiver_id in transceivers_list)
        transceiver_id_set = set(transceiver_id.split('.')[2] for transceiver_id in transceivers_list)
        first_transceiver_name = f"{list(chassis_sn_set)[0]}.{random.choice(list(slot_id_set))}.{random.choice(list(transceiver_id_set))}"
        second_transceiver_name = f"{list(chassis_sn_set)[1]}.{random.choice(list(slot_id_set))}.{random.choice(list(transceiver_id_set))}"
        chosen_transceivers_list = [Transceiver(sdn.transceivers, first_transceiver_name), Transceiver(sdn.transceivers, second_transceiver_name)]
        logger.info(f"The chosen transceivers are: {first_transceiver_name}, {second_transceiver_name}")

    with allure.step("Change maintenance state for the chosen transceivers"):
        for maintenance_state in ClusterConsts.MAINTENANCE_STATE_OPTIONS:
            for transceiver in chosen_transceivers_list:

                with allure.step(f"Change maintenance state to {maintenance_state} to transceiver {transceiver.name}"):
                    transceiver.action_update_maintenance_state(maintenance_state)

                with allure.step(f"Validate maintenance state is updated to {maintenance_state} for transceiver {transceiver.name}"):
                    transceiver_show_output = OutputParsingTool.parse_show_output_to_dict(transceiver.show()).get_returned_value()
                    assert transceiver_show_output[ClusterConsts.MAINTENANCE_STATE] == maintenance_state, "The maintenance state is not updated"

                with allure.step(f"Restore maintenance state for transceiver {transceiver.name}"):
                    transceiver.action_restore_maintenance_state()

                with allure.step(f"Validate maintenance state is restored to up for transceiver {transceiver.name}"):
                    transceiver_show_output = OutputParsingTool.parse_show_output_to_dict(transceiver.show()).get_returned_value()
                    assert transceiver_show_output[ClusterConsts.MAINTENANCE_STATE] == 'up', "The maintenance state is not restored to up"


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_bad_params(test_api):
    """
    Test error handling for invalid parameters in SDN maintenance state commands.

    This test verifies:
    1. The 'nv show sdn transceivers' command handles invalid parameters correctly
    2. The maintenance state update command rejects invalid state values
    """
    TestToolkit.tested_api = test_api
    sdn = Sdn()
    random_string = RandomizationTool.get_random_string(length=10)

    with allure.step("check show sdn transceivers cmd with bad param"):
        sdn.transceivers.show(random_string, exempted_err_msgs=["is not a ", "Error"])

    with allure.step("check update sdn transceiver maintenance state cmd with bad param"):

        with allure.step("get a transceiver name"):
            transceivers_output = OutputParsingTool.parse_show_output_to_dict(sdn.transceivers.show()).get_returned_value()
            transceiver_name = list(transceivers_output.keys())[0]
            transceiver = Transceiver(sdn.transceivers, transceiver_name)

        with allure.step("update maintenance state with bad param"):
            transceiver.action_update_maintenance_state(random_string, expected_err_msgs=["is not one of", "Error"])


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_port_state_change_according_to_maintenance_state(engines, devices, test_api):
    """
    Test that port states change correctly based on maintenance state changes.

    This test verifies:
    1. For ports in UP state:
       - Port stays UP when maintenance state is 'up' or 'diag'
       - Port goes DOWN when maintenance state is 'down'
    2. For ports in DOWN state:
       - Port stays DOWN regardless of maintenance state
    """
    TestToolkit.tested_api = test_api
    up_port_maintenance_state_mapping = {'up': 'up', 'diag': 'up', 'down': 'down'}  # key is the maintenance state, value is the expected port state
    down_port_maintenance_state_mapping = {'up': 'down', 'diag': 'down', 'down': 'down'}  # key is the maintenance state, value is the expected port state

    send_mads_for_port_and_validate_maintenance_state(NvosConsts.LINK_STATE_UP, devices, engines, up_port_maintenance_state_mapping)
    send_mads_for_port_and_validate_maintenance_state(NvosConsts.LINK_STATE_DOWN, devices, engines, down_port_maintenance_state_mapping)


def send_mads_for_port_and_validate_maintenance_state(port_state, devices, engines, maintenance_state_mapping):
    """
    Helper function to send MADs and validate port state changes.

    This function:
    1. Selects a random port in the specified state
    2. Gets the port's current state and maintenance state
    3. For each maintenance state option:
       - Sends MADs to set the admin state
       - Waits for and validates the port state change
    4. Return the maintenance state to up

    Args:
        port_state: The initial state of the port to select
        devices: Test devices fixture
        engines: Test engines fixture
        maintenance_state_mapping: Dictionary mapping maintenance states to expected port states
    """
    with allure.step(f"Choose a port in {port_state} state"):
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_type='nvl', requested_ports_state=port_state, interface_type='sw').get_returned_value()
        port_name = selected_port.name

    with allure.step(f"Get the port state and maintenance state"):
        output_dictionary = OutputParsingTool.parse_show_interface_link_output_to_dictionary(selected_port.interface.link.show()).get_returned_value()
        port_state = output_dictionary['state']
        port_maintenance_state = output_dictionary[ClusterConsts.MAINTENANCE_STATE]
        logger.info(
            f"The chosen port is: {port_name}, the port state is: {port_state}, the port maintenance state is: {port_maintenance_state}")

    modifier, sx_ib_device = get_modifier_and_sx_ib_device(port_name, devices.dut)

    for maintenance_state, expected_port_state in maintenance_state_mapping.items():
        with allure.step(f"Send MADs to set admin state to {maintenance_state} and validate port state is {expected_port_state}"):
            send_mad_to_set_admin_state(engines.dut, sx_ib_device, modifier, maintenance_state)
            Port.wait_for_port_state(selected_port, expected_state=expected_port_state)

    with allure.step("Return maintenance state to up"):
        send_mad_to_set_admin_state(engines.dut, sx_ib_device, modifier, 'up')
        Port.wait_for_port_state(selected_port, expected_state=port_state)


def get_modifier_and_sx_ib_device(port_name, device):
    with allure.step(f"Get the modifier and sx_ib_device for the port {port_name}"):
        start_of_modifer_number_decimal = 37
        _, port_number, local_port, split_number, _ = Port.parse_port_name(port_name)

        if isinstance(device, JulietSwitch) and port_number > 9:
            # Juliet ports 10-18 belong to ASIC B and their label_port numbering restarts at 1
            port_number = port_number - 9

        modifier_decimal = start_of_modifer_number_decimal + (4 * (port_number - 1) + 2 * (local_port - 1) + (split_number - 1))
        modifier_hex = f"0x{modifier_decimal:02x}"

        fae = Fae(port_name=port_name)
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(fae.interface.show()).get_returned_value()
        asic_number = output_dictionary[IbInterfaceConsts.PRIMARY_ASIC]
        sx_ib_device = f"sx_ib_{asic_number}"
        return modifier_hex, sx_ib_device


def send_mad_to_set_admin_state(engine, sx_ib_device, modifier, maintenance_state):
    with allure.step(f"Send MADs to {sx_ib_device} to modifier {modifier} to set nmx admin state to {maintenance_state}"):
        result_obj = ResultObj(True, "")
        nmx_admin_state_map = {'up': '1', 'down': '2', 'diag': '3'}
        nmx_admin_state = nmx_admin_state_map[maintenance_state]
        mad_cmd = f"sudo python /usr/local/lib/nvmad/nvmad.py --Ca {sx_ib_device} --dr 0 --mad MEPI --method=0x2 --modifier={modifier} \
                --get -x MEPI.StateChangeEnable=0x2 -x  MEPI.NMXAdminState={nmx_admin_state}"
        result_obj.returned_value = engine.run_cmd(mad_cmd)
        return result_obj
