
UPGRADE_STATUS_FILE_PATH = '/tmp/upgrade-status'
UPGRADE_STATUS_SUCCESS_MSG = 'success'
UPGRADE_STATUS_FAIL_PREFIX = 'Upgrade status FAILURE'
UPGRADE_STATUS_FAIL_MSG = f'{UPGRADE_STATUS_FAIL_PREFIX}: Configuration after upgrade is not as saved before the upgrade.'


class InstallSteps:
    ONIE_NOS_INSTALL = 'onie-nos-install'
    INSTALL_SUCCESS = 'install success'
    SYSTEM_IS_READY_AFTER_MANUFACTURE = 'system is ready after manufacture'
    UPGRADE_CMD = 'upgrade command'
    SHUT_DOWN = 'shut down - no ping'
    SYSTEM_IS_READY_AFTER_UPGRADE = 'system is ready after upgrade'

    ALL_STEPS = [ONIE_NOS_INSTALL, INSTALL_SUCCESS, SYSTEM_IS_READY_AFTER_MANUFACTURE, UPGRADE_CMD, SHUT_DOWN, SYSTEM_IS_READY_AFTER_UPGRADE]
