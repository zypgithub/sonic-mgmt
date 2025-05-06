import allure
import logging
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType


class Ntp(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/ntp')
        self.servers = NtpBaseResources(self, resource='/server')
        self.keys = NtpBaseResources(self, resource='/key')
        self.listen = BaseComponent(self, path='/listen')


class NtpBaseResources(BaseComponent):
    def __init__(self, parent_obj=None, resource=''):
        BaseComponent.__init__(self, parent=parent_obj, path=resource)
        self.resources_dict = {}
        self.resource = resource

    def set_resource(self, resource_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set {} with id : {}".format(self.resource, resource_id)):
            logging.info("Set {} with id : {}".format(self.resource, resource_id))
            resource_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            result_obj = self.set(op_param_name=resource_id, op_param_value=resource_value, expected_str=expected_str,
                                  apply=apply, ask_for_confirmation=ask_for_confirmation)
            resource = NtpBaseResource(self, resource_id)
            self.resources_dict.update({resource_id: resource})
            return result_obj

    def unset_resource(self, resource_id, apply=False, ask_for_confirmation=False):
        result_obj = self.resources_dict[resource_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.resources_dict.pop(resource_id)
        return result_obj


class NtpBaseResource(NtpBaseResources):
    def __init__(self, parent_obj=None, resource_id=''):
        NtpBaseResources.__init__(self, parent_obj=parent_obj, resource='/' + resource_id)
        self.resource_id = resource_id
