"""
This module is used to set and get the OS upgrade flag
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SONIC_UPGRADE_FLAG_FILE = "/etc/sonic_upgrade_flag"


def set_os_upgrade_flag() -> bool:
    """
    Set the flag that indicates the SONiC OS is upgraded
    return True if the flag is successfully set, otherwise False
    """
    try:
        with open(SONIC_UPGRADE_FLAG_FILE, "w") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return True
    except Exception as e:
        logger.error(f"Failed to set the OS upgrade flag: {e}")
        return False


def is_os_upgraded() -> bool:
    """
    Check if the SONiC OS is upgraded
    return True if the flag is set, otherwise False
    """
    try:
        # if the flag file exists and is regular file, return True
        if os.path.exists(SONIC_UPGRADE_FLAG_FILE) and os.path.isfile(SONIC_UPGRADE_FLAG_FILE):
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Failed to check if the OS is upgraded: {e}")
        return False
