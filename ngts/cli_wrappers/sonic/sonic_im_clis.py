import allure
import logging
import json
import os

from ngts.helpers.interface_helpers import get_alias_number
from ngts.helpers.sonic_branch_helper import get_sonic_branch
from ngts.constants.constants import InfraConst, IndependentModuleConst, SonicConst
from ngts.cli_util.cli_parsers import parse_show_interfaces_transceiver_eeprom

logger = logging.getLogger()


class SonicImClis:
    def __init__(self, engine, cli_obj):
        self.engine = engine
        self.cli_obj = cli_obj
        self.chassis_cli = self.cli_obj.chassis
        self.interface_cli = self.cli_obj.interface
        self.general_cli = self.cli_obj.general

    def is_system_supports_im(self):
        """
        @summary: This method is for check if system supports IM
        @return: True in case system is SPC3 or higher
        """
        if self.general_cli.is_spc1() or self.general_cli.is_spc2():
            return False
        else:
            return True

    def is_im_enabled(self):
        """
        @summary: This method is for check if SAI_INDEPENDENT_MODULE_MODE set to 1 in sai.profile
        @return: True in case SAI_INDEPENDENT_MODULE_MODE set to 1 else False
        """
        parse_platform_summary = self.chassis_cli.parse_platform_summary()
        platfrom = parse_platform_summary["Platform"]
        hwsku = parse_platform_summary["HwSKU"]

        im_sai_param = self.engine.run_cmd(
            f'sudo cat {SonicConst.SAI_PROFILE_FILE_PATH.format(PLATFORM=platfrom, HWSKU=hwsku)} | grep '
            f'{IndependentModuleConst.IM_SAI_ATTRIBUTE_NAME}')
        if im_sai_param:
            if im_sai_param.split("=")[1] == '1':
                return True
            else:
                return False

    def enable_im_in_sai(self):
        """
        @summary: This method is for set SAI_INDEPENDENT_MODULE_MODE to 1 in sai.profile
        """
        parse_platform_summary = self.chassis_cli.parse_platform_summary()
        platfrom = parse_platform_summary["Platform"]
        hwsku = parse_platform_summary["HwSKU"]

        if not self.is_im_enabled():
            logger.info(f'Set {IndependentModuleConst.IM_SAI_ATTRIBUTE_NAME} to 1 in '
                        f'{SonicConst.SAI_PROFILE_FILE_PATH.format(PLATFORM=platfrom, HWSKU=hwsku)}')
            self.engine.run_cmd(f'sudo bash -c \'echo "{IndependentModuleConst.IM_SAI_ATTRIBUTE_NAME}=1" >> '
                                f'{SonicConst.SAI_PROFILE_FILE_PATH.format(PLATFORM=platfrom, HWSKU=hwsku)}\'')

    def is_ms_hwsku(self):
        """
        @summary: This method is for checking if DUT having Microsoft HWSKU
        """
        parse_platform_summary = self.chassis_cli.parse_platform_summary()
        hwsku = parse_platform_summary["HwSKU"]
        return any(item in hwsku for item in IndependentModuleConst.PLATFORM_GENERATION)

    def get_ports_supporting_im(self, dut_ports_number_dict):
        """
        @summary: This method is for get DUT ports supporting IM
        @return: dict with AOC cables, Passive Copper cables and all cables which are under SW control
        """
        ports_with_im_support = []
        ports_numbers_to_check = []
        parse_platform_summary = self.chassis_cli.parse_platform_summary()
        platfrom = parse_platform_summary["Platform"]
        internal_ports = ['Ethernet224', 'Ethernet232', 'Ethernet240', 'Ethernet248']
        for index, port_name in enumerate(dut_ports_number_dict):
            if '4280' in platfrom and port_name in internal_ports:
                continue
            ports_numbers_to_check.append(str(int(dut_ports_number_dict[port_name]) - 1))
        if ports_numbers_to_check:
            ports_numbers_to_check = ",".join(ports_numbers_to_check)
            cmd = "for i in {%s}; do sudo cat /sys/module/sx_core/asic0/module$i/control; done" % ports_numbers_to_check
            output = self.engine.run_cmd(cmd)
            split_output = output.splitlines()
            for index, port_name in enumerate(dut_ports_number_dict):
                if '4280' in platfrom and port_name in internal_ports:
                    continue
                if int(split_output[index]) == 1:
                    ports_with_im_support.append(port_name)
        active_optical_cables = self.get_active_optic_cables(ports_with_im_support)
        passive_copper_cables = list(filter(lambda x: x not in active_optical_cables, ports_with_im_support))
        logger.info(f'Ports supporting IM are {ports_with_im_support}'
                    f'\n DUT active optical cables plug in at ports {active_optical_cables}. \n Passive coppers plug in'
                    f' at ports {passive_copper_cables}')

        return {'aoc_cables': active_optical_cables,
                'passive_copper_cables': passive_copper_cables,
                'all_cables': ports_with_im_support}

    def disable_autoneg_on_ports_supporting_im(self, port_supporting_im):
        """
        @summary: This method is for disable auto negotiation at ports supporting IM
        """
        logger.info(f'Disabling autoneg for ports {port_supporting_im}')
        for port in port_supporting_im:
            self.interface_cli.config_auto_negotiation_mode(port, "disabled")
        self.general_cli.save_configuration()

    def enable_autoneg_on_passive_copper(self, port_supporting_im):
        """
        @summary: This method is for disable auto negotiation at ports supporting IM
        """
        logger.info(f'Enabling autoneg for ports {port_supporting_im}')
        for port in port_supporting_im:
            self.interface_cli.config_auto_negotiation_mode(port, "enabled")
        self.general_cli.save_configuration()

    def enable_cmis_mgr_in_pmon_file(self, platform_params):
        """
        @summary: This method is for enable CMIS in pmon file
        @param: platform_params: platform_params fixture
        """
        skip_xcvrd_cmis_mgr_flag = 'skip_xcvrd_cmis_mgr'
        cmd = f'sudo sed -i \'s/"{skip_xcvrd_cmis_mgr_flag}": true/"{skip_xcvrd_cmis_mgr_flag}": false/\' ' \
            f'{SonicConst.PMON_DAEMON_CONTROL_JSON_PATH.format(PLATFORM=platform_params["platform"])}'
        self.engine.run_cmd(cmd)

    def dut_ports_number_dict(self, topology_obj, is_community=False):
        """
        @summary: This method is return logical to physical port mapping for topology active ports
        @param: topology_obj: topology_obj fixture
        @param: is_community: if function call for community setup
        """
        dut_ports_number_dict = {}
        ports_aliases_dict = self.interface_cli.parse_ports_aliases_on_sonic()
        if is_community:
            ports = self.interface_cli.get_admin_up_ports()
        else:
            ports = topology_obj.players_all_ports['dut']
        for port in ports:
            dut_ports_number_dict[port] = get_alias_number(ports_aliases_dict[port])
        return dut_ports_number_dict

    def upload_cmis_files(self, platform_params, chip_type):
        platform = platform_params['platform']
        hwsku = platform_params['hwsku']
        shared_cmis_path = InfraConst.MARS_CMIS_FOLDER_PATH

        logger.info("Copy Independent Module files")
        media_setting_file_path = f'{shared_cmis_path}{chip_type.lower()}_{IndependentModuleConst.MEDIA_SETTINGS_FILE_NAME}'

        logger.info(f'Copy file {media_setting_file_path} to /tmp directory on a switch')
        self.engine.copy_file(source_file=media_setting_file_path,
                              dest_file=IndependentModuleConst.MEDIA_SETTINGS_FILE_NAME,
                              file_system='/tmp/',
                              overwrite_file=True, verify_file=False)
        self.engine.run_cmd(f'sudo mv /tmp/{IndependentModuleConst.MEDIA_SETTINGS_FILE_NAME} '
                            f'{IndependentModuleConst.IM_INTERFACE_SETTINGS_FILE_PATH.format(PLATFORM=platform, HWSKU=hwsku)}')

        logger.info(f'Copy file {shared_cmis_path}{IndependentModuleConst.OPTICS_SI_SETTINGS_FILE_NAME} '
                    f'to /tmp directory on a switch')
        self.engine.copy_file(source_file=f'{shared_cmis_path}{IndependentModuleConst.OPTICS_SI_SETTINGS_FILE_NAME}',
                              dest_file=IndependentModuleConst.OPTICS_SI_SETTINGS_FILE_NAME, file_system='/tmp/',
                              overwrite_file=True, verify_file=False)
        self.engine.run_cmd(f'sudo mv /tmp/{IndependentModuleConst.OPTICS_SI_SETTINGS_FILE_NAME}'
                            f' {IndependentModuleConst.IM_INTERFACE_SETTINGS_FILE_PATH.format(PLATFORM=platform, HWSKU=hwsku)}')

    def update_port_lanes_in_config_db(self, platform_params, im_ports):
        if platform_params.host_name in ['r-moose-01', 'mtvr-moose-04']:
            with allure.step("Change port lanes to 4 for IM ports at Community moose setups"):
                config_db = self.general_cli.get_config_db()
                for port in im_ports:
                    lanes_to_use = [lane for lane in config_db['PORT'][port]['lanes'].split(',')][:4]
                    config_db['PORT'][port]['lanes'] = ','.join(lanes_to_use)
                with open('/tmp/config_db.json', 'w') as f:
                    json.dump(config_db, f, indent=4)
                os.chmod('/tmp/config_db.json', 0o777)
                self.engine.copy_file(source_file='/tmp/config_db.json',
                                      dest_file="config_db.json", file_system='/tmp/',
                                      overwrite_file=True, verify_file=False)
                self.engine.run_cmd("sudo cp /tmp/config_db.json /etc/sonic/config_db.json")
                self.general_cli.reload_configuration(force=True)

    def get_active_optic_cables(self, sw_control_cable_list):
        sfputil_eeprom_output = self.engine.run_cmd('sudo sfputil show eeprom', validate=True)
        parsed_eeprom_info_dict = parse_show_interfaces_transceiver_eeprom(sfputil_eeprom_output)
        aoc_list = []
        for cable in sw_control_cable_list:
            vendor_pn = parsed_eeprom_info_dict[cable].get('Vendor PN', '').strip()
            if vendor_pn in IndependentModuleConst.AOC_VENDOR_PN:
                aoc_list.append(cable)
        return aoc_list

    def sw_controlled_aoc_cables(self, sw_control_dict):
        """
        @summary: This method is checking if aoc cables present at setup
        @param: topology_obj: topology_obj fixture
        @return: list of aoc cables if any or None
        """
        if sw_control_dict:
            if sw_control_dict.get('aoc_cables'):
                return sw_control_dict.get('aoc_cables')
        else:
            return None

    def cleanup_sai_profile_flag(self, platform_params):
        """
        @summary: This method is removing the flag in case we have 'SAI_INDEPENDENT_MODULE_MODE=0'
        @param: platform_params: platform_params fixture
        """
        platform = platform_params.platform
        hwsku = platform_params.hwsku

        attribute_name = IndependentModuleConst.IM_SAI_ATTRIBUTE_NAME
        file_path = SonicConst.SAI_PROFILE_FILE_PATH.format(PLATFORM=platform, HWSKU=hwsku)
        cmd = f"sudo sed -i '/^{attribute_name}=0$/d' {file_path}"
        self.engine.run_cmd(cmd)

    def enable_im(self, topology_obj, platform_params, chip_type, enable_im=True):
        """
        @summary: This method is for enable IM feature at DUT
        @param: topology_obj: topology_obj fixture
        @param: platform_params: platform_params fixture
        @param: chip_type: chip_type fixture
        @param: enable_im: flag for enable IM by default
        """
        # TODO: This is WA on mtvr-moose-08 ci setup for RM#4154761
        from infra.tools.redmine.redmine_api import is_redmine_issue_active
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        if is_redmine_issue_active([4154761])[0] and "mtvr-moose-08" in dut_name:
            logger.info('IM is not enabled on mtvr-moose-08 due to RM#4154761')
            return

        with allure.step('Check if system supports IM'):
            sonic_branch = get_sonic_branch(topology_obj)
            skip_for_release = ['201911', '202012', '202205', '202211', '202305']
            with allure.step('Check if SPC3 or higher and is Microsoft SKU applied at system'):
                if self.is_system_supports_im() and self.is_ms_hwsku():
                    with allure.step('Check if setup having cables that supports IM'):
                        if "simx" not in platform_params.platform:
                            with allure.step('Check if SONiC branch supports IM'):
                                if sonic_branch not in skip_for_release:
                                    with allure.step('Check if IM enabled by default, if not - enable it'):
                                        if enable_im and not self.is_im_enabled():
                                            self.enable_im_in_sai()
                                            if self.is_im_enabled():
                                                with allure.step('Upload IM files files, skip cmis_mgr'):
                                                    logger.info(f'Configure IM at DUT')
                                                    self.upload_cmis_files(platform_params, chip_type)
                                                    self.enable_cmis_mgr_in_pmon_file(platform_params)
