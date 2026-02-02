import os
import re
import logging
from jinja2 import Template
from ngts.constants.constants import SimxCommunityConsts, SerialConsts

logger = logging.getLogger(__name__)


def get_dest_file_path(dest_dir_path, file_name, **kwargs):
    suffix = ''
    if file_name in ['testbed']:
        suffix = '.yaml'
    elif file_name in ['sonic_nvidia_devices', 'sonic_nvidia_links']:
        suffix = '.csv'
    elif file_name in ['fanout_port_config']:
        file_name = "port_config"
        suffix = '.ini'
    elif file_name in ['HYPERVISOR']:
        setup_name = kwargs['setup_name'].upper()
        file_name = f'{setup_name}-HYPERVISOR'
        suffix = '.yml'
    file_path = os.path.join(dest_dir_path, f'{file_name}{suffix}')
    return file_path


def validate_and_create_directory(directory_path):
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
        logger.info(f"Creating directory: {directory_path}")
        os.chmod(directory_path, 0o755)


def create_file(source_file_path, dest_dir_path, **kwargs):
    with open(source_file_path, "r") as f:
        template = Template(f.read())
    content = template.render(**kwargs).strip()
    file_name = source_file_path.split('/')[-1].split('.')[0]
    dest_file_path = get_dest_file_path(dest_dir_path, file_name, **kwargs)
    with open(dest_file_path, "w+") as f:
        f.write(content)
    os.chmod(dest_file_path, 0o644)
    logger.info(f"Created file: {dest_file_path}")


def prepare_air_community_directory(setup_name, topology, hwsku, platform_params):
    platform_name = platform_params.platform
    filtered_platform_name = platform_params.filtered_platform.upper()
    dut_ip = topology.players['dut']['engine'].ip
    fanout_ip = topology.players['fanout']['engine'].ip
    hypervisor_ip = topology.players['hyper']['engine'].ip
    oob_mgmt_server_ip = topology.players['oob-mgmt-server']['engine'].ip
    air_community_files_path = SimxCommunityConsts.SIMX_COMMUNITY_FILES_PATH
    common_files_path = SimxCommunityConsts.COMMON_FILES_PATH
    ansible_setup_path = os.path.join(SimxCommunityConsts.ANSIBLE_HWSKU_VARS_PATH, setup_name)

    platform_dir = os.path.join(air_community_files_path, filtered_platform_name)
    hwsku_source_path = os.path.join(platform_dir, hwsku)
    validate_and_create_directory(ansible_setup_path)
    destination_hwsku_path = os.path.join(ansible_setup_path, hwsku)
    validate_and_create_directory(destination_hwsku_path)

    logger.info(f"Creating air-community files for {hwsku} in {destination_hwsku_path}")
    kwargs = {
        "hwsku": hwsku,
        "setup_name": setup_name,
        "platform": filtered_platform_name,
        "dut_ip": dut_ip,
        "fanout_ip": fanout_ip,
        "hypervisor_ip": hypervisor_ip,
        "ptf_ip": SimxCommunityConsts.PTF_IP,
        "server_docker_ip": SimxCommunityConsts.SERVER_DOCKER_IP,
        "oob_mgmt_server_ip": oob_mgmt_server_ip,
        "serial_num": SerialConsts.PLATFORM_SERIAL_NUM_MAP[platform_name]
    }
    create_file(source_file_path=os.path.join(common_files_path, SimxCommunityConsts.HYPERVISOR_FILE_NAME), dest_dir_path=SimxCommunityConsts.HOST_VARS_PATH, **kwargs)
    create_file(source_file_path=os.path.join(platform_dir, "veos.j2"), dest_dir_path=ansible_setup_path, **kwargs)
    for file_name in os.listdir(hwsku_source_path):
        if file_name in SimxCommunityConsts.FILES_TO_TEMPLATE:
            create_file(source_file_path=os.path.join(hwsku_source_path, file_name), dest_dir_path=destination_hwsku_path, **kwargs)
