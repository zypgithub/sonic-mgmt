from ngts.nvos_constants.constants_nvos import BiosConsts
from ngts.nvos_tools.infra.BiosTools.BiosTool import BiosTool


class CoffeeLakeBios(BiosTool):

    @property
    def BIOS_MENU_PAGES(self):
        return BiosConsts.BIOS_MENU_PAGES

    @property
    def CREATE_NEW_PASSWORD(self):
        return BiosConsts.CREATE_NEW_PASSWORD

    @property
    def ENTER_CURRENT_PASSWORD(self):
        return BiosConsts.ENTER_CURRENT_PASSWORD

    @property
    def CLEAR_OLD_PASSWORD(self):
        return BiosConsts.CLEAR_OLD_PASSWORD
