import os
import netmiko
from infra.constants.constants import LinuxConsts
from infra.logger.logger import logger


class SSH:
    def __init__(self, ip, username, password, port=22, global_delay_factor=1, device_type='linux', verbose=False):
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.global_delay_factor = global_delay_factor
        self.device_type = device_type
        self.verbose = verbose
        self._engine = None

    @property
    def engine(self):
        """
        Creates the engine only when the client accesses the object.
        :return: ssh engine
        """
        if self._engine is None:
            self._engine = self.create_engine()
            logger.debug('New SSH connection established to host: {}'.format(self.ip))
        return self._engine

    def create_engine(self):
        connection_details = {
            'device_type': self.device_type,
            'ip': self.ip,
            'username': self.username,
            'password': self.password,
            'port': self.port,
            'global_delay_factor': self.global_delay_factor,
            'verbose': self.verbose
        }
        return netmiko.ConnectHandler(**connection_details)

    def run_cmd(self, cmd, validate=False, print_output=True, max_loops=500, sanitized_cmd=None):
        """
        Run command using SSH engine(run it on hosts)
        :param cmd: command which should be executed
        :param validate: if need validate that command executed successfully - True, else False
        :param print_output: True if user want to print the cmd output, else False
        :param sanitized_cmd: optional redacted command string for logging (e.g. to hide credentials)
        :return: command execution output
        """
        log_cmd = sanitized_cmd if sanitized_cmd is not None else cmd
        logger.info('Running CMD: {}'.format(log_cmd))
        cmd_output = self.engine.send_command(cmd, max_loops=max_loops)
        return self.handle_cmd_output(cmd_output, validate, print_output, log_cmd=log_cmd)

    def handle_cmd_output(self, output, validate=True, print_output=True, log_cmd=None):
        """
        :param output: the command output
        :param validate: if need validate that command executed successfully - True, else False
        :param print_output: True if user want to print the cmd output, else False
        :param log_cmd: optional command identifier for error messages (sanitized if credentials present)
        :return: the output
        """
        if print_output:
            logger.info('Player: {}, cmd output: {}'.format(self.ip, output))
        if validate:
            self.validate_command(log_cmd=log_cmd)
        return output

    def validate_command(self, log_cmd=None):
        cmd_output = self.engine.send_command(LinuxConsts.get_exit_code)
        if cmd_output.strip() != LinuxConsts.exit_code_zero:
            error_msg = 'Failed to execute command'
            if log_cmd:
                error_msg += f': {log_cmd}'
            error_msg += f', exit code: {cmd_output}'
            raise Exception(error_msg)

    def copy_file_to_host(self, src_path, dst_path, copy_to_tmp=False):
        """
        Copy file to remote host from local folder
        :param src_path: path in local filesystem to file which should be copied
        :param dst_path: path in remote filesystem
        :param copy_to_tmp: if True, move src file to a tmp dir in the switch 
        and then move the file from the tmp dir to the dst_path
        """
        if copy_to_tmp:
            file_name = os.path.basename(src_path)
            tmp_dst_path = os.path.join('/tmp', file_name)
            self.copy_file_to_host(src_path=src_path, dst_path=tmp_dst_path, copy_to_tmp=False)
            self.run_cmd("sudo cp {} {}".format(tmp_dst_path, dst_path))
        else:
            logger.info("Copy file from source path: {}\n to destination path: {}\n".format(src_path, dst_path))
            netmiko.file_transfer(self.engine, source_file=src_path, dest_file=dst_path, file_system='/',
                                  overwrite_file=True)

    def copy_file_from_host(self, src_path, dst_path):
        """
        Copy file from remote host to local folder
        :param src_path: path in remote filesystem to file which should be copied
        :param dst_path: path in local filesystem
        """
        netmiko.file_transfer(self.engine, source_file=src_path, dest_file=dst_path, file_system='/',
                              direction='get', overwrite_file=True)

    def disconnect(self):
        if self._engine:
            logger.debug('Disconnecting SSH Engine: {}'.format(self.ip))
            self._engine.disconnect()
