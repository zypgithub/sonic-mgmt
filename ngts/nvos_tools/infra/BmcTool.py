import json
import logging
from typing import Dict

from retry import retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import DatabaseConst
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.tests_nvos.constants import PRODUCTION, DEVELOPMENT
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import ADMIN
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ResultObj import ResultObj

logger = logging.getLogger()


class BmcTool:
    BASE_URL = "https://10.0.1.1/redfish/v1/"
    USER_NAME = ADMIN
    PLATFORM_COMPONENTS_DICT = dict()

    @staticmethod
    def _get_bmc_password(engine: LinuxSshEngine):
        return TpmTool(engine).get_bmc_admin_password_from_tpm()

    @staticmethod
    def reset(engine: LinuxSshEngine):
        password = BmcTool._get_bmc_password(engine)
        cmd = (f"""curl -k -u {BmcTool.USER_NAME}:{password} -H "Content-Type: application/json" -X POST """ +
               """-d '{"ResetType": "GracefulRestart"}' """ +
               f"""{BmcTool.BASE_URL}Managers/BMC_0/Actions/Manager.Reset""")
        response = engine.run_cmd(cmd)
        if "The request completed successfully" not in response:
            raise Exception("Shutdown command failed with the following response:\n" + response)

    @staticmethod
    def fetch_and_install_platform_component(platform_component, path, name, filename, topology_obj, test_name) -> ResultObj:
        with allure.step(f'Fetch {name} image from: {path}'):
            platform_component.action_fetch(path).verify_result()

        with allure.step(f'installing image {name}'):
            return BmcTool.install_fw_image(platform_component, test_name, filename, topology_obj, name)

    @staticmethod
    def verify_platform_component_version(platform_component, expected_version: str):
        with allure.step(f'Making sure component is now on version {expected_version}'):
            platform_component_output = OutputParsingTool.parse_json_str_to_dictionary(
                platform_component.show()).verify_result()
            output_version = platform_component_output[PlatformConsts.FW_ACTUAL]
            logger.info(f"Found version: {output_version}")

            assert output_version == expected_version, \
                f"firmware is {output_version}, expected {expected_version} after the install"

    @staticmethod
    def compare_bmc_version_issu_module(engines, expected_version: str):
        with allure.step(f'Making sure component is now on version {expected_version}'):
            bmc_output = Tools.DatabaseTool.sonic_db_cli_hgetall(engine=engines.dut, asic="",
                                                                 db_name=DatabaseConst.STATE_DB_NAME,
                                                                 table_name='\"SYSTEM_COMPONENTS|BMC\"')

            assert bmc_output == expected_version, \
                f"firmware is {bmc_output}, expected {expected_version} after the install"

    @staticmethod
    def _get_fw_component_version_info(component_name, version):
        device = TestToolkit.devices.dut
        fw_path = device.fw_versions_json_file_path
        with allure.step(f'Read platform components info from json {fw_path}'):
            if not BmcTool.PLATFORM_COMPONENTS_DICT:
                with open(fw_path, 'r') as file:
                    BmcTool.PLATFORM_COMPONENTS_DICT = json.load(file)
            platform_components_dict = BmcTool.PLATFORM_COMPONENTS_DICT
            provisioning = DEVELOPMENT if SecureBootTool.is_dev_system(TestToolkit.engines.dut) else PRODUCTION
            component_image_info = platform_components_dict[provisioning][component_name][version]
            return component_image_info['path'], component_image_info['filename'], component_image_info['version_name']

    @staticmethod
    def get_fw_component_version_dict(component_name, version):
        device = TestToolkit.devices.dut
        fw_path = device.fw_versions_json_file_path
        with allure.step(f'Read platform components info from json {fw_path}'):
            if not BmcTool.PLATFORM_COMPONENTS_DICT:
                with open(fw_path, 'r') as file:
                    BmcTool.PLATFORM_COMPONENTS_DICT = json.load(file)
            platform_components_dict = BmcTool.PLATFORM_COMPONENTS_DICT
            provisioning = DEVELOPMENT if SecureBootTool.is_dev_system(TestToolkit.engines.dut) else PRODUCTION
            component_image_info = platform_components_dict[provisioning][component_name][version]
            return component_image_info

    @staticmethod
    @retry(AssertionError, tries=14, delay=30)
    def verify_background_copy_completed(platform, erot_name):
        with allure.step(f"Verifying {erot_name} completed background copy"):
            firmware_shown: Dict[str, str] = OutputParsingTool.parse_json_str_to_dictionary(
                platform.firmware.erot_id[erot_name].show()).get_returned_value()
            background_copy_status = firmware_shown[PlatformConsts.FW_BACKGROUND_COPY_STATUS]
            assert background_copy_status.lower() == "Completed".lower(), "Background copy status is not completed"

    @staticmethod
    def get_fw_component_version_latest(component_name):
        return BmcTool._get_fw_component_version_info(component_name, "latest")

    @staticmethod
    def get_fw_component_version_previous(component_name):
        return BmcTool._get_fw_component_version_info(component_name, "previous")

    @staticmethod
    def get_bmc_ip_addresses(engines, topology_obj):
        """
        get ipv4 using noga and ipv6 using curl -k -u <user>>:<password> https://<bmc_ip>/redfish/v1/Managers/BMC_0/EthernetInterfaces/eth0
        :param engines:
        :param topology_obj:
        :return:
        """
        ip_addresses = {}
        with allure.step("Get bmc ipv4 from noga"):
            bmc_ipv4_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
                'bmc_ip']
            assert bmc_ipv4_address, "Could you please check the BMC IP box in NOGA? It appears to be empty"
            logger.info(f"the bmc IPv4 is {bmc_ipv4_address}")
            ip_addresses["IPv4"] = bmc_ipv4_address

        with allure.step("Sending a curl request to get the IPv6 address from the BMC"):
            curl_request = f'curl -s -k -u {BmcTool.USER_NAME}:{BmcTool._get_bmc_password(engines.dut)} https://{bmc_ipv4_address}/redfish/v1/Managers/BMC_0/EthernetInterfaces/eth0 | python3 -m json.tool'
            eth0_details = OutputParsingTool.parse_json_str_to_dictionary(
                engines.dut.run_cmd(curl_request)).verify_result()
            ipv6_data = eth0_details["IPv6Addresses"]
            slaac_address = next(
                (address['Address'] for address in ipv6_data if address['AddressOrigin'] == 'SLAAC'),
                None  # If no SLAAC address is found, return None
            )
            ip_addresses["IPv6"] = slaac_address
            return ip_addresses

    @staticmethod
    def install_fw_image(platform_component, test_name, filename, topology_obj, name) -> ResultObj:
        component_name = platform_component.get_resource_basename().lower()
        res_obj, duration = OperationTime.save_duration(f'{component_name} install with reboot', '',
                                                        test_name,
                                                        platform_component.files.file_name[
                                                            filename].action_file_install_with_reboot,
                                                        topology_obj=topology_obj)
        return res_obj
