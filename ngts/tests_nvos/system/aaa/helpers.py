import logging
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import SystemConsts

logger = logging.getLogger()


def create_new_user(role: str, apply: bool = True):
    # Forcing NVUE API type for this operation until the issue of setting password with OPENAPI is fixed :
    return System(force_api=ApiType.NVUE).aaa.user.set_new_user(role=role, apply=apply)


def change_user_role(username: str, role: str, apply: bool = True):
    System().aaa.user.user_id[username].set(SystemConsts.USER_ROLE, role, apply=apply).verify_result()
    logger.info(f'Changed role for user {username} to {role}')
