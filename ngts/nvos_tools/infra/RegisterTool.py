import logging

from ngts.nvos_constants.constants_nvos import UfmMadConsts
from ngts.nvos_tools.infra.EngineAdapterTool import EngineAdapterTool

logger = logging.getLogger()


class RegisterTool:

    @staticmethod
    def _run_cmd(engine, cmd):
        """Run command on engine, handling both SSH and serial engines."""
        return EngineAdapterTool.run_cmd(engine, cmd, validate=True)

    @staticmethod
    def get_mst_status(engine):
        logging.info('Get MST PCI loaded module and configuration module')
        return RegisterTool._run_cmd(engine, 'sudo mst status')

    @staticmethod
    def get_mst_register_value(engine, mst_dev_name, reg_name, additional_params="", grep_pattern='""'):
        logging.info(f'Get {reg_name} value {additional_params}')
        cmd = f'sudo mlxreg -d {mst_dev_name} -g --reg_name {reg_name} {additional_params} | grep {grep_pattern}'
        return RegisterTool._run_cmd(engine, cmd)

    @staticmethod
    def set_mst_register_value(engine, mst_dev_name, reg_name, set_params, additional_params=""):
        logging.info(f'Set {reg_name} value {additional_params} with {set_params}')
        cmd = f'sudo mlxreg -d {mst_dev_name} --reg_name {reg_name} {additional_params} -s {set_params} -y'
        return RegisterTool._run_cmd(engine, cmd)

    @staticmethod
    def update_pmaos_register(engine, device, admin_status, mst_dev_name, slot_index=0, module_index=0):
        indexes = f"-i slot_index={slot_index},module={module_index}"
        set_params = f"ase=1,e=1,ee=1,admin_status={admin_status}"
        return RegisterTool.set_mst_register_value(engine, mst_dev_name, UfmMadConsts.PMAOS_REGISTER,
                                                   set_params, additional_params=indexes)

    @staticmethod
    def update_prei_register(engine, mst_dev_name, local_port):
        indexes = f"-i local_port=0x{local_port},plane_ind=0x0,lp_msb=0x0,pnat=0x0"
        set_params = "error_type_admin=0x4,error_injection_time=0xFFFF,time_res=1"
        return RegisterTool.set_mst_register_value(engine, mst_dev_name, UfmMadConsts.PREI_REGISTER,
                                                   set_params, additional_params=indexes)

    @staticmethod
    def get_paos_register(engine, mst_dev_name, local_port, lp_msb="0", plane_ind="0"):
        indexes = f"-i local_port={local_port},lp_msb={lp_msb},plane_ind={plane_ind}"
        return RegisterTool.get_mst_register_value(engine, mst_dev_name, UfmMadConsts.PAOS_REGISTER,
                                                   additional_params=indexes, grep_pattern='""')

    @staticmethod
    def update_paos_register(engine, mst_dev_name, local_port, admin_status, lp_msb="0", plane_ind="0"):
        indexes = f"-i local_port={local_port},lp_msb={lp_msb},plane_ind={plane_ind}"
        set_params = f"admin_status={admin_status},ase=1"
        return RegisterTool.set_mst_register_value(engine, mst_dev_name, UfmMadConsts.PAOS_REGISTER,
                                                   set_params, additional_params=indexes)

    @staticmethod
    def inject_prei_error(engine, mst_dev_name, local_port, error_type_admin, error_injection_time):
        """
        Inject error via PREI register to trigger/test PHY recovery.

        This method uses the --set flag format for PREI register manipulation,
        which is the preferred format for error injection operations.

        Args:
            engine: DUT SSH engine
            mst_dev_name: MST device path (e.g., /dev/mst/mt54004_pciconf2)
            local_port: Local port number (decimal string)
            error_type_admin: Error type (4 = trigger recovery)
            error_injection_time: Injection time
                - 0xFFFF: Always fail (broken cable simulation)
                - 5: Noise (flaky cable simulation)
                - 0: Disable error injection

        Returns:
            Command output from engine.run_cmd()
        """
        cmd = (f"sudo mlxreg -d {mst_dev_name} --reg_name {UfmMadConsts.PREI_REGISTER} "
               f"--set 'local_port={local_port},error_type_admin={error_type_admin},"
               f"error_injection_time={error_injection_time}' --yes")
        logging.info(f"Injecting PREI error: local_port={local_port}, "
                     f"error_type_admin={error_type_admin}, error_injection_time={error_injection_time}")
        return engine.run_cmd(cmd)
