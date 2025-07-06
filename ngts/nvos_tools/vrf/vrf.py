import logging

from typing import Dict
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.DefaultDict import DefaultDict


logger = logging.getLogger()


class Vrf(BaseComponent):

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, api={ApiType.NVUE: NvueBaseCli, ApiType.OPENAPI: OpenApiBaseCli}, path='/vrf')
        self.vrf_id: Dict[str, VrfID] = DefaultDict(lambda vrf_id: VrfID(parent_obj=self, vrf_id=vrf_id))


class VrfID(BaseComponent):

    def __init__(self, vrf_id, parent_obj=None):
        super().__init__(parent=parent_obj, path=f'/{vrf_id}')
