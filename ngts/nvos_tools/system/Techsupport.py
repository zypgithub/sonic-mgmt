import logging
import re
from datetime import datetime, timedelta

from ngts.nvos_constants.constants_nvos import SystemConsts, CumulusConsts, NvosConst, ApiType
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.constants.constants import BugHandlerConst
from ngts.nvos_constants.constants_nvos import NvosConst

logger = logging.getLogger()


class TechSupport(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/tech-support/files')
        self.file_name = ""

    def action_upload(self, upload_path, file_name):
        with allure.step("Upload techsupport {file} to '{path}".format(file=file_name, path=upload_path)):
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_upload, TestToolkit.engines.dut,
                                                   self.get_resource_path(), file_name, upload_path)

    def action_delete(self, file_name):
        with allure.step("Delete tech-support: {}".format(file_name)):
            if TestToolkit.devices.dut.switch_type == CumulusConsts.ETH_SWITCH_TYPE and TestToolkit.tested_api == ApiType.OPENAPI:
                resource_path = self.get_resource_path() + '/\\{file-name\\}'
            else:
                resource_path = self.get_resource_path()
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_delete, TestToolkit.engines.dut,
                                                   resource_path, file_name)

    def action_generate(self, engine="", option="", since_time="", test_name=''):
        """
        in the future the command will be nv action generate system tech-support (without files)
        changes to do :
            update self._resource_path in the init method
            remove self.get_resource_path().replace('/files', ' ') in this method
        """
        switch_type = TestToolkit.devices.dut.switch_type
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut

            cmd_out, duration = OperationTime.save_duration('generate tech-support', option, test_name, SendCommandTool.execute_command,
                                                            self.api_obj[TestToolkit.tested_api].action_generate_techsupport, engine,
                                                            self.get_resource_path().replace('/files', ' '), option, since_time)
            cmd_out.ignore_result()
            if 'failed' in cmd_out.info or 'error' in cmd_out.info:
                return cmd_out.info, duration
            if TestToolkit.devices.dut.is_eth():
                self.parse_eth_techsupport_folder_name(cmd_out)
                return CumulusConsts.TECHSUPPORT_FILES_PATH + self.file_name, duration
            else:
                self.parse_ib_techsupport_folder_name(cmd_out)
                return SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name, duration

    def parse_ib_techsupport_folder_name(self, techsupport_res):
        techsupport_res_list = techsupport_res.returned_value.split('\n')
        files_name = "".join([name for name in techsupport_res_list if '.tar.gz' in name])
        files_name = files_name.replace('Generated tech-support', '').split(' ')
        self.file_name = files_name[-1]

    def parse_eth_techsupport_folder_name(self, techsupport_res):
        techsupport_res_list = techsupport_res.returned_value.split('\n')
        for line in techsupport_res_list:
            if "Please send" in line:
                path = line.split("Please send")[-1].strip()
                if ".txz" in path:
                    self.file_name = path.split(".txz")[0].split("/")[-1] + ".txz"
                else:
                    self.file_name = path.split("/")[-1].split()[0]
                return

    def extract_techsupport_files(self, engine, file_name=''):
        self.file_name = file_name if file_name else self.file_name
        with allure.step(f"extract {self.file_name}"):
            logging.info(f"extract {self.file_name}")
            full_path = SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name
            engine.run_cmd('sudo tar -xf ' + full_path + ' -C' + SystemConsts.TECHSUPPORT_FILES_PATH)

    def get_techsupport_files_names(self, engine, expected_files_dict):
        """
        :param engine:
        :param expected_files_dict: the files expected to be in the techsupport .tar.gz
        :return: dict, dict item for example - {sub-folder : list of files contained in that sub-folder)
        """
        with allure.step('Get all tech-support files'):
            logging.info('Get all tech-support files')
            full_path = SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name.replace('.tar.gz', "")
            dict_files = {}
            for sub_folder in expected_files_dict.keys():
                dict_files[sub_folder] = engine.run_cmd('ls ' + full_path + '/' + sub_folder).split()
            return dict_files

    def get_techsupport_empty_files(self, engine, test_support_file='', tech_folder=''):
        """
        :param engine: engine
        :param tech_folder: the tech_folder sub folder in techsupport .tar.gz
        :return: list of the empty files in the tech-support sub folder
        """
        self.file_name = test_support_file if test_support_file else self.file_name
        with allure.step(f'Get all tech-support empty files from {tech_folder}'):
            logging.info(f'Get all tech-support empty files from {tech_folder}')
            full_path = SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name.replace('.tar.gz', "")
            output = engine.run_cmd('sudo find ' + full_path + '/' + tech_folder + " -type f -empty")
            return [file.split('/')[-1] for file in output.split()]

    def cleanup(self, engine):
        engine.run_cmd('sudo rm -rf ' + SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name.replace('.tar.gz', ""))

    def clean_timestamp_techsupport_sdk_files_names(self, file_names):
        return [self.rename_file(name) for name in file_names]

    def rename_file(self, filename):

        sai_sdk_regex = re.compile(r'sai_sdk_dump_\d{2}_\d{2}_\d{4}_\d{2}_\d{2}_(AM|PM)\.(.*)')
        sdk_dump_ext_regex = re.compile(r'(sdk_dump_ext)_\d{1,2}[A-Za-z]{3}\d{4}_\d{2}:\d{2}:\d{2}\.\d{6}_(dev\d+.*)')
        if sai_sdk_regex.match(filename):
            return sai_sdk_regex.sub(r'sai_sdk_dump.\2', filename)
        elif sdk_dump_ext_regex.match(filename):
            return sdk_dump_ext_regex.sub(r'\1_\2', filename)

        return filename

    def get_techsupport_files_list(self, engine, tech_folder):
        """
        :param engine:
        :param tech_folder: :param tech_folder: the tech_folder sub folder in techsupport .tar.gz
        :return: list of files contained in that sub-folder)
        """
        with allure.step(f'Get all tech-support files from {tech_folder}'):
            logging.info(f'Get all tech-support files from {tech_folder}')
            full_path = SystemConsts.TECHSUPPORT_FILES_PATH + self.file_name.replace('.tar.gz', "")
            output = engine.run_cmd('ls ' + full_path + '/' + tech_folder)
            return output.split()

    def check_techsupport_file_age(self, engine, system, tech_support_path: str = '', max_age_hours: int = 24):
        """
            Verify that tech-support file was generated within a specified number of hours.

            :param engine: system engine
            :param system: System() object
            :param tech_support_path: Path to the tech-support file.
            :param max_age_hours: Maximum allowed age of the tech-support file in hours. Default is 24 hours.
        """
        with allure.step(f"Run 'stat {tech_support_path}' and get tech-support file's birth-time"):
            file_info = engine.run_cmd(f"stat {tech_support_path}")
            birth_time_match = re.search(fr'Birth: ({NvosConst.DATE_TIME_REGEX[1]})', file_info)
            birth_time = datetime.strptime(birth_time_match.group(1), BugHandlerConst.TIMESTAMP_FORMATS[4])

            with allure.step(f"Verify last tech-support file was generated in less than 24 hours ago"):
                current_time_str = ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show())
                current_time = datetime.strptime(current_time_str, BugHandlerConst.TIMESTAMP_FORMATS[4])
                assert current_time - birth_time < timedelta(
                    hours=max_age_hours), f"The last tech-support file was generated {birth_time}, more than 24 hours ago"
