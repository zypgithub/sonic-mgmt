import logging
import os
import time
from typing import Tuple, Dict, Union, Iterable

from infra.tools.validations.traffic_validations.port_check.port_checker import validate_port_in_expected_state
from ngts.cli_wrappers.nvue.base_cli import BaseCli
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.nvos_constants.constants_nvos import ApiType, ConfState, ImageConsts, ActionConsts, OutputFormat, \
    ActionParamConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, RebootParams
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tools.test_utils import allure_utils as allure


logger = logging.getLogger()


class BaseComponent:
    parent_obj = None
    api_obj = {ApiType.NVUE: NvueSystemCli, ApiType.OPENAPI: OpenApiSystemCli}
    _resource_path = ''

    def __init__(self, parent=None, api=None, path='', force_api=None):
        self.parent_obj = parent
        if self.parent_obj and not api:
            self.api_obj = self.parent_obj.api_obj
        else:
            self.api_obj = api
        self._resource_path = path
        assert force_api in ApiType.ALL_TYPES + [
            None], f'Argument "force_api" must be in {ApiType.ALL_TYPES + [None]}. Given: {force_api}'

        if force_api or not self.parent_obj:
            self._force_api = force_api
        else:
            self._force_api = self.parent_obj._force_api

    @property
    def _api_to_use(self):
        return self._force_api if self._force_api else TestToolkit.tested_api

    @property
    def _cli_wrapper(self) -> BaseCli:
        return self.api_obj[self._api_to_use]

    @property
    def _general_cli_wrapper(self):
        return TestToolkit.GeneralApi[self._api_to_use]

    def get_resource_path(self):
        return "{parent_path}{self_path}".format(
            parent_path=self.parent_obj.get_resource_path() if self.parent_obj else "", self_path=self._resource_path)

    def get_resource_basename(self):
        resource_path = self.get_resource_path()
        return os.path.basename(resource_path)

    def update_param(self, param, rev):
        if self._api_to_use == ApiType.OPENAPI:
            param = param.replace('/', "%2F").replace(' ', "/").replace('--', '?')
        if rev and rev != ConfState.OPERATIONAL:
            param += ('?rev=' + rev) if self._api_to_use == ApiType.OPENAPI else f' --{rev}'
        return param

    def show(self, op_param="", output_format=OutputFormat.json, dut_engine=None, should_succeed=True,
             rev=ConfState.OPERATIONAL, exempted_err_msgs=None, if_returned_value=True, check_engine_connectivity: bool = True):
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut

        with allure.step('Execute show for {}'.format(self.get_resource_path())):
            op_param = self.update_param(op_param, rev)
            result_obj = SendCommandTool.execute_command(self._cli_wrapper.show, dut_engine, self.get_resource_path(),
                                                         op_param, output_format, check_engine_connectivity, exempted_err_msgs=exempted_err_msgs)
        if if_returned_value:
            return result_obj.get_returned_value(should_succeed)
        else:
            return result_obj

    def parse_show(self, op_param="", dut_engine=None, should_succeed=True):
        output = self.show(op_param, OutputFormat.json, dut_engine, should_succeed)
        return OutputParsingTool.parse_json_str_to_dictionary(output).verify_result()

    def _set(self, param_name, param_value, expected_str='', apply=False, ask_for_confirmation=False, dut_engine=None,
             client_certs_after_apply: CertInfo = None, check_engine_connectivity: bool = True):
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut

        result_obj = SendCommandTool.execute_command_expected_str(self._cli_wrapper.set,
                                                                  expected_str, dut_engine,
                                                                  self.get_resource_path(), param_name, param_value, check_engine_connectivity)
        if result_obj.result and apply:
            with allure.step("Applying set configuration"):
                option = ''
                if ask_for_confirmation == '-y':
                    option = '-y'
                    ask_for_confirmation = False
                result_obj = SendCommandTool.execute_command(self._general_cli_wrapper.apply_config, dut_engine,
                                                             ask_for_confirmation, option, client_certs_after_apply=client_certs_after_apply)
        return result_obj

    def set(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
            dut_engine=None, client_certs_after_apply: CertInfo = None, check_engine_connectivity: bool = True) -> 'ResultObj':
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut
        with allure.step('Execute set for {resource_path}'.format(resource_path=self.get_resource_path())):
            if op_param_name:
                if TestToolkit.tested_api == ApiType.OPENAPI and self._api_to_use != ApiType.NVUE:
                    if isinstance(op_param_value, str):
                        op_param_value = op_param_value.replace('"', '')
                    value = {op_param_name: op_param_value}
                    return self._set('', value, expected_str, apply, ask_for_confirmation, dut_engine,
                                     client_certs_after_apply, check_engine_connectivity)
                else:
                    if op_param_value == {}:
                        op_param_value = op_param_name
                        op_param_name = ''
                        return self._set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation,
                                         dut_engine, client_certs_after_apply, check_engine_connectivity)
                    elif isinstance(op_param_value, dict):
                        output = ''
                        for param_name, param_value in op_param_value.items():
                            res = self._set(param_name, param_value, expected_str, apply, ask_for_confirmation,
                                            dut_engine, client_certs_after_apply, check_engine_connectivity)
                            output = output + "\n" + res
                        return output
                    elif isinstance(op_param_value, str) or isinstance(op_param_value, int):
                        return self._set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation,
                                         dut_engine, client_certs_after_apply, check_engine_connectivity)
            else:
                logging.info('Run set with no params')
                op_param_value = '' if TestToolkit.tested_api == ApiType.NVUE else {}
                return self._set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation,
                                 dut_engine, client_certs_after_apply, check_engine_connectivity)

    def unset(self, op_param="", expected_str="", apply=False, ask_for_confirmation=False, dut_engine=None, check_engine_connectivity: bool = True):
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step('Execute unset {op_param} for {resource_path}'.format(op_param=op_param,
                                                                               resource_path=resource_path)):
            result_obj = SendCommandTool.execute_command_expected_str(self._cli_wrapper.unset,
                                                                      expected_str, dut_engine,
                                                                      resource_path, op_param, check_engine_connectivity)
        if result_obj.result and apply:
            with allure.step("Applying unset configuration"):
                result_obj = SendCommandTool.execute_command(self._general_cli_wrapper.apply_config, dut_engine,
                                                             ask_for_confirmation)
        return result_obj

    # todo: remove this function once it's no longer needed for backward-compatibility
    def action_deprecated(self, action: str, suffix="", param_name="", param_value="", output_format=OutputFormat.json,
                          dut_device=None, dut_engine=None, expected_output='', expect_reboot=False, deny_reboot=False,
                          topology_obj=None) -> ResultObj:
        """
        Runs nv action commands. The arguments `suffix`, `param_name` and `param_value` are all arguments passed to the
        the command, the difference is that in OpenAPI the `suffix` is appended to the URL while param_name and
        param_value are in the message contents. See examples below (also notice how NVUE handles param_name differently
        in these examples, based on whether or not we have param_value).
        :param deny_reboot:
        :param expect_reboot: Set to True if the system is expected to reboot when the action is run.

        Example: fae.platform.firmware.cpld.action_deprecated('install', "files /path/to/xyz.img", param_name="force")
        --> NVUE:       nv action install fae platform firmware cpld files /path/to/xyz.img force
        --> OPENAPI:    /fae/platform/firmware/cpld/files/%2Fpath%2Fto%2Fxyz.img
                        {"@install": {"state": "start", "parameters": {"force": True}}}

        Example: fae.platform.firmware.cpld.action_deprecated('fetch', param_name="remote-url", param_value="scp://...")
        --> NVUE:       nv action fetch fae platform firmware cpld scp://...
        --> OPENAPI:    /fae/platform/firmware/cpld
                        {"@fetch": {"state": "start", "parameters": {"remote-url": "scp://..."}}}
        """
        dut_engine = dut_engine or TestToolkit.engines.dut
        dut_device = dut_device or TestToolkit.devices.dut
        topology_obj = topology_obj or (TestToolkit.topology_obj if TestToolkit else None)
        resource_path = self.get_resource_path()
        with allure.step(f"Execute action {action} for {resource_path}"):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_deprecated, expected_output, dut_engine,
                                                                dut_device, action, resource_path, suffix, param_name,
                                                                param_value, output_format, expect_reboot, None,
                                                                deny_reboot=deny_reboot, topology_obj=topology_obj,
                                                                expected_output=expected_output)

    def action_fetch(self, path, base_url=None, engine=None) -> ResultObj:
        """
        nv action fetch <resource-path> <remote-url>
        :param path: Absolute file-path in the network drive, e.g. '/auto/path/to/file.img'.
        :param base_url: e.g. 'scp://user:password@host'. If None, the default credentials are used. If empty string
            then the `path` parameter needs to contain the full URL.
        """
        url = (ImageConsts.SCP_PATH if base_url is None else base_url) + path
        with allure.step(f"Fetching: {url}"):
            return self.action(ActionConsts.FETCH, (ActionParamConsts.REMOTE_URL, url), engine=engine,
                               expected_output='File fetched successfully')

    def action(self,
               action_str: str,  # e.g. 'install'
               main_param: Tuple[str, str] = None,  # e.g. ('remote-url', '/path/to/file')
               flags: Union[str, Iterable[str]] = '',  # e.g. 'force immediate' or ['force', 'immediate']
               additional_params: Dict = None,  # e.g. {'reboot': 'no'}
               engine=None,
               reboot_params: Union[bool, RebootParams, None] = None,  # set True if reboot is expected
               send_user_confirmation: str = None,  # e.g. 'y' or 'n' if NVUE asks for confirmation
               expected_output: Union[str, Iterable[str]] = '',  # string or list of possible strings
               # todo: timeout parameter
               device=None):
        """
        :param action_str: e.g. 'install', 'reboot', ...
        :param main_param: A 2-tuple containing the (name, value) of the action's main parameter, if any. For example,
            for action 'fetch' this argument would be ('remote-url', '/path/to/file')
        :param flags: String or list of strings. For NVUE the flags are included as-is in the command. For OpenAPI
            they become {flag1: True, flag2: True, ... }
        :param additional_params: A dict of all other parameters sent to the action, e.g. {'reboot': 'no'}
        :param engine: LinuxSshEngine. If None, the DUT engine is used.
        :param reboot_params: One of [True, False, None, RebootParams object].
            If the action should cause a reboot then reboot_params should be either `True` (for using default parameters
            for the reboot) or a RebootParams object specifying the parameters.
            If no reboot is expected as a result of this action, set to False or None.
        :param send_user_confirmation: If we expect the action to present a [y/n] confirmation message, set this
            argument to 'y' or 'n' (or any other string). If no confirmation-message is expected, set to None.
            Note: For OpenAPI actions this should always be set to None.
        :param expected_output: Sub-string we expect to see when the action is finished and before reboot (if expected).
        :param device: BaseDevice. If None, the DUT is used.
        """
        additional_params = additional_params or {}
        engine = engine or TestToolkit.engines.dut
        device = device or TestToolkit.devices.dut

        if not (reboot_params is None or type(reboot_params) in (bool, RebootParams)):
            raise TypeError(f'{reboot_params=} but it should be one of [True, False, None, RebootParams()]')

        resource_path = self.get_resource_path()
        with allure.step(f"Execute action {action_str} for {resource_path}"):
            result = self._cli_wrapper.action(action_str, resource_path, main_param, flags, additional_params,
                                              engine, reboot_params, send_user_confirmation, expected_output,
                                              device)

        if reboot_params and result:  # if reboot is expected and the action returned a success message: wait on reboot
            reboot_result = DutUtilsTool.wait_on_system_reboot(engine, reboot_params,
                                                               device=device, verify_final_result=False)
            result = reboot_result
        else:
            try:
                with allure.step('Assert that no reboot happened'):
                    time.sleep(3)
                    validate_port_in_expected_state(engine.ip, engine.ssh_port)
            except AssertionError:
                logger.error(f'Action {"succeeded" if result else "failed"} and caused an unexpected reboot. '
                             f'Failure information:\n{result.info}')
                with allure.step('Waiting for system to recover from unexpected reboot'):
                    DutUtilsTool.wait_on_system_reboot(engine, reboot_params or RebootParams(), device)
                    if result:
                        result.result = False
                        result.info += '\nThe operation caused an unexpected reboot.'

        return result
