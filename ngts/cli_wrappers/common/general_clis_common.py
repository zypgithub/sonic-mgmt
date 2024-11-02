import logging
import json
import re
from ngts.cli_wrappers.interfaces.interface_general_clis import GeneralCliInterface

logger = logging.getLogger()


class GeneralCliCommon(GeneralCliInterface):
    """
    This class hosts methods which are implemented identically for Linux and SONiC
    """

    def __init__(self, engine, cli_obj=None, dut_alias=None):
        self.engine = engine
        self.cli_obj = cli_obj
        self.dut_alias = dut_alias

    def start_service(self, service):
        output = self.engine.run_cmd('sudo service {} start'.format(service), validate=True)
        return output

    def stop_service(self, service):
        output = self.engine.run_cmd('sudo service {} stop'.format(service), validate=True)
        return output

    def systemctl_start(self, service):
        output = self.engine.run_cmd(f'sudo systemctl start {service}', validate=True)
        return output

    def systemctl_stop(self, service):
        output = self.engine.run_cmd(f'sudo systemctl stop {service}', validate=True)
        return output

    def systemctl_restart(self, service):
        output = self.engine.run_cmd(f'sudo systemctl restart {service}', validate=True)
        return output

    def systemctl_is_service_active(self, service):
        service_status = False
        output = self.engine.run_cmd(f'sudo systemctl is-active {service}', validate=True)
        if output == 'active':
            service_status = True
        return service_status

    def get_container_status(self, app_name):
        """
        Get specified container's status:
        Example:
            docker ps -a -f name=snmp$ --format "{'ID':'{{ .ID }}', 'Names':'{{ .Names }}', 'Status':'{{ .Status }}'}"
            {'ID':'bb2ef5fcd2b1', 'Names':'snmp', 'Status':'Up 3 hours'}
        :param app_name: ssh engine object
        :Return app container status, None if no container data
        """
        container_data_format = "{'ID':'{{ .ID }}', 'Names':'{{ .Names }}', 'Status':'{{ .Status }}'}"
        app_container_info = self.engine.run_cmd('docker ps -a -f name={}$ --format "{}" '.
                                                 format(app_name, container_data_format), validate=True)
        logger.info("get {} container status:{}".format(app_name, app_container_info))
        app_container_status = None
        if app_container_info:
            app_container_status = eval(app_container_info)["Status"]
        return app_container_status

    def get_running_containers_names(self):
        """
        Returns the names of running Docker containers in the system.
        """
        return self.engine.run_cmd("docker ps --format '{{.Names}}'").splitlines()

    def hostname(self, flags=''):
        return self.engine.run_cmd(f'hostname {flags}')

    def echo(self, string, flags=''):
        return self.engine.run_cmd(f'echo {flags} {string}')

    def ls(self, path, flags='', validate=False):
        return self.engine.run_cmd(f'ls {flags} {path}', validate=validate)

    def mv(self, src_path, dst_path, flags=''):
        return self.engine.run_cmd(f'mv {flags} {src_path} {dst_path}')

    def cp(self, src_path, dst_path, flags=''):
        return self.engine.run_cmd(f'cp {flags} {src_path} {dst_path}')

    def rm(self, path, flags=''):
        return self.engine.run_cmd(f'rm {flags} {path}')

    def mkdir(self, path, flags=''):
        return self.engine.run_cmd(f'mkdir {flags} {path}')

    def which(self, path):
        return self.engine.run_cmd(f'which {path}')

    def sed(self, path, script, flags=''):
        return self.engine.run_cmd(f"sed {flags} '{script}' {path}")

    def chmod_by_mode(self, path, mode, flags=''):
        return self.engine.run_cmd(f'chmod {flags} {mode} {path}')

    def chmod_by_ref_file(self, path, ref_path, flags=''):
        return self.engine.run_cmd(f'chmod {flags} --reference={ref_path} {path}')

    def chown_by_user(self, path, user, group='', flags=''):
        if group:
            group = f':{group}'
        return self.engine.run_cmd(f'chown {flags} {user}{group} {path}')

    def chown_by_ref_file(self, path, ref_path, flags=''):
        return self.engine.run_cmd(f'chown {flags} --reference={ref_path} {path}')

    def apt_update(self, flags=''):
        return self.engine.run_cmd(f'apt {flags} update', validate=True)

    def apt_install(self, package, flags=''):
        return self.engine.run_cmd(f'apt {flags} install {package}', validate=True)

    def coverage_combine(self, flags=''):
        return self.engine.run_cmd(f'coverage combine {flags}', validate=True)

    def coverage_xml(self, out_file, flags=''):
        return self.engine.run_cmd(f'coverage xml -i -o {out_file} {flags}', validate=True)

    def tar(self, flags=''):
        return self.engine.run_cmd(f'tar {flags}')

    def pip3_install(self, package, flags=''):
        return self.engine.run_cmd(f'pip3 {flags} install {package}', validate=True)

    def gcovr(self, paths='', flags='', additional_flags=''):
        return self.engine.run_cmd(f'gcovr {flags} {paths} {additional_flags}', validate=True)

    def lcovr(self, flags=''):
        return self.engine.run_cmd(f'lcov {flags}', validate=True)

    def get_time(self):
        output = self.engine.run_cmd('date +"%T"', validate=True)
        return output

    def get_date(self):
        output = self.engine.run_cmd('date +"%d-%m-%y"', validate=True)
        return output

    def get_utc_time(self):
        output = self.engine.run_cmd('date +%s', validate=True)
        return output

    def set_time(self, time_str):
        output = self.engine.run_cmd(f'sudo date -s "{time_str}"', validate=True)
        return output

    def find(self, folder, name):
        """
        get result of find command
        :return: command output
        """
        return self.engine.run_cmd(f"sudo find {folder} -name {name}")

    def remove_module(self, module):
        """
        remove module
        """
        return self.engine.run_cmd(f"sudo rmmod {module}")

    def check_module_status(self, module):
        """
        check module install status
        :return: command output
        """
        return self.engine.run_cmd(f"sudo lsmod | grep {module}")

    def install_module(self, module):
        """
        install module
        """
        return self.engine.run_cmd(f"sudo insmod {module}")

    def extract_key_from_module(self, module):
        """
        extract key from a module
        """
        return self.engine.run_cmd(f"sudo strip -g {module}")

    def get_version(self, cli_type):
        version = None
        if cli_type == "NVUE":
            nv_version_json_str = self.engine.run_cmd("nv show system version -o json", validate=True)
            json_output = json.loads(nv_version_json_str)
            version = json_output.get("image")
        elif cli_type == "Sonic":
            sonic_version_output = self.engine.run_cmd('sudo sonic-cfggen -y /etc/sonic/sonic_version.yml'
                                                       ' -v build_version', validate=True)
            version = sonic_version_output.strip()
        return version

    def stat(self, file):
        """
        get status of file
        :return: file stat. e.g.  {"exists": False,"islink": False}
        """
        file_stat = {"exists": False,
                     "islink": False}
        reg_no_file = r"stat: cannot statx .* No such file or directory"
        reg_symbolic_file = r"Size:.*Blocks:.*O Block:.*symbolic link"
        file_stat_res = self.engine.run_cmd(f"sudo stat {file}")
        if re.search(reg_no_file, file_stat_res):
            return file_stat
        file_stat["exists"] = True
        if re.search(reg_symbolic_file, file_stat_res):
            file_stat["islink"] = True
        logger.info(f"{file}: {file_stat}")
        return file_stat

    def read_file(self, file_path):
        """
        Read file content.
        :param file_path:  file path.
        :return: Content of file.
        """
        file_status = self.stat(file_path)
        if not file_status['exists']:
            raise Exception(f'{file_path} not exist')
        return self.engine.run_cmd(f"cat {file_path}")
