import os
import json
from ngts.constants.constants import SonicConst

LOCAL_CONFIG_DB_PATH = os.path.join('/tmp', SonicConst.CONFIG_DB_JSON)


def save_config_db_json(engine, config_db_json, json_path=LOCAL_CONFIG_DB_PATH, remove_json_path=True):
    """
    save json to the config_db.json file
    :param engine: ssh engine object
    :param config_db_json: config db content in json format
    :return: None
    """
    with open(json_path, 'w') as f:
        json.dump(config_db_json, f, indent=4)
        # Python JSON dump misses last newline, so add the newline at the end of the file
        f.write("\n")
    engine.copy_file(source_file=json_path, dest_file=SonicConst.CONFIG_DB_JSON,
                     file_system='/tmp', overwrite_file=True, verify_file=False)
    engine.run_cmd(f'sudo mv {os.path.join("/tmp", SonicConst.CONFIG_DB_JSON)} {SonicConst.CONFIG_DB_JSON_PATH}')
    if remove_json_path:
        os.remove(json_path)


def save_config_into_json(engine, config_dict, config_file_name, dst_folder='/tmp'):
    """
    Save json config to file and upload to DUT dst folder
    :param engine: ssh engine object
    :param config_dict: dictionary which should be saved into json
    :param config_file_name: config db content in json format
    :param dst_folder: destination folder
    :return: string with path to file on DUT
    """
    local_file_path = f'/tmp/{config_file_name}'
    with open(local_file_path, 'w') as f:
        json.dump(config_dict, f, indent=4)
        # Python JSON dump misses last newline, so add the newline at the end of the file
        f.write("\n")
    engine.copy_file(source_file=local_file_path, dest_file=config_file_name,
                     file_system=dst_folder, overwrite_file=True, verify_file=False)
    os.remove(local_file_path)
    path_to_file_on_dut = f'{dst_folder}/{config_file_name}'
    return path_to_file_on_dut
