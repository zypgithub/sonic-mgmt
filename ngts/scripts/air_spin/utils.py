import os
import json
from jinja2 import Environment, FileSystemLoader
import sys
from .config import SETUPS_FOLDER_PATH, TOPO_FOLDER_PATH, TOPO_TEMPLATE_FILE, SETUP_TEMPLATE_FILE, NOGA_MANAGE_SCRIPT, TEMPLATE_FOLDER_PATH, RESULTS_FOLDER_PATH

import logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)


def save_file(path, content):
    with open(path, "w") as f:
        f.write(content)
    os.system(f"chmod 666 {path}")
    logger.info(f"Created file: {path}")

def render_template(template_name, context, dir_path, file_name):
    env = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER_PATH))
    template = env.get_template(template_name)
    output = template.render(context)
    file_path = os.path.join(dir_path, file_name)
    save_file(file_path, output)
    return file_path
    
def create_setup_file(setup_obj):
    setup_path = os.path.join(SETUPS_FOLDER_PATH, setup_obj.setup_name)
    os.makedirs(setup_path, exist_ok=True)
    context = {
        "dut": setup_obj,
        "hypervisor": setup_obj.vm_obj
    }
    setup_obj.setup_path = render_template(SETUP_TEMPLATE_FILE, context, setup_path, f"{setup_obj.setup_name}.setup")

def create_config_db_file(setup_obj):
    template_config_db_path = os.path.join(TEMPLATE_FOLDER_PATH, "config_db_template.json")
    config_db_path = os.path.join(TOPO_FOLDER_PATH, setup_obj.setup_name, "config_db.json")
    config_db_dict = json.load(open(template_config_db_path))
    config_db_dict['DEVICE_METADATA']['localhost']['hostname'] = setup_obj.setup_name
    json.dump(config_db_dict, open(config_db_path, "w"), indent=4)
    print(f"Created config_db.json file: {config_db_path}")

def create_topo_files(setup_obj):
    topology_path = os.path.join(TOPO_FOLDER_PATH, setup_obj.setup_name)
    os.makedirs(topology_path, exist_ok=True)
    context = {
        "dut": setup_obj,
        "hypervisor": setup_obj.vm_obj
    }
    topology_file_path = render_template("topology_template.xml", context, topology_path, "topology.xml")
    # config_db_file_path = render_template("config_db_template.json", context, topology_path, "config_db.json")
    setup_obj.topology_xml_path = topology_file_path
    create_config_db_file(setup_obj)

def prepare_results_dir(setup_obj):
    os.makedirs(os.path.join(RESULTS_FOLDER_PATH, setup_obj.setup_name), exist_ok=True)
    os.makedirs(os.path.join(RESULTS_FOLDER_PATH, setup_obj.setup_name, "logs"), exist_ok=True)
    setup_obj.results_dir = os.makedirs(os.path.join(RESULTS_FOLDER_PATH, setup_obj.setup_name, "results"), exist_ok=True)
    setup_obj.logs_dir = os.makedirs(os.path.join(RESULTS_FOLDER_PATH, setup_obj.setup_name, "logs"), exist_ok=True)


def start_deployment_with_mini_mars(setup_obj):
    prepare_results_dir(setup_obj)
    cmd = f"/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/4_4_4_1//bin/mars_docker_executor.py \
    --command '/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/4_4_4_1//bin/mini_mars_runner.py \
    --local_conf /auto/sw_regression/system/SONIC/MARS/conf/global/setups_mgr_local_mtr-stm-095.conf \
    --global_conf /auto/sw_regression/system/SONIC/MARS/conf/global/MARS_SONiC_setups_mgr_docker.conf \
    --setup_id {setup_obj.setup_name} \
    --setup_conf_file {setup_obj.setup_path} \
    --results_dir /auto/mtrsysgwork/ytzur/results_qw/ \
    --meinfo_detect_players_pyversion True \
    --meinfo_IGNORE_NOGA_SETUP_LOCK  True \
    --meinfo_IGNORE_NOGA_SETUP_UNLOCK  True \
    --meinfo_skip_run_db true' --docker_name {setup_obj.setup_name}_mini_mars_runner"
    #connect to mtr-stm-095
    cmd = f"sshpass -p 3tango ssh root@mtr-stm-095 \"{cmd}\""
    res = os.system(cmd)
    if res != 0:
        raise Exception(f"Failed to start simulation with mini mars, error: {res}")
    return res