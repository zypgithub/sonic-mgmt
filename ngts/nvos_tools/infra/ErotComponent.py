from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Files import Files


class ErotComponent(BaseComponent):
    def __init__(self, parent_obj=None, erot_name=None):
        super().__init__(parent=parent_obj, path=f"/{erot_name}")
        self.files = Files(self)
