import logging

from ngts.nvos_constants.constants_nvos import UfmMadConsts

logger = logging.getLogger()


class RegisterTool:

    @staticmethod
    def get_mst_status(engine):
        logging.info('Get MST PCI loaded module and configuration module')
        return engine.run_cmd('sudo mst status')

    @staticmethod
    def get_mst_register_value(engine, mst_dev_name, reg_name, additional_params=""):
        logging.info(f'Get {reg_name} value {additional_params}')
        return engine.run_cmd(f'sudo mlxreg -d {mst_dev_name} -g --reg_name {reg_name} {additional_params}')

    @staticmethod
    def set_mst_register_value(engine, mst_dev_name, reg_name, set_params, additional_params=""):
        logging.info(f'Set {reg_name} value {additional_params} with {set_params}')
        return engine.run_cmd(
            f'sudo mlxreg -d {mst_dev_name} --reg_name {reg_name} {additional_params} -s {set_params} -y')

    @staticmethod
    def update_pmaos_register(engine, device, admin_status, mst_dev_name, slot_index=0, module_index=0):
        indexes = f"-i slot_index={slot_index},module={module_index}"
        set_params = f"ase=1,e=1,ee=1,admin_status={admin_status}"
        return RegisterTool.set_mst_register_value(engine, mst_dev_name, UfmMadConsts.PMAOS_REGISTER,
                                                   set_params, additional_params=indexes)

    @staticmethod
    def update_prei_register(engine, mst_dev_name, local_port):
        indexes = f"-i local_port={local_port},plane_ind=0x0,lp_msb=0x0,pnat=0x0"
        set_params = "error_type_admin=0x4,error_injection_time=10,time_res=1"
        return RegisterTool.set_mst_register_value(engine, mst_dev_name, UfmMadConsts.PREI_REGISTER,
                                                   set_params, additional_params=indexes)
