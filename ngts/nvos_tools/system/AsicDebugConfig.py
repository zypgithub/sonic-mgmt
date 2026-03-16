import logging

from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts, ActionParamConsts
from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Files import Files
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class AsicDebugConfig(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/asic-debug-config')
        self.files = Files(self)
