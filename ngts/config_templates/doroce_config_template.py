import time
import allure
import logging

from functools import partial
from ngts.constants.constants import AppExtensionInstallationConstants, SonicConst

logger = logging.getLogger()


class DoroceConfigTemplate:
    """
    This class contains 2 methods for configuring and cleaning-up DoRoCE related settings.
    """
    @staticmethod
    def configuration(topology_obj, platform, request=None):
        """
        Method which are performing DoRoCE configuration
        :param topology_obj: topology object fixture
        :param platform: device platform info
        :param request: request object fixture
        """
        if request:
            with allure.step('Add DoRoCE configuration cleanup into finalizer'):
                cleanup = partial(DoroceConfigTemplate.cleanup, topology_obj)
                request.addfinalizer(cleanup)

        cli_object = topology_obj.players['dut']['cli']
        if ('sn2' not in platform and 'simx' not in platform and
                AppExtensionInstallationConstants.DOAI in cli_object.general.show_and_parse_feature_status()):
            logger.info('Applying DoRoCE configuration')
            with allure.step('Applying DoRoCE configuration'):
                cli_object.app_ext.disable_app(AppExtensionInstallationConstants.DOAI, validate=False)
                cli_object.app_ext.enable_app(AppExtensionInstallationConstants.DOAI)
                # TODO: workaround for the issue https://redmine.mellanox.com/issues/2834968
                # happens in push_gate with reload
                # when will be fixed, must be left only reload_qos
                cli_object.qos.clear_qos()
                time.sleep(10)
                cli_object.qos.reload_qos()
                cli_object.doroce.config_doroce_lossless_double_ipool(ports_list=topology_obj.players_all_ports['dut'])
        else:
            logger.info('Skip DoAI configurations')

    @staticmethod
    def cleanup(topology_obj, platform):
        """
        Method which are doing DoRoCE configuration cleanup
        :param topology_obj: topology object fixture
        :param platform: device platform info
        """
        cli_object = topology_obj.players['dut']['cli']
        if ('sn2' not in platform and 'simx' not in platform and
                AppExtensionInstallationConstants.DOAI in cli_object.general.show_and_parse_feature_status()):
            logger.info('Performing DoRoCE configuration cleanup')
            with allure.step('Performing DoRoCE configuration cleanup'):
                cli_object.doroce.disable_doroce()
                cli_object.app_ext.disable_app(AppExtensionInstallationConstants.DOAI)
        else:
            logger.info('Skip DoAI configurations')
