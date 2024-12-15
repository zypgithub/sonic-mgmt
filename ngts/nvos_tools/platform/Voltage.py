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
            "drwxr-xr-x 2 root root 120 Jul  4 10:51 SENSOR-NAME_1"
            "drwxr-xr-x 2 root root 120 Jul  4 10:51 SENSOR-NAME_2"
            "drwxr-xr-x 2 root root 100 Jul  4 10:51 SENSOR-NAME_3"

            /var/run/hw-management/ui/voltage/psu1:
            total 0
            "drwxr-xr-x 2 root root 280 Jul  4 12:41 SENSOR+NAME+4"

        :return: list of sensors names, the returned value for the example:
            ['SENSOR-NAME_1', 'SENSOR-NAME_2', 'SENSOR-NAME_3', 'SENSOR+NAME+4']
        """
        with allure.step('run ls command using voltage path'):
            sensors_path = '/var/run/hw-management/ui/voltage/*'
            sensors = engine.run_cmd('ls -l {} '.format(sensors_path)).splitlines()

        return [sensor.split()[-1] for sensor in sensors if sensor.startswith('dr')]

    def get_cli_sensors_list(self, engine):
        with allure.step('Execute show for voltage sensors'):
            output = self.show()
            cli_sensors_list = json.loads(output).keys()
            return list(cli_sensors_list)
