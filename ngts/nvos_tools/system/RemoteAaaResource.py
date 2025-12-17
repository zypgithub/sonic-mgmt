from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.Server import Server
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AuthConsts
import logging
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class AbstractRemoteAaaResource(BaseComponent):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        super().__init__(parent=parent_obj, path=resource_name)

        self.server = Server(self)
        self.accounting = BaseComponent(self, path='/accounting')

        self._remote_aaa_type_name: str = self._resource_path.replace('/', '')

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        raise Exception("method 'enable' is not implemented for object of class 'AbstractRemoteAaaResource'")


class NVOSRemoteAaaResource(AbstractRemoteAaaResource):

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        with allure.step('Enable NVOS remote AAA resource'):
            authentication: BaseComponent = self.parent_obj.authentication
            authentication.set(AuthConsts.ORDER, [self._remote_aaa_type_name, AuthConsts.LOCAL],
                               dut_engine=engine).verify_result()
            failthrough_val = AaaConsts.ENABLED if failthrough else AaaConsts.DISABLED
            res = authentication.set(AuthConsts.FAILTHROUGH, failthrough_val, apply=apply, dut_engine=engine)
            if verify_res:
                res.verify_result()
            else:
                res.ignore_result()


class CLRemoteAaaResource(AbstractRemoteAaaResource):

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        with allure.step('Enable CL remote AAA resource'):
            authentication: BaseComponent = self.parent_obj.authentication

            # Check version to determine which CLI format to use
            if self._should_use_new_format():
                # Version >= 5.15.0: Use new format API
                methods = [self._remote_aaa_type_name, AuthConsts.LOCAL]
                res = authentication.set_authentication_order(methods, dut_engine=engine, apply=apply, ask_for_confirmation='-y')
            else:
                # Version < 5.15.0: Use legacy format with priority-based configuration
                if self._api_to_use == ApiType.NVUE:
                    authentication.set("1", self._remote_aaa_type_name, dut_engine=engine).verify_result()
                    res = authentication.set("2", AuthConsts.LOCAL, dut_engine=engine, apply=apply, ask_for_confirmation='-y')
                else:
                    authentication.set('1', {self._remote_aaa_type_name: {}}, dut_engine=engine).verify_result()
                    res = authentication.set('2', {AuthConsts.LOCAL: {}}, dut_engine=engine, apply=apply, ask_for_confirmation='-y')

            if verify_res:
                res.verify_result()
            else:
                res.ignore_result()

    def _should_use_new_format(self):
        """
        Determine if we should use the new authentication order format
        by delegating to the device's method.

        Returns:
            bool: True if new format should be used, False for legacy format
        """
        with allure.step('Check if should use new format'):
            logger.info('CLRemoteAaaResource: Checking if should use new format...')

            if not TestToolkit.is_eth_dut():
                logger.info('CLRemoteAaaResource: Not an ETH device, using NVOS format')
                return False  # Only ETH devices have version-dependent format changes

            try:
                # Delegate to the device's _should_use_new_format method
                if hasattr(TestToolkit, 'devices') and TestToolkit.devices and hasattr(TestToolkit.devices, 'dut'):
                    return TestToolkit.devices.dut._should_use_new_format()
                else:
                    logger.warning('CLRemoteAaaResource: TestToolkit.devices.dut not available, using LEGACY format')
                    return False
            except Exception as e:
                logger.exception(f'CLRemoteAaaResource: Exception during format check - using LEGACY format: {e}')
                return False


resource_class_by_is_eth = {
    True: CLRemoteAaaResource,
    False: NVOSRemoteAaaResource
}


class RemoteAaaResource(AbstractRemoteAaaResource):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        super().__init__(parent_obj=parent_obj, resource_name=resource_name)

        # decide actual structure dynamically according to switch type (composition & delegation)
        self.__actual_resource: AbstractRemoteAaaResource = resource_class_by_is_eth[TestToolkit.is_eth_dut()](parent_obj,
                                                                                                               resource_name)

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        return self.__actual_resource.enable(failthrough, apply, engine, verify_res)
