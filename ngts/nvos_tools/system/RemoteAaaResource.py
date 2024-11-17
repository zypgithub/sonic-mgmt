from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Server import Server
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AuthConsts


class RemoteAaaResource(BaseComponent):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueSystemCli, ApiType.OPENAPI: OpenApiSystemCli}, path=resource_name)
        self.server = Server(self)

    def enable(self, failthrough=False, apply=False, engine=None, verify_res=True):
        remote_aaa_type = self._resource_path.replace('/', '')
        authentication: BaseComponent = self.parent_obj.authentication
        authentication.set(AuthConsts.ORDER, f'{remote_aaa_type},{AuthConsts.LOCAL}', dut_engine=engine).verify_result()
        failthrough_val = AaaConsts.ENABLED if failthrough else AaaConsts.DISABLED
        res = authentication.set(AuthConsts.FAILTHROUGH, failthrough_val, apply=apply, dut_engine=engine)
        if verify_res:
            res.verify_result()
