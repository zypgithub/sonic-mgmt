from typing import Dict

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo


class ControlPlaneAclDirection(BaseComponent):
    # OpenAPI: leaf PATCH {} -> 405; set via parent {inbound|outbound:{}}. Outbound unset -> parent {outbound:null}.
    def _openapi_parent(self) -> bool:
        return TestToolkit.tested_api == ApiType.OPENAPI and self._api_to_use != ApiType.NVUE and self.parent_obj

    def set(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
            dut_engine=None, client_certs_after_apply: CertInfo = None, check_engine_connectivity: bool = True,
            is_fips_mode=False, fips_timeout=10) -> 'ResultObj':
        d = self._resource_path.strip('/')
        if not op_param_name and op_param_value == {} and self._openapi_parent() and d in ('inbound', 'outbound'):
            return self.parent_obj.set(
                d, {}, expected_str=expected_str, apply=apply, ask_for_confirmation=ask_for_confirmation,
                dut_engine=dut_engine, client_certs_after_apply=client_certs_after_apply,
                check_engine_connectivity=check_engine_connectivity, is_fips_mode=is_fips_mode, fips_timeout=fips_timeout)
        return super().set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation, dut_engine,
                           client_certs_after_apply, check_engine_connectivity, is_fips_mode, fips_timeout)

    def unset(self, op_param="", expected_str="", apply=False, ask_for_confirmation=False, dut_engine=None,
              check_engine_connectivity: bool = True, is_fips_mode=False, fips_timeout=10):
        d = self._resource_path.strip('/')
        if not op_param and self._openapi_parent() and d == 'outbound':
            return self.parent_obj._set(
                '', {'outbound': 'null'}, expected_str, apply, ask_for_confirmation, dut_engine, None,
                check_engine_connectivity, is_fips_mode, fips_timeout)
        return super().unset(op_param, expected_str, apply, ask_for_confirmation, dut_engine,
                             check_engine_connectivity, is_fips_mode, fips_timeout)


class ControlPlane(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/control-plane')
        self.acl = ControlPlaneAcl(self)


class ControlPlaneAcl(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/acl')
        from ngts.nvos_tools.infra.DefaultDict import DefaultDict
        self.acl_id: Dict[str, ControlPlaneAclID] = DefaultDict(lambda acl_id: ControlPlaneAclID(parent_obj=self, acl_id=acl_id))


class ControlPlaneAclID(BaseComponent):
    def __init__(self, acl_id, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path=f'/{acl_id}')
        self.inbound = ControlPlaneAclDirection(self, path='/inbound')
        self.outbound = ControlPlaneAclDirection(self, path='/outbound')
        self.statistics = ControlPlaneAclStatistics(self)


class ControlPlaneAclStatistics(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/statistics')
        from ngts.nvos_tools.infra.DefaultDict import DefaultDict
        self.rule_id: Dict[str, BaseComponent] = DefaultDict(lambda rule_id: BaseComponent(parent=self, path=f'/{rule_id}'))
