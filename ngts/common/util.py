import logging
import os
from ngts.constants.constants import INSTALLED_DPUS


logger = logging.getLogger()


def get_specified_installed_dpus():
    """
    Get specified installed dpus
    """
    specified_installed_dpus = []
    if os.path.exists(INSTALLED_DPUS):
        with open(INSTALLED_DPUS) as f:
            specified_installed_dpus = f.read().split(',')
    logger.info(f"specified installed dpus are :{specified_installed_dpus}")
    return specified_installed_dpus


def get_specified_installed_dpu_indexes():
    """
    Get specified installed dpu indexes
    """
    installed_dpus = get_specified_installed_dpus()
    dpu_indexes = [int(dpu.replace("dpu", '')) for dpu in installed_dpus]
    logger.info(f"specified installed dpus indexes are :{dpu_indexes}")
    return dpu_indexes


def save_specified_installed_dpus(installed_dpus):
    """
    Save installed dpus info to /tmp/installed_dpus
    """
    with open(INSTALLED_DPUS, "a") as f:
        logger.info(f"write installed dpus {installed_dpus} into {INSTALLED_DPUS}")
        f.write(installed_dpus)
    logger.info(f"save installed_dpus:{installed_dpus} to:{INSTALLED_DPUS}")


def get_specified_installed_dpus_from_noga(topology_obj):
    """
    Get specified installed dpus from noga
    """
    dut_attr = eval(topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['devdescription'])
    specified_installed_dpus = dut_attr.get("installed_dpus", "dpu0,dpu1,dpu2,dpu3")
    logger.info(f"specified installed dpus from noga are :{specified_installed_dpus}")
    return specified_installed_dpus


def get_installed_dpu_info(topology_obj):
    rshim_value = 'all'
    dpu_index_list = [0, 1, 2, 3]
    installed_dpus = get_specified_installed_dpus_from_noga(topology_obj)
    if installed_dpus:
        rshim_value = installed_dpus.replace(' ', '').replace('dpu', 'rshim')
        dpu_index_list = [dpu.replace('dpu', '') for dpu in installed_dpus.split(',')]
        logger.info(f"installed_dpus:{installed_dpus}, rshim_value:{rshim_value}, dpu_index_list:{dpu_index_list}")

    return rshim_value, dpu_index_list, installed_dpus
