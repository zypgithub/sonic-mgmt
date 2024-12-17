from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.Server import Server
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AuthConsts


class AbstractRemoteAaaResource(BaseComponent):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        super().__init__(parent=parent_obj, path=resource_name)

        self.server = Server(self)
        self.accounting = BaseComponent(self, path='/accounting')

        self._remote_aaa_type_name: str = self._resource_path.replace('/', '')

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        raise Exception("method 'enable' is not implemented for object of class 'AbstractRemoteAaaResource'")


class NVOSRemoteAaaResource(AbstractRemoteAaaResource):

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        authentication: BaseComponent = self.parent_obj.authentication
        authentication.set(AuthConsts.ORDER, f'{self._remote_aaa_type_name},{AuthConsts.LOCAL}',
                           dut_engine=engine).verify_result()
        failthrough_val = AaaConsts.ENABLED if failthrough else AaaConsts.DISABLED
        res = authentication.set(AuthConsts.FAILTHROUGH, failthrough_val, apply=apply, dut_engine=engine)
        if verify_res:
            res.verify_result()


class CLRemoteAaaResource(AbstractRemoteAaaResource):

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        authentication: BaseComponent = self.parent_obj.authentication

        if self._api_to_use == ApiType.NVUE:
            authentication.set("1", self._remote_aaa_type_name, dut_engine=engine).verify_result()
            res = authentication.set("2", AuthConsts.LOCAL, dut_engine=engine, apply=apply)
        else:
            authentication.set('1', {self._remote_aaa_type_name: {}}, dut_engine=engine).verify_result()  # TODO: check if 1 is sub-resource of /authentication-order
            res = authentication.set('2', {AuthConsts.LOCAL: {}}, dut_engine=engine, apply=apply)

        if verify_res:
            res.verify_result()


resource_class_by_is_eth = {
    True: CLRemoteAaaResource,
    False: NVOSRemoteAaaResource
}


class RemoteAaaResource(AbstractRemoteAaaResource):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        super().__init__(parent_obj=parent_obj, resource_name=resource_name)

        # decide actual structure dynamically according to switch type (composition & delegation)
        self.__actual_resource: AbstractRemoteAaaResource = resource_class_by_is_eth[TestToolkit.is_eth_dut()](parent_obj,
                                                                                                               resource_name)

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        return self.__actual_resource.enable(failthrough, apply, engine, verify_res)
