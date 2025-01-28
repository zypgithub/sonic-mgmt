from typing import Dict

import allure
import logging
import random
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.DefaultDict import DefaultDict


from ngts.nvos_tools.infra.BaseComponent import BaseComponent


class CableCartridge(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/cable-cartridge')
        self.cartridge_id: Dict[str, CartridgeId] = DefaultDict(
            lambda cartridge_id: CartridgeId(parent=self, cartridge_id=cartridge_id))


class CartridgeId(BaseComponent):
    def __init__(self, parent, cartridge_id):
        super().__init__(parent=parent, path=f'/{cartridge_id}')
