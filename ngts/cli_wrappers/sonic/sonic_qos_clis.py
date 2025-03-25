class SonicQosCli:
    """
    This class hosts SONiC Qos cli methods
    """

    def __init__(self, engine):
        self.engine = engine

    def reload_qos(self, ports_list=[], no_dynamic=False):
        """
        This method is to reload qos
        :param ports_list: if provided a port lists, reload qos configuration only on ports in list
        :param no_dynamic: True if buffer module is traditional
        :return: command output
        """
        cmd_suffix = ""
        if ports_list:
            cmd_suffix += f"--ports {','.join(ports_list)}"
        if no_dynamic:
            cmd_suffix += "--no-dynamic-buffer"
        return self.engine.run_cmd(f'sudo config qos reload {cmd_suffix}', validate=True)

    def clear_qos(self):
        """
        This method is to clear qos
        :param engine: ssh engine object
        :return: command output
        """
        return self.engine.run_cmd('sudo config qos clear ', validate=True)

    def stop_buffermgrd(self):
        """
        This method is to stop buffermgrd
        :param engine: ssh engine object
        :return: command output
        """
        return self.engine.run_cmd('docker exec swss supervisorctl stop buffermgrd', validate=True)

    def start_buffermgrd(self):
        """
        This method is to start buffermgrd
        :param engine: ssh engine object
        :return: command output
        """
        return self.engine.run_cmd('docker exec swss supervisorctl start buffermgrd', validate=True)
