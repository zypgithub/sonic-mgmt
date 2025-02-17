import logging

from retry import retry

from ngts.constants.constants import GnmiConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.MTLSableServerResource import MTLSableServerResource

logger = logging.getLogger()


class GnmiServer(MTLSableServerResource):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/gnmi-server')

    def enable_gnmi_server(self, apply=True):
        return self.set(GnmiConsts.GNMI_STATE_FIELD, GnmiConsts.GNMI_STATE_ENABLED, apply=apply)

    def disable_gnmi_server(self, apply=True):
        return self.set(GnmiConsts.GNMI_STATE_FIELD, GnmiConsts.GNMI_STATE_DISABLED, apply=apply)

    def unset_gnmi_server(self, apply=True):
        return self.unset(apply=apply)

    def parsed_show_gnmi(self):
        return OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()

    @retry(Exception, tries=4, delay=3)
    def compare_show_gnmi_output(self, expected={GnmiConsts.GNMI_STATE_FIELD: GnmiConsts.GNMI_STATE_ENABLED,
                                                 GnmiConsts.GNMI_IS_RUNNING_FIELD: GnmiConsts.GNMI_IS_RUNNING}):
        show_output = self.parsed_show_gnmi()
        msg = ''
        for key, value in expected.items():
            if show_output[key] != expected[key]:
                msg += f"{key} field is different than expected: \n" \
                    f"Expected: {expected[key]}, but got: {value}\n"
        assert not msg, f"The output of show gnmi-server is different than expected:\n{msg}"
