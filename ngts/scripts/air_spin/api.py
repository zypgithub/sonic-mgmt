from .objects import SetupObj
from .utils import start_deployment_with_mini_mars


class AirSpinApi:
    def __init__(self):
        pass

    def create_simulation(self, setup_name, topology_type, simx_version, dut_name, dut_hwsku, chip_type, base_version, custom_tarball_name, branch, topology, organization_name="SONIC", topology_links_path=""):
        setup_obj = SetupObj(setup_name, topology_type, simx_version, dut_name, dut_hwsku, chip_type, base_version, custom_tarball_name, branch, topology, organization_name, topology_links_path)
        setup_obj.allocate_vm_obj()
        setup_obj.create_files(topology_type)
        start_deployment_with_mini_mars(setup_obj)

    def start_simulation(self, simulation_name):
        pass

    def stop_simulation(self, simulation_name):
        pass

    def destroy_simulation(self, simulation_name):
        pass

    def get_simulation_status(self, simulation_name):
        pass
