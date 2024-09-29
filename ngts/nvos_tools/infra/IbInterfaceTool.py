import logging
import time

from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.LinuxCmdBuilderTool import LinuxCmdBuilderTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class IbInterfaceTool:

    @staticmethod
    def switch_port_connection_mode(port_name, connection_mode):
        with allure.step(f"Set connection-mode for {port_name} to {connection_mode}"):
            interface = Interface(parent_obj=None, port_name=port_name)
            interface.link.set(op_param_name=LinkDetectionConsts.CONNECTION_MODE,
                               op_param_value=connection_mode, apply=True,
                               ask_for_confirmation=True).verify_result()

    @staticmethod
    def switch_port_connection_mode_to_default(port_name):
        with allure.step(f"Set connection-mode for {port_name} default"):
            interface = Interface(parent_obj=None, port_name=port_name)
            interface.link.unset(op_param_name=LinkDetectionConsts.CONNECTION_MODE,
                                 apply=True, ask_for_confirmation=True).verify_result()

    @staticmethod
    def simulate_plugin_module_event(engine, device, module_index, mst_dev_name, sleep):
        with allure.step(f"Simulate plugin event for module {module_index}"):
            admin_status = "1"  # The code to simulate plug event
            RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                               admin_status=admin_status, module_index=module_index)
            time.sleep(sleep)

    @staticmethod
    def simulate_unplug_module_event(engine, device, module_index, mst_dev_name, sleep):
        with allure.step(f"Simulate unplug event for module {module_index}"):
            admin_status = "0xe"  # The code to simulate unplug event
            RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                               admin_status=admin_status, module_index=module_index)
            time.sleep(sleep)

    @staticmethod
    def get_mst_dev_name(engines, asic_conf_dict, module_name=None, port_name=None):
        fae = Fae(port_name=port_name)
        if is_redmine_issue_active([4034283]):
            # in future needs to handle xdr ports too
            IbInterfaceTool.switch_port_connection_mode(port_name, IbInterfaceConsts.NDR)

        with allure.step(f"Find correct mst_dev_name for {module_name or port_name}"):
            output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
                fae.port.interface.show()).get_returned_value()
            asic_number = output_fae_port.get(IbInterfaceConsts.PRIMARY_ASIC, "0")
            assert asic_number is not None, "primary-asic is None"
            asic_dev_id_number = f"DEV_ID_ASIC_{asic_number}"
            asic_mapping_number = asic_conf_dict[asic_dev_id_number]
            cmd = LinuxCmdBuilderTool("sudo mst status -v").grep("pciconf").grep(f"{asic_mapping_number}").awk_print(
                "2").build()
            mst_dev_name = engines.dut.run_cmd(cmd)
            return mst_dev_name
