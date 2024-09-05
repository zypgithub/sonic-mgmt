import logging

from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output
from ngts.nvos_constants.constants_nvos import ActionType

logger = logging.getLogger()


class NvuePlatformCli(NvueBaseCli):

    def __init__(self):
        self.cli_name = "Platform"

    @staticmethod
    @check_output
    def action_install_fae_bios_firmware(engine, bios_image_path, resource_path='', device=None):
        """
        Method to install BIOS firmware using NVUE
        :param engine: the engine to use
        :param device: Noga device info
        :param bios_image_path: the path to the BIOS firmware image
        :param resource_path: unused
        """
        return NvuePlatformCli.action_install(engine=engine, device=device, fae_command=True, args='firmware bios files {}'.format(bios_image_path), expect_reboot=True, force=True)

    @staticmethod
    @check_output
    def action_generate(engine, resource_path, name=""):
        return NvuePlatformCli.action(engine, action_type=ActionType.GENERATE.replace('@', ''), resource_path=resource_path, param_value=name)
