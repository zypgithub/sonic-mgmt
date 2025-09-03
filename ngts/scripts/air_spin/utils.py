import os
import json
from jinja2 import Environment, FileSystemLoader
from .config import *


def save_file(path, content):
    with open(path, "w") as f:
        f.write(content)
    os.system(f"chmod 777 {path}")
    print(f"Created file: {path}")


def create_dir(path):
    os.makedirs(path, exist_ok=True, mode=0o777)
    print(f"Created directory: {path}")


def render_template(template_name, context, dir_path, file_name):
    env = Environment(loader=FileSystemLoader(TEMPLATE_FOLDER_PATH))
    template = env.get_template(template_name)
    output = template.render(context)
    file_path = os.path.join(dir_path, file_name)
    save_file(file_path, output)
    return file_path


def update_execution_block(dbs_to_run_path):
    dbs = json.load(open(dbs_to_run_path))
    execution_block = []
    for db in dbs:
        execution_block.append({
            "entry_points": "SONIC_MGMT",
            "tests_dbs_tarball": "sonic-mgmt/sonic-tool/mars/dbs/" + db
        })
    return execution_block


def create_setup_file(setup_obj):
    setup_path = os.path.join(SETUPS_FOLDER_PATH, setup_obj.setup_name)
    create_dir(setup_path)
    execution_block = update_execution_block(setup_obj.dbs_to_run_path)
    context = {
        "dut": setup_obj,
        "hypervisor": setup_obj.vm_obj,
        "execution_block": execution_block
    }
    setup_obj.setup_path = render_template(SETUP_TEMPLATE_FILE, context, setup_path, f"{setup_obj.setup_name}.setup")


def create_config_db_file(setup_obj, setup_topo_path):
    template_config_db_path = os.path.join(TEMPLATE_FOLDER_PATH, "config_db_template.json")
    config_db_dict = json.load(open(template_config_db_path))
    config_db_dict['DEVICE_METADATA']['localhost']['hostname'] = setup_obj.setup_name
    config_db_path = os.path.join(setup_topo_path, "config_db_try.json")
    json.dump(config_db_dict, open(config_db_path, "w"), indent=4)
    os.system(f"chmod 777 {config_db_path}")
    print(f"Created config_db.json file: {config_db_path}")


def create_topo_files(setup_obj):
    setup_topo_path = os.path.join(TOPO_FOLDER_PATH, setup_obj.setup_name)
    create_dir(setup_topo_path)
    context = {
        "dut": setup_obj,
        "hypervisor": setup_obj.vm_obj
    }
    topology_file_path = render_template(TOPO_TEMPLATE_FILE, context, setup_topo_path, "topology.xml")
    setup_obj.topology_file_path = topology_file_path
    create_config_db_file(setup_obj, setup_topo_path)


def prepare_results_dir(setup_obj):
    setup_path = os.path.join(RESULTS_FOLDER_PATH, setup_obj.setup_name)
    create_dir(setup_path)
    setup_logs_path = os.path.join(setup_path, "logs")
    create_dir(setup_logs_path)
    results_path = os.path.join(setup_path, "results")
    create_dir(results_path)
    setup_obj.logs_dir = setup_logs_path
    setup_obj.results_dir = results_path


def run_cmd_in_stm(cmd):
    cmd = f'sshpass -p {STM_PASSWORD} ssh {STM_USER}@mtr-stm-095 \"{cmd}\"'
    os.system(cmd)


def run_simulation_with_mini_mars(setup_obj):
    prepare_results_dir(setup_obj)
    cmd = f"/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/last_release/bin/mars_docker_executor.py \
        --command \'/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/last_release/bin/mini_mars_runner.py \
        --local_conf /auto/sw_regression/system/SONIC/MARS/conf/global/setups_mgr_local_mtr-stm-095.conf \
        --global_conf /auto/sw_regression/system/SONIC/MARS/conf/global/MARS_SONiC_setups_mgr_docker.conf \
        --setup_id {setup_obj.setup_name} \
        --setup_conf_file {setup_obj.setup_path} \
        --results_dir {SPIN_AIR_RESULTS_FOLDER_PATH} \
        --meinfo_detect_players_pyversion True \
        --meinfo_IGNORE_NOGA_SETUP_LOCK True \
        --meinfo_IGNORE_NOGA_SETUP_UNLOCK True \'\
        --docker_name {setup_obj.setup_name}_mini_mars_runner"

    # print(cmd)
    res = run_cmd_in_stm(cmd)
    if res != 0:
        raise Exception(f"Failed to run simulation with mini mars, error: {res}")

    print(f"Simulation completed successfully")
    return res
