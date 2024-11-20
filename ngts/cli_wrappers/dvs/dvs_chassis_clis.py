from ngts.cli_wrappers.interfaces.interface_chassis_clis import ChassisCliInterface


class DvsChassisCli(ChassisCliInterface):
    """
    This class hosts methods which are implemented identically for Linux and SONiC
    """

    def __init__(self, engine):
        self.engine = engine

    def get_hostname(self):
        """
        This method return the hostname of host/switch
        :return: command output
        """
        return self.engine.run_cmd("hostname")