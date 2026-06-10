import pytest
import logging

from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_constants.constants_nvos import ChassisLocationConsts, OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

logger = logging.getLogger()


@pytest.fixture(scope="module")
def cluster_and_sdn(setup_name, devices, standalone_system):
    """Enable cluster, yield (cluster, sdn), then disable cluster."""
    if standalone_system:
        pytest.skip("Tray admin state tests require non-standalone setup (multi-switch rack)")
    cluster = Cluster()
    sdn = Sdn()
    ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json, devices=devices)
    ClusterTools.wait_until_app_expected_status(cluster, ClusterConsts.NMX_CONTROLLER, 'ok')
    yield cluster, sdn
    cluster.unset(apply=True)
    ClusterTools.wait_for_apps_to_be_in_wanted_state(
        cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')


@pytest.fixture(scope="module")
def chassis_info():
    """Get chassis serial number and slot number from platform."""
    platform = Platform()
    chassis_location = OutputParsingTool.parse_show_output_to_dict(
        platform.chassis_location.show()).get_returned_value()
    return {
        'slot-number': chassis_location.get(ChassisLocationConsts.SLOT_NUM),
        'chassis-sn': chassis_location.get(ChassisLocationConsts.CHAS_SN),
    }


@pytest.fixture(scope="module")
def tray_topology_config(setup_name):
    """
    Per-setup tray model from RegressionConfigurations.tray_topology.

    Missing setup_name: pytest.skip (not a failure). Tests that need a lab model
    must list the setup there before running.
    """
    tray_info = Configurations.tray_topology.get(setup_name)
    if not tray_info:
        pytest.skip(f"No tray topology defined for setup '{setup_name}'")
    return tray_info


@pytest.fixture(scope="module")
def expected_tray_count(tray_topology_config):
    """Expected len(nv show sdn trays) == switch_nodes + compute_nodes from lab config."""
    return tray_topology_config['switch_nodes'] + tray_topology_config['compute_nodes']
