import pytest

from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.generic_aaa_accounting_testing import *
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.generic_remote_aaa_testing import *
from ngts.tests_nvos.skynet.constants import TacacsSkynetServer
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch

logger = logging.getLogger()


@pytest.mark.skip_clear_config
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_configure_skynet_envrionemnt(topology_obj, engines, devices, test_api, has_loopbox, standalone_system,
                                      setup_name):
    """
    @summary: Basic config flow to set up skynet setup with the following config:
        1. configure Tacacs server
        2. on Juliet machines) start cluster functionality
    """
    TestToolkit.tested_api = test_api
    with allure.step(f'fetching environment details'):
        if isinstance(devices.dut, JulietSwitch):
            skynet_config_obj = SkynetJulietConfig
            switch_type = "juliet"
        else:
            skynet_config_obj = SkynetIbConfig
            switch_type = "ib"

    with allure.step(f'Configuring Skynet environment on {switch_type} setup'):
        skynet_config_obj = skynet_config_obj(devices, engines, has_loopbox, standalone_system, setup_name)
        skynet_config_obj.configure_setup()


class SkynetConfig:
    def __init__(self, devices, engines, has_loopbox, standalone_system, setup_name):
        """
            @summary: This class is a base class that include functionality to configure Skynet setups
        """
        self.devices = devices
        self.engines = engines
        self.setup_name = setup_name
        self.has_loopbox = has_loopbox
        self.standalone_system = standalone_system

    def configure_setup(self):
        pass

    def configure_tacacs(self):
        """
            @summary: This function applies Tacacs configuration on the dut
            the Tacacs details are in the constants.py file on this folder
        """
        logger.info("Configuring Tacacs server")
        remote_aaa_type = RemoteAaaType.TACACS
        server_by_addr_type = TacacsSkynetServer.SERVER_BY_ADDRESSING_TYPE
        with allure.step(f'Configure {remote_aaa_type} server'):
            addressing_type = AddressingType.IPV4
            tacacs = System().aaa.tacacs
            server = server_by_addr_type[addressing_type].copy()
            server.configure(self.engines)
            tacacs.enable(apply=True, verify_res=False)


class SkynetIbConfig(SkynetConfig):
    """
        @summary: This class include skynet configuration functionality for ib switches (aka non-juliet) setups
    """

    def configure_setup(self):
        """
            @summary: This function handles setup config for IB switches setups it will do:
            A. Applies Tacacs configuration on the dut
        """
        with allure.step(f'Configuring Skynet environment'):
            self.configure_tacacs()


class SkynetJulietConfig(SkynetConfig):
    """
        @summary: This class include skynet configuration functionality for juliet switches setups
    """

    def configure_setup(self):
        """
            @summary: This function handles setup config for IB switches setups it will do:
            A. Applies Tacacs configuration on the dut
            B. configure Cluster on switch
        """
        with allure.step(f'Configuring Skynet environment'):
            self.configure_tacacs()
            self.configure_cluster(self.devices, self.engines, self.has_loopbox,
                                   self.standalone_system, self.setup_name, perform_cleanup=False)

    @disabled_access_ports
    def configure_cluster(self, devices, engines, has_loopbox, standalone_system, setup_name, perform_cleanup):
        """
            @summary: This function configure cluster on the juliet switch
            note - it will use the decorator disabled_access_ports to perform additional configurations
        """
        with allure.step("Create and start Cluster object"):
            cluster = Cluster()
            logger.info("Setting cluster state to enabled")
            output_format = OutputFormat.json
            ClusterTools.start_cluster(cluster, setup_name, output_format)
