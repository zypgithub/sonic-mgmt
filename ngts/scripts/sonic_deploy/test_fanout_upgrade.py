import logging

import pytest
import allure

from ngts.constants.constants import CliType
from ngts.scripts.sonic_deploy.test_deploy_and_upgrade import get_info_from_topology, get_hwsku

logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
def test_fanout_upgrade(topology_obj, workspace_path, setup_name, fanout_target_version, platform_params):
    """
    To upgrade fanout to target version.
    """
    if not fanout_target_version:
        pytest.skip("Skip it when fanout_target_version is not specified")

    setup_info = get_info_from_topology(topology_obj, workspace_path)
    setup_info['setup_name'] = setup_name
    install_threads = {}

    with allure.step('Installing fanout image on fanout'):
        for dut in setup_info['duts']:
            fanout_engine_type, fanout_name, fanout = dut['cli_obj'].get_fanout_info(topology_obj, dut['dut_alias'])
            if fanout_engine_type == CliType.SONIC:
                logger.info(f"Installing fanout image on {fanout_name}")
                fanout.deploy_sonic_fanout(topology_obj=topology_obj,
                                           target_version=fanout_target_version,
                                           setup_info=setup_info,
                                           threads_dict=install_threads,
                                           platform_params=platform_params,
                                           fanout_name=fanout_name,
                                           dut_alias=dut['dut_alias'])
            else:
                pytest.skip(f"{fanout_name} is not SONiC.")
