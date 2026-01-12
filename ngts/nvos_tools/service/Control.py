import allure
import logging
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType, ServiceConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
# from collections import DefaultDict
logger = logging.getLogger()


class Control(BaseComponent):
    def __init__(self, parent_obj=None, path=None):
        file_path = path if path else '/control'
        BaseComponent.__init__(self, parent=parent_obj, path=file_path)
        self.service_name = ServiceName(self)

    def get_control_field_values(self, field_names=[ServiceConsts.NTP]):
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        values = {}
        for field_name in field_names:
            if field_name in output.keys():
                values[field_name] = output[field_name]
            else:
                values[field_name] = ""
        return values

    def verify_show_control_output(self, expected_dictionary):
        with allure.step("Verify show control output"):
            logging.info("Verify show control output")
            output = self.get_control_field_values()
            logger.info("Expected show control output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()


class ServiceName(Control):
    def __init__(self, parent_obj=None, service_name_id=ServiceConsts.NTP):
        # Control.__init__(self, parent_obj=parent_obj, path='/' + service_name_id)
        BaseComponent.__init__(self, parent=parent_obj, path='/' + service_name_id)
        self.service_name_id = service_name_id
        self.resource_limit = ResourceLimit(self)


class ResourceLimit(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/resource-limit')

    def set_cpu(self, cpu, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=ServiceConsts.NTP_RESOURCE_LIMIT_CPU, op_param_value=cpu, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_cpu(self, apply=False, ask_for_confirmation=False):
        return self.unset(ServiceConsts.NTP_RESOURCE_LIMIT_CPU, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_memory(self, memory, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=ServiceConsts.NTP_RESOURCE_LIMIT_MEMORY, op_param_value=memory, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_memory(self, apply=False, ask_for_confirmation=False):
        return self.unset(ServiceConsts.NTP_RESOURCE_LIMIT_MEMORY, apply=apply, ask_for_confirmation=ask_for_confirmation)
