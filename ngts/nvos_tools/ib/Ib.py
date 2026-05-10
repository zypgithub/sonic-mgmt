import logging
from typing import Dict

from ngts.cli_wrappers.nvue.nvue_opensm_clis import NvueOpenSmCli
from ngts.cli_wrappers.openapi.openapi_opensm_cli import OpenApiOpenSmCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.ib.ibdiagnet import Ibdiagnet
from ngts.nvos_tools.ib.Sm import Sm
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.tools.test_utils import allure_utils as allure


logger = logging.getLogger()


class Ib(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/ib')
        self.ibdiagnet = Ibdiagnet(self)
        self.sm = Sm(self)
        self.device = BaseComponent(self, path='/device')
        self.router = IbRouter(self)


class IbRouter(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/router')
        self.routing_table = BaseComponent(self, path='/routing-table')
        self.ib_subnet = IbSubnet(self)
        self.counters = Counters(self)


class IbSubnet(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/ib-subnet')
        self.swid_id: Dict[str, SwidId] = DefaultDict(lambda swid_id: SwidId(self, swid_id))


class SwidId(BaseComponent):
    def __init__(self, parent, swid_id):
        BaseComponent.__init__(self, parent, path=f'/{swid_id}')
        self.counters = Counters(self)


class Counters(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/counters')

    def clear_counters(self, engine=None, device=None):
        with allure.step(f"Clearing IB router counters"):
            return self.action(ActionConsts.CLEAR, engine=engine, device=device,
                               expected_output=['Cleared IB router counters successfully'])
