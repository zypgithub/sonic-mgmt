import random

from ngts.nvos_constants.constants_nvos import SystemConsts, ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool


class Version(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/version')
        self.image = BaseComponent(self, path='/image')
        self.packages = Packages(self)

    def get_nvos_image_version(self):
        return OutputParsingTool.parse_json_str_to_dictionary(self.image.show()).get_returned_value()[
            SystemConsts.VERSION_BUILD_ID]


class Packages(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/packages')
        self.installed = BaseComponent(self, path='/installed')
