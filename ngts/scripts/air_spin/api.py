from .objects import SetupObj
from .utils import run_simulation_with_mini_mars
from .handle_noga_resources import lock_unlock_vm, add_simulation_id_to_noga, delete_simulation_id_from_noga


class AirSpinApi:
    def __init__(self):
        pass

    def create_simulation(self, setup_name, topology_type, simx_version, dut_name, dut_hwsku, chip_type, base_version, custom_tarball_name, branch,
                          topology, organization_name, custom_links_path, dbs_to_run_path):
        setup_obj = SetupObj(setup_name, topology_type, simx_version, dut_name, dut_hwsku,
                             chip_type, base_version, custom_tarball_name, branch, topology, organization_name, custom_links_path, dbs_to_run_path)
        print(f"Starting to create AIR SIMULATION named:'{setup_obj.setup_name}'")
        setup_obj.allocate_vm_obj()
        try:
            setup_obj.create_files()
            run_simulation_with_mini_mars(setup_obj)
            print(f"Simulation started successfully")
            setup_obj.get_simulation_data()
            add_simulation_id_to_noga(setup_obj.simulation_data["simulation_id"], setup_obj.vm_obj.resource_id)
            self.release_simulation(setup_obj)
        except Exception as e:
            print(f"Simulation failed, error: {e}")
            self.release_simulation(setup_obj)
            raise e

    def release_simulation(self, setup_obj):
        print(f"Releasing simulation: {setup_obj.setup_name}")
        if setup_obj.simulation_data and setup_obj.simulation_data["simulation_id"]:
            delete_simulation_id_from_noga(setup_obj.vm_obj.resource_id)
        print(f"Unlocking the VM")
        lock_unlock_vm(setup_obj.vm_obj.ip, lock=False)

    def get_simulation_data(self, simulation_name):
        pass

    def stop_simulation(self, simulation_name):
        pass

    def destroy_simulation(self, simulation_name):
        pass

    def get_simulation_status(self, simulation_name):
        pass
