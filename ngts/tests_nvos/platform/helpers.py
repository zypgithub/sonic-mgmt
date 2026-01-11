from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, DelayedRecovery, InterfaceConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Fae import Fae


def _pre_port_config(ports):
    """
    in this function we will configure the port with the following:
    - description
    - delayed recovery state
    - delayed recovery retry threshold
    - link phy-recovery serdes-eq-mode - enabled
    :param port: the port to configure
    :return: the output of the show command
    """
    with allure.step("Apply link configurations to selected ports"):
        show_ports_output = []
        for port in ports:
            with allure.step(f"configuration for port {port}"):
                fae = Fae(port_name=port.name)
                port.interface.set(InterfaceConsts.DESCRIPTION, "testing").verify_result()
                fae.interface.link.delayed_recovery.set(DelayedRecovery.DELAYED_RECOVERY_STATE, "enabled").verify_result()
                fae.interface.link.delayed_recovery.set(DelayedRecovery.DELAYED_RECOVERY_RETRY_TH, "200", apply=True, ask_for_confirmation=True).verify_result()
                # fae.interface.link.phy_recovery.set("serdes-eq-mode", "enabled", apply=True), we need to add more configurations here - NVL and IB
            with allure.step(f"run show fae interface link for {port}"):
                show_ports_output.append(OutputParsingTool.parse_json_str_to_dictionary(fae.interface.link.show()).get_returned_value())
        return show_ports_output


def _post_port_config(show_ports_output, ports, ignore_fields=None):
    diff_result = []
    with allure.step("verify link configurations"):
        for output, port in zip(show_ports_output, ports):
            fae = Fae(port_name=port.name)
            current_output = OutputParsingTool.parse_json_str_to_dictionary(fae.interface.link.show()).get_returned_value()
            with allure.independent_step(f"verify output for {port}"):
                if output != current_output:
                    diff_only = ValidationTool._compute_dict_diff(output, current_output, ignore_fields=[IbInterfaceConsts.LINK_ROUND_TRIP_LATENCY])
                    if diff_only:
                        diff_result.append({"port": port.name, "diff": diff_only})
        assert not diff_result, f"some ports are not configured as expected, diff: {diff_result}"

    with allure.step("unset link configurations"):
        for port in ports:
            fae = Fae(port_name=port.name)
            port.interface.unset(apply=True, ask_for_confirmation=True).verify_result()
            fae.interface.unset(apply=True, ask_for_confirmation=True).verify_result()
        return diff_result
