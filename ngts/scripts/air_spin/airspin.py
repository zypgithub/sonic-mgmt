import os
import json
import subprocess
import re

from jinja2 import Environment, FileSystemLoader
from .message import Message
from .config import AIR_WEBSITE_SIMULATIONS_URL, RESULTS_FOLDER_PATH, SETUPS_FOLDER_PATH, TOPO_FOLDER_PATH, TEMPLATE_FOLDER_PATH
from .config import SETUP_TEMPLATE_FILE, TOPO_TEMPLATE_FILE, SPIN_AIR_RESULTS_FOLDER_PATH, STM, STM_PASSWORD, STM_USER

msg = Message()


class AirSpin:
    def __init__(self, **kwargs):
        self.setup_name = kwargs.get("setup_name")
        self.topology_type = kwargs.get("topology_type")
        self.organization_name = kwargs.get("organization_name")
        self.dut_name = kwargs.get("dut_name") if kwargs.get("dut_name") else self.setup_name
        self.dut_hwsku = kwargs.get("dut_hwsku")
        self.base_version = kwargs.get("base_version")
        self.custom_tarball_name = kwargs.get("custom_tarball_name")
        self.custom_links_path = kwargs.get("custom_links_path")
        self.dbs_to_run = kwargs.get("dbs_to_run")
        self.username = kwargs.get("username")
        self.topology_file_path = None
        self.setup_path = None
        self.docker_mac = None
        self.simulation_data = None
        self.ngts_docker_name = self.username + "_airspin_runner"
        if self.setup_name:
            self.mars_docker_name = self.setup_name + "_mini_mars_runner"
        self.force_clean_up_dockers()

    def create_simulation(self):
        msg.info(f"Starting to create AIR SIMULATION named:'{self.setup_name}' for user:{self.username}")
        msg.info(f"You can find your simulation in Air website: {AIR_WEBSITE_SIMULATIONS_URL} after it's created successfully.")
        default_db = f"{self.topology_type}/airspin_default.db"
        db_list = [default_db]
        if not self.dbs_to_run:
            msg.warning(f"No test dbs are provided, will only run the default db: {default_db}")
        else:
            db_list.extend(self.dbs_to_run.split(","))
        self.dbs_to_run = db_list
        self._create_files()
        self._run_simulation_with_mini_mars()

    def _get_default_docker_tag(self):
        """Get default docker tag from update_docker.py without importing it"""
        update_docker_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..",  # Go up to sonic-mgmt
            "sonic-tool", "mars", "scripts", "update_docker.py"
        )
        update_docker_path = os.path.normpath(update_docker_path)
        try:
            msg.info(f"Reading update_docker.py for the docker-ngts tag...")
            with open(update_docker_path, 'r') as f:
                content = f.read()
            # Find the default_list dictionary in the file
            # Match pattern like: 'docker-ngts': '1.2.500'
            pattern = r"{.*docker-ngts.*(1\.\d\.\d+).*}"
            match = re.search(pattern, content)
            if match:
                return match.group(1)
            else:
                msg.warning(f"Could not find default tag for docker-ngts, using 'latest'")
                return "latest"
        except Exception as e:
            msg.warning(f"Could not read update_docker.py: {e}, using 'latest'")
            return "latest"

    def get_simulations(self):
        docker_tag = self._get_default_docker_tag()
        msg.info(f"Pulling ngts docker image: {docker_tag} on STM:{STM}, this may take a few minutes...")
        docker_image = f"harbor.mellanox.com/sonic/docker-ngts:{docker_tag}"
        self._run_cmd_in_stm(f"docker pull {docker_image}")
        msg.info(f"Pulled ngts docker image successfully.")
        try:
            self._run_cmd_in_stm(f"docker run -dt --name {self.ngts_docker_name} --env-file <(env) {docker_image}")
            cmd = f"PYTHONPATH=/devts /ngts_venv/bin/python /devts/scripts/airspin_simulation_mgmt.py --list --username {self.username}"
            result = self._run_cmd_in_stm(f"docker exec -i {self.ngts_docker_name} sh -c \'{cmd}\'")
            simulation_list = []
            simulations_output = result.stdout.strip().split(f"Airspin simulations for user {self.username}:")[1].strip()
            if simulations_output:
                simulation_list = simulations_output.split("\n")
            return simulation_list
        finally:
            self.force_clean_up_dockers()

    def _create_files(self):
        self.create_setup_file()
        self.create_topo_files()

    def _run_simulation_with_mini_mars(self):
        self.prepare_results_dir()
        cmd = f"/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/last_release/bin/mars_docker_executor.py \
            --command \'/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/last_release/bin/mini_mars_runner.py \
            --local_conf /auto/sw_regression/system/SONIC/MARS/conf/global/setups_mgr_local_{STM}.conf \
            --global_conf /auto/sw_regression/system/SONIC/MARS/conf/global/MARS_SONiC_setups_mgr_docker_airspin.conf \
            --setup_id {self.setup_name} \
            --setup_conf_file {self.setup_path} \
            --results_dir {SPIN_AIR_RESULTS_FOLDER_PATH} \
            --meinfo_detect_players_pyversion True \
            --meinfo_IGNORE_NOGA_SETUP_LOCK True \
            --meinfo_IGNORE_NOGA_SETUP_UNLOCK True \'\
            --docker_name {self.mars_docker_name}"

        msg.info(f"Running simulation with minimars: {cmd} on stm")
        res = self._run_cmd_in_stm(cmd, validate=False, terminal=True)
        if res.returncode != 0:
            self.force_clean_up_dockers()
            raise Exception(f"Start Airspin simulation failed.")

        msg.success(f"Simulation completed successfully")

    def prepare_results_dir(self):
        setup_path = os.path.join(RESULTS_FOLDER_PATH, self.setup_name)
        self._create_dir(setup_path)
        setup_logs_path = os.path.join(setup_path, "logs")
        self._create_dir(setup_logs_path)
        results_path = os.path.join(setup_path, "results")
        self._create_dir(results_path)
        self.logs_dir = setup_logs_path
        self.results_dir = results_path

    def _save_file(self, path, content):
        with open(path, "w") as f:
            f.write(content)
        os.system(f"chmod 777 {path}")
        msg.info(f"Created file: {path}")

    def _create_dir(self, path):
        os.makedirs(path, exist_ok=True)
        os.system(f"chmod 777 {path}")
        msg.info(f"Created directory: {path}")

    def render_template(self, template_name, context, dir_path, file_name):
        env = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER_PATH))
        template = env.get_template(template_name)
        output = template.render(context)
        file_path = os.path.join(dir_path, file_name)
        self._save_file(file_path, output)
        return file_path

    def update_execution_block(self, dbs_to_run):
        if isinstance(dbs_to_run, list):
            dbs = dbs_to_run
        else:
            dbs = json.load(open(dbs_to_run))
        execution_block = []
        for db in dbs:
            execution_block.append({
                "entry_points": "SONIC_MGMT",
                "tests_dbs_tarball": "sonic-mgmt/sonic-tool/mars/dbs/" + db
            })
        return execution_block

    def create_setup_file(self):
        setup_path = os.path.join(SETUPS_FOLDER_PATH, self.setup_name)
        self._create_dir(setup_path)
        execution_block = self.update_execution_block(self.dbs_to_run)
        context = {
            "dut": self,
            "execution_block": execution_block
        }
        self.setup_path = self.render_template(SETUP_TEMPLATE_FILE, context, setup_path, f"{self.setup_name}.setup")

    def create_config_db_file(self, setup_topo_path):
        template_config_db_path = os.path.join(TEMPLATE_FOLDER_PATH, "config_db_template.json")
        config_db_dict = json.load(open(template_config_db_path))
        config_db_dict['DEVICE_METADATA']['localhost']['hostname'] = self.setup_name
        config_db_path = os.path.join(setup_topo_path, "config_db_try.json")
        self._save_file(config_db_path, json.dumps(config_db_dict, indent=4))
        os.system(f"chmod 777 {config_db_path}")
        msg.info(f"Created config_db.json file: {config_db_path}")

    def create_topo_files(self):
        setup_topo_path = os.path.join(TOPO_FOLDER_PATH, self.setup_name)
        self._create_dir(setup_topo_path)
        context = {
            "dut": self.dut_name,
        }
        topology_file_path = self.render_template(TOPO_TEMPLATE_FILE, context, setup_topo_path, "topology.xml")
        self.topology_file_path = topology_file_path
        self.create_config_db_file(setup_topo_path)

    def force_clean_up_dockers(self):
        try:
            if hasattr(self, "ngts_docker_name"):
                self._run_cmd_in_stm(f"docker rm -f {self.ngts_docker_name}", validate=False)
            if hasattr(self, "mars_docker_name"):
                self._run_cmd_in_stm(f"docker rm -f {self.mars_docker_name}", validate=False)
        except Exception as e:
            pass

    def _run_cmd_in_stm(self, cmd, validate=True, terminal=False):
        ssh_cmd = f'sshpass -p {STM_PASSWORD} ssh {STM_USER}@{STM} \"{cmd}\"'

        class Result:
            def __init__(self, returncode, stdout, stderr):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        if terminal:
            result = os.system(ssh_cmd)
            result = Result(result, None, None)
        else:
            result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
            result = Result(result.returncode, result.stdout, result.stderr)

        if validate and result.returncode != 0:
            raise Exception(f"Failed to run command: {cmd}, error: \n{result.stderr}")

        return result
