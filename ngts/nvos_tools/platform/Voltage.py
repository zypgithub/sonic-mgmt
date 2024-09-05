import logging
import re
import json
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Voltage(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/voltage')

    def get_sensors_list(self, engine, stringtoadd="VOLTAGE_INFO|"):
        """
        the out of the ls commands will be:
            total 0
            "drwxr-xr-x 2 root root 120 Jul  4 10:51 SENSOR NAME 1"
            "drwxr-xr-x 2 root root 120 Jul  4 10:51 SENSOR NAME 2"
            "drwxr-xr-x 2 root root 100 Jul  4 10:51 SENSOR NAME 3"

            /var/run/hw-management/ui/voltage/psu1:
            total 0
            "drwxr-xr-x 2 root root 280 Jul  4 12:41 SENSOR NAME 4"

        :return: list of sensors names, the returned value for the example:
            [SENSOR NAME 1, SENSOR NAME 2, SENSOR NAME 3, SENSOR NAME 4]
        """
        with allure.step('run ls command using voltage path'):
            sensors_path = '/var/run/hw-management/ui/voltage/*'
            sensors = engine.run_cmd('ls -l {} '.format(sensors_path)).splitlines()

        with allure.step('get the sensors list'):
            list_full_path = [x for x in sensors if x.startswith('dr')]
            sensors_list = []
            with allure.step('generate the database table name for each sensor'):
                for item in list_full_path:
                    sensors_list.append(self.get_file_name(item, stringtoadd))

        return sensors_list

    @staticmethod
    def get_file_name(file_full_detailes, stringtoadd=""):
        match = re.search(r'\s([^ ]+$)', file_full_detailes)
        sensor_name = re.sub(r'PMIC-.\+', '', match.group(1))
        sensor_name = sensor_name.replace('+', ' ').replace('_', ' ').replace(' Vol', '')

        return stringtoadd + sensor_name

    def get_cli_sensors_list(self, engine):
        with allure.step('Execute show for voltage sensors'):
            output = self.show()
            cli_sensors_list = json.loads(output).keys()
            return cli_sensors_list
