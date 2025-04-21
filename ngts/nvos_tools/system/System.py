import logging
import os
import time

import pytest
from retry import retry

from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.constants.constants import InfraConst
from ngts.helpers.sanitizer_helper import check_sanitizer_and_store_dump
from ngts.nvos_constants.constants_nvos import ApiType, SystemConsts, HealthConsts
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Aaa import Aaa
from ngts.nvos_tools.system.Config import Config
from ngts.nvos_tools.system.Debug_log import DebugLog
from ngts.nvos_tools.system.Disk import Disk
from ngts.nvos_tools.system.GnmiServer import GnmiServer
from ngts.nvos_tools.system.Health import Health
from ngts.nvos_tools.system.Image import Image
from ngts.nvos_tools.system.Lldp import Lldp
from ngts.nvos_tools.system.Log import Log
from ngts.nvos_tools.system.MTLSableServerResource import MTLSableServerResource
from ngts.nvos_tools.system.Ntp import Ntp
from ngts.nvos_tools.system.Profile import Profile
from ngts.nvos_tools.system.Reboot import Reboot
from ngts.nvos_tools.system.Security import Security
from ngts.nvos_tools.system.SnmpServer import SnmpServer
from ngts.nvos_tools.system.Stats import Stats
from ngts.nvos_tools.system.Syslog import Syslog
from ngts.nvos_tools.system.Techsupport import TechSupport
from ngts.nvos_tools.system.Ztp import Ztp
from ngts.tools.test_utils import allure_utils as allure

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
        self.system_cli = BaseComponent(self, path='/cli')
        self.serial_console = BaseComponent(self, path='/serial-console')
        self.syslog = Syslog(self)
        self.ntp = Ntp(self)
        self.ztp = Ztp(self)
        self.stats = Stats(self, devices_dut)
        self.techsupport = TechSupport(self)
        self.image = Image(self)
        self.message = BaseComponent(self, path='/message')
        self.version = BaseComponent(self, path='/version')
        self.events = Events(self)
        self.dns = BaseComponent(self, path='/dns')
        self.reboot = Reboot(self)
        self.factory_default = FactoryDefault(self)
        self.profile = Profile(self)
        self.health = Health(self)
        self.datetime = DateTime(self)
        self.gnmi_server = GnmiServer(self)
        self.web_server_api = WebServerAPI(self)
        self.api = Api(self)
        self.ptp = BaseComponent(self, path='/ptp')
        self.lldp = Lldp(self)
        self.disk = Disk(self)

    @staticmethod
    def get_expected_fields(device, resource):
        return device.constants.system[resource]

    def validate_health_status(self, expected_status, throw_exception=True):
        with allure.step("Validate health status with \"nv show system\" cmd"):
            logger.info("Validate health status with \"nv show system\" cmd")
            system_output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            if expected_status != system_output[SystemConsts.HEALTH_STATUS]:
                health_output = OutputParsingTool.parse_json_str_to_dictionary(self.health.show()).get_returned_value()
                health_issues_str = '\n'.join(f'{k}: {v}' for k, v in health_output[HealthConsts.ISSUES].items())
                exception_str = "Unexpected health status.\nExpected: {}, but got :{}," \
                    " with the following health issues:\n{}".\
                    format(expected_status, health_output[HealthConsts.STATUS], health_issues_str)
                logger.warning(exception_str)
                if throw_exception:
                    assert False, exception_str

    @retry(Exception, tries=3, delay=2)
    def wait_until_health_status_change_to(self, expected_status):
        self.validate_health_status(expected_status)

    def action_reboot(self, flags=(), reboot_params=None, engine=None, device=None):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            engine = engine or TestToolkit.engines.dut
            device = device or TestToolkit.devices.dut
            start_time = time.time()
            result = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_reboot,
                                                     engine, device, self.get_resource_path(), flags, reboot_params)
            end_time = time.time()
            duration = end_time - start_time

            with allure.step(f"Reboot and system is ready takes {duration} seconds"):
                pass

            if pytest.is_sanitizer:
                dumps_folder = os.environ.get(InfraConst.ENV_LOG_FOLDER)
                with allure.step(f'check_sanitizer_and_store_dump in {dumps_folder}'):
                    check_sanitizer_and_store_dump(engine, dumps_folder, pytest.test_name)

            return result


class Events(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/events')

    def show_last(self, last_events_count=1):
        system = System()
        with allure.step("Show last system event"):
            logging.info("Show last system event")
            if TestToolkit.tested_api == ApiType.OPENAPI:
                return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].show,
                                                       TestToolkit.engines.dut, self.get_resource_path(),
                                                       SystemConsts.SYSTEM_LAST_EVENT + str(last_events_count))
            else:
                return system.events.show(SystemConsts.SYSTEM_LAST_EVENT + str(last_events_count))

    def show_recent(self, recent_events_count=1):
        system = System()
        with allure.step("Show recent system event"):
            logging.info("Show recent system event")
            if TestToolkit.tested_api == ApiType.OPENAPI:
                return SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].show,
                                                       TestToolkit.engines.dut, self.get_resource_path(),
                                                       SystemConsts.SYSTEM_RECENT_EVENT + str(recent_events_count))
            else:
                return system.events.show(SystemConsts.SYSTEM_RECENT_EVENT + str(recent_events_count))


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

    def action_reset(self, engine=None, device=None, operation='reset factory', param="", topology_obj=None, system_is_ready_timeout=None, verify_duration=False, test_name=''):
        with allure.step("Execute factory reset {}".format(param)):
            logging.info("Execute factory reset {}".format(param))
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            res_obj, duration = OperationTime.save_duration(f'reset factory {param}', "", test_name, SendCommandTool.execute_command,
                                                            self.api_obj[TestToolkit.tested_api].action_reset, engine=engine, device=device, comp="factory-default", param=param, topology_obj=topology_obj,
                                                            system_is_ready_timeout=system_is_ready_timeout, check_system_is_functional=False)

            engine.disconnect()

            with allure.step('wait for os to be functional'):
                if device:
                    result_obj = device.wait_for_os_to_become_functional(engine)
                else:
                    result_obj = DutUtilsTool.wait_for_nvos_to_become_functional(engine)

            logger.info("Reset factory till system is ready takes: {} seconds".format(duration))
            res_obj.duration = duration

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


class Api(MTLSableServerResource):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/api')
