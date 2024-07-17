import logging
import time
from retry import retry
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType, SystemConsts, HealthConsts, ActionConsts
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.system.Lldp import Lldp
from ngts.nvos_tools.system.Security import Security
from ngts.nvos_tools.system.Syslog import Syslog
from ngts.nvos_tools.system.Ntp import Ntp
from ngts.nvos_tools.system.Ztp import Ztp
from ngts.nvos_tools.system.Stats import Stats
from ngts.nvos_tools.system.Image import Image
from ngts.nvos_tools.system.Reboot import Reboot
from ngts.nvos_tools.system.Profile import Profile
from ngts.nvos_tools.system.Config import Config
from ngts.nvos_tools.system.Log import Log
from ngts.nvos_tools.system.Debug_log import DebugLog
from ngts.nvos_tools.system.SnmpServer import SnmpServer
from ngts.nvos_tools.system.Techsupport import TechSupport
from ngts.nvos_tools.system.Aaa import Aaa
from ngts.nvos_tools.system.Health import Health
from ngts.nvos_tools.system.Gnmi_server import Gnmi_server
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.Certificate import Certificate

logger = logging.getLogger()


class System(BaseComponent):
    def __init__(self, parent_obj=None, devices_dut=None, force_api=None):
        assert force_api in ApiType.ALL_TYPES + [None], f'Argument "force_api" must be in {ApiType.ALL_TYPES + [None]}. Given: {force_api}'
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueSystemCli, ApiType.OPENAPI: OpenApiSystemCli}, path='/system', force_api=force_api)
        self.config = Config(self)
        self.documentation = Documentation(self)
        self.aaa = Aaa(self)
        self.log = Log(self)
        self.debug_log = DebugLog(self)
        self.snmp_server = SnmpServer(self)
        self.security = Security(self)
        self.ssh_server = BaseComponent(self, path='/ssh-server')
        self.serial_console = BaseComponent(self, path='/serial-console')
        self.syslog = Syslog(self)
        self.ntp = Ntp(self)
        self.ztp = Ztp(self)
        self.stats = Stats(self, devices_dut)
        self.techsupport = TechSupport(self)
        self.image = Image(self)
        self.message = BaseComponent(self, path='/message')
        self.version = BaseComponent(self, path='/version')
        self.events = BaseComponent(self, path='/events')
        self.reboot = Reboot(self)
        self.factory_default = FactoryDefault(self)
        self.profile = Profile(self)
        self.health = Health(self)
        self.datetime = DateTime(self)
        self.gnmi_server = Gnmi_server(self)
        self.web_server_api = WebServerAPI(self)
        self.api = Api(self)
        self.ptp = BaseComponent(self, path='/ptp')
        self.lldp = Lldp(self)

    def ssd_cleanup(self, expected_str="", dut_engine=None):
        """nv action run fae system ssd-cleanup """
        return self.action(ActionConsts.RUN, 'ssd-cleanup', expected_output=expected_str)

    @staticmethod
    def get_expected_fields(device, resource):
        return device.constants.system[resource]

    def validate_health_status(self, expected_status):
        with allure.step("Validate health status with \"nv show system\" cmd"):
            logger.info("Validate health status with \"nv show system\" cmd")
            system_output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            if expected_status != system_output[SystemConsts.HEALTH_STATUS]:
                health_output = OutputParsingTool.parse_json_str_to_dictionary(self.health.show()).get_returned_value()
                health_issues_str = '\n'.join(f'{k}: {v}' for k, v in health_output[HealthConsts.ISSUES].items())
                assert False, "Unexpected health status.\nExpected: {}, but got :{}," \
                    " with the following health issues:\n{}".\
                    format(expected_status, health_output[HealthConsts.STATUS], health_issues_str)

    @retry(Exception, tries=3, delay=2)
    def wait_until_health_status_change_to(self, expected_status):
        self.validate_health_status(expected_status)


class Documentation(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/documentation')

    def action_upload(self, upload_path, file_name):
        with allure.step("Upload {file} to '{path}".format(file=file_name, path=upload_path)):
            logging.info("Upload {file} to '{path}".format(file=file_name, path=upload_path))
            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_upload,
                                                   TestToolkit.engines.dut, self.get_resource_path(),
                                                   'files ' + file_name, upload_path)


class FactoryDefault(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/factory-default')

    def show(self, op_param="", output_format=OutputFormat.json):
        raise Exception("unset is not implemented for system/factory-default")

    def set(self, op_param_name="", op_param_value=None):
        raise Exception("unset is not implemented for system/factory-default")

    def unset(self, op_param=""):
        raise Exception("unset is not implemented for system/factory-default")

    def action_reset(self, engine=None, device=None, operation='reset factory', param=""):
        with allure.step("Execute factory reset {}".format(param)):
            logging.info("Execute factory reset {}".format(param))
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            marker = TestToolkit.get_loganalyzer_marker(engine)

            start_time = time.time()

            res_obj = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_reset,
                                                      engine, device, "factory-default", param)
            end_time = time.time()
            duration = end_time - start_time

            TestToolkit.add_loganalyzer_marker(engine, marker)

            with allure.step("Reset factory takes: {} seconds".format(duration)):
                logger.info("Reset factory takes: {} seconds".format(duration))

            DutUtilsTool.wait_for_nvos_to_become_functional(engine).verify_result()
            end_time = time.time()
            duration = end_time - start_time

            with allure.step("Reset factory till system is functional takes: {} seconds".format(duration)):
                logger.info("Reset factory till system is functional takes: {} seconds".format(duration))
                OperationTime.verify_operation_time(duration, operation).verify_result()

            return res_obj


class DateTime(BaseComponent):
    """
    @summary:
    Infra class for system.date-time field object
    """

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/date-time')

    def action_change(self, params=""):
        rsrc_path = self.get_resource_path()

        with allure.step('Execute action change for {rsrcp} \tparams: {prm}'.format(rsrcp=rsrc_path, prm=params)):
            logging.info('Execute action change for {rsrcp} \tparams: {prm}'.format(rsrcp=rsrc_path, prm=params))

            if TestToolkit.tested_api == ApiType.OPENAPI:
                params_list = params.split(' ')
                clock_date = params_list[0] if len(params_list) else ''
                clock_time = params_list[1] if len(params_list) > 1 else ''
                params = {'clock-date': clock_date, 'clock-time': clock_time}

            return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_change,
                                                   TestToolkit.engines.dut, rsrc_path, params)


class WebServerAPI(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/api')
        self.connections = BaseComponent(self, path='/connections')
        self.listen_address = BaseComponent(self, path='/listening-address')


class Api(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/api')
