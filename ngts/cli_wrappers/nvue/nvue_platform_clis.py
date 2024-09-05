import logging

from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output

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
