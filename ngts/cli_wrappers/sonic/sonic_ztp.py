import logging
from retry.api import retry_call

logger = logging.getLogger()


class SonicZtpCli:

    def __new__(cls, **kwargs):
        branch = kwargs.get('branch')
        engine = kwargs['engine']
        cli_obj = kwargs.get('cli_obj')
        dut_alias = kwargs.get('dut_alias', 'dut')

        supported_cli_classes = {'default': SonicZtpCliDefault(engine, cli_obj, dut_alias)}

        cli_class = supported_cli_classes.get(branch, supported_cli_classes['default'])
        cli_class_name = cli_class.__class__.__name__
        logger.info(f'Going to use ZTP CLI class: {cli_class_name}')

        return cli_class


class SonicZtpCliDefault:
    """
    This class is for ZTP cli commands for sonic only
    """

    def __init__(self, engine, cli_obj, dut_alias):
        self.engine = engine
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias

    def show_ztp_status(self):
        """
        This method show ztp status on the sonic switch
        :return: command output
        """
        return self.engine.run_cmd('show ztp status')

    def enable_ztp(self):
        """
        This method enable ZTP on the sonic switch
        :return: command output
        """
        return self.engine.run_cmd('sudo config ztp enable')

    def disable_ztp(self):
        """
        This method disable ZTP on the sonic switch
        :return: command output
        """
        res = self.engine.run_cmd('sudo config ztp disable -y')

        # await for ztp status to be changed
        retry_call(
            lambda: 'inactive' in self.engine.run_cmd('systemctl is-active ztp'),
            tries=5, delay=30, logger=logger
        )

        return res
