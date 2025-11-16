from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo


class Dns(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/dns')

    def set(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
            dut_engine=None, client_certs_after_apply: CertInfo = None, check_engine_connectivity: bool = True) -> 'ResultObj':
        """
        Override set method to handle API-specific differences for DNS server configuration.
        For OpenAPI: converts string values to dictionary format {value: {}}
        For NVUE: keeps the value as-is
        """
        # If using OpenAPI and op_param_value is a string (e.g., DNS server IP), wrap it in dict format
        if TestToolkit.tested_api == ApiType.OPENAPI and isinstance(op_param_value, str):
            op_param_value = {op_param_value: {}}

        # Call parent's set method with the adjusted parameter
        return super().set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation,
                           dut_engine, client_certs_after_apply, check_engine_connectivity)
