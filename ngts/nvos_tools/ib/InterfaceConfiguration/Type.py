from .ConfigurationBase import ConfigurationBase
from .nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
import logging

logger = logging.getLogger()


class Type(ConfigurationBase):
    def __init__(self, port_obj):
        ConfigurationBase.__init__(self,
                                   port_obj=port_obj,
                                   label=IbInterfaceConsts.TYPE,
                                   description="The type of interface",
                                   field_name_in_db={},
                                   output_hierarchy=IbInterfaceConsts.TYPE)

    def _get_value(self, engine=None, renew_show_cmd_output=True):
        """
        Returns operational/applied value
        :param renew_show_cmd_output: If true - 'show' command will be executed before checking the value
                                      Else - results from the previous 'show' command will be used
        :return:
        """
        if not engine:
            engine = TestToolkit.get_engine()

        if renew_show_cmd_output:
            TestToolkit.update_port_output_dictionary(self.port_obj, engine)
        output_str = self.port_obj.show_output_dictionary[IbInterfaceConsts.TYPE]
        return output_str
