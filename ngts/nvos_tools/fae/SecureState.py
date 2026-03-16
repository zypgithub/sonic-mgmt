from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool


class SecureState(BaseComponent):
    """Represents fae/platform/secure-state subtree."""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/secure-state')

    def is_asic_dev_signed(self) -> bool:
        """Check if ASIC is in dev state. Returns True for 'dev', False otherwise."""
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        return output.get('asic', '') == 'dev'
