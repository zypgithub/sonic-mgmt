import logging

from ngts.cli_wrappers.nvue.nvue_platform_clis import NvuePlatformCli
from ngts.cli_wrappers.openapi.openapi_platform_clis import OpenApiPlatformCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ActionConsts

logger = logging.getLogger()


class Bmc_password(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         path='/bmc-password')

    def action_reset(self):
        """ nv action reset platform bmc-password """
        return self.action_deprecated(ActionConsts.RESET)
