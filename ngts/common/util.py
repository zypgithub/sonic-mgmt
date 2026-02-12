import json
import logging
import os
from ngts.constants.constants import INSTALLED_DPUS


logger = logging.getLogger()


def get_specified_installed_dpus(dut_alias, dut_name):
    """
    Get specified installed dpus
    """
    # cleanup if the dut is the dpu itself r-bobcat-03-dpu-0
    if "dpu" in dut_name:
        logger.info(f"Extracting dut switch name from {dut_name}")
        dut_name = dut_name.split("-dpu")[0]
    specified_installed_dpus = []
    input_filename = f"{INSTALLED_DPUS}_{dut_name}"
    if os.path.exists(input_filename):
        with open(input_filename) as f:
            specified_installed_dpus = f.read().split(',')
    logger.info(f"For {dut_name}({dut_alias}) specified installed dpus on {dut_alias} are :{specified_installed_dpus}")
    return specified_installed_dpus


def get_specified_installed_dpu_indexes(dut_alias, dut_name):
    """
    Get specified installed dpu indexes
    """
    installed_dpus = get_specified_installed_dpus(dut_alias, dut_name)
    dpu_indexes = [int(dpu.replace("dpu", '')) for dpu in installed_dpus]
    logger.info(f"For {dut_name}({dut_alias}) specified installed dpus indexes are :{dpu_indexes}")
    return dpu_indexes


def save_specified_installed_dpus(installed_dpus, dut_alias, dut_name):
    """
    Save installed dpus info to /tmp/installed_dpus
    """
    output_filename = f"{INSTALLED_DPUS}_{dut_name}"
    with open(output_filename, "w") as f:
        logger.info(f"write installed dpus {installed_dpus} into {output_filename}")
        f.write(installed_dpus)
    logger.info(f"save installed_dpus of {dut_name}({dut_alias}): {installed_dpus} to:{output_filename}")


def extract_devdescription_from_noga(topology_obj, dut_alias):
    try:
        dev_description_str = topology_obj.players[dut_alias]['attributes'].noga_query_data['attributes']['Specific']['devdescription']
        return json.loads(dev_description_str)
    except KeyError:
        logger.error(f"devdescription not found in noga for {dut_alias}")
    except json.JSONDecodeError:
        logger.error(f"Failed to parse devdescription from noga for {dut_alias}: {dev_description_str}")
    return {}


def get_specified_installed_dpus_from_noga(topology_obj, dut_alias, dut_name, default_dpus="dpu0,dpu1,dpu2,dpu3"):
    """
    Get specified installed dpus from noga
    """
    dut_attr = extract_devdescription_from_noga(topology_obj, dut_alias)
    specified_installed_dpus = dut_attr.get("installed_dpus", default_dpus)
    logger.info(f"specified installed dpus from noga on {dut_name}({dut_alias}) are :{specified_installed_dpus}")
    return specified_installed_dpus


def get_installed_dpu_info(topology_obj, dut_alias, dut_name):
    rshim_value = 'all'
    dpu_index_list = [0, 1, 2, 3]
    installed_dpus = get_specified_installed_dpus_from_noga(topology_obj, dut_alias, dut_name)
    if installed_dpus:
        rshim_value = installed_dpus.replace(' ', '').replace('dpu', 'rshim')
        dpu_index_list = [dpu.replace('dpu', '') for dpu in installed_dpus.split(',')]
        logger.info(f"installed_dpus on {dut_name}({dut_alias}): {installed_dpus}, rshim_value:{rshim_value}, dpu_index_list:{dpu_index_list}")

    return rshim_value, dpu_index_list, installed_dpus
