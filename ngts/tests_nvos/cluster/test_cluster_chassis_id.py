import logging
import random
import re

import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat, ChassisLocationConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

from ngts.tests_nvos.cluster.cluster_tools import ClusterTools

from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts


logger = logging.getLogger()


@pytest.fixture(scope='function', autouse=True)
def enable_stop_cluster(setup_name):
    cluster = Cluster()
    ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json)
    yield
    ClusterTools.stop_cluster(cluster, OutputFormat.json)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_chassis_id(engines, devices, test_api):

    TestToolkit.tested_api = test_api
    with allure.step("Create Cluster object"):
        cluster = Cluster()
        platform = Platform()
        sdn = Sdn()
        file_type = ClusterConsts.NMX_CONTROLLER_CONFIG_CHASSIS_MAPPING

    with allure.step("Get chassis-id"):
        output = platform.chassis_location.show()
        chassis_id_serial = OutputParsingTool.parse_show_output_to_dict(output).get_returned_value()[ChassisLocationConsts.CHAS_SN]
        if chassis_id_serial == 'N/A':
            pytest.skip("no serial number available")

    with allure.step("Update chassis-id mapping with invalid number - should fail"):
        invalid_mapping_ids = [-1, 1000]
        for mapping_id in invalid_mapping_ids:
            cluster.action_update_chassis_id(mapping_id=mapping_id).verify_result(False)

    with allure.step("Update chassis-id mapping good flow"):
        mapping_id = random.randint(1, 255)
        cluster.action_update_chassis_id(mapping_id=mapping_id).verify_result()

    try:
        with allure.step(f"Generate {ClusterConsts.NMX_CONTROLLER_CONFIG_CHASSIS_MAPPING} file"):
            output = sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn().get_returned_value()
            filename = get_name_from_generate_config_file(output)

        with allure.step("Verify content of config file is as expected"):
            dict_output = OutputParsingTool.parse_show_output_to_dict(
                sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[
                    file_type].files.show()).get_returned_value()
            path = dict_output[filename]['path']
            current_config_content = engines.dut.run_cmd(f"sudo cat {path} | grep chassis")
            expected_contect = f'chassisId{mapping_id} {chassis_id_serial}'
            ValidationTool.verify_expected_output(current_config_content, expected_contect)

    finally:
        with allure.step("Delete config file"):
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.file_name[
                filename].action_delete().verify_result()


def get_name_from_generate_config_file(output):
    match = re.search(r'App config file (\S+)', output)
    filename = match.group(1) if match else None
    return filename
