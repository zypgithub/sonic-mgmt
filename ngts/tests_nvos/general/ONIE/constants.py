class OnieConsts:
    '''
    Class contains ONIE-related commands and constants.
    '''
    ONIE_UPDATER_FILE = 'onie-updater-x86_64-mlnx_x86-r0'
    ONIE_UPDATE_COMMAND = f'onie-self-update ./{ONIE_UPDATER_FILE}'
    UPDATE_ONIE_MENU_ENTRY = 'ONIE: Update ONIE'
    UPDATE_SUCCESS_PATTERN = '.*ONIE: Success.*'

    ONIE_FILES_DICT = {
        'OPN': "http://nbu-nfs.mellanox.com/auto/sw_system_release/sx_mlnx_os/onie_release/5.3.0015/115200/onie-updater-x86_64-mlnx_x86-r0",
        'IPN': "http://nbu-nfs.mellanox.com/auto/sw_system_release/sx_mlnx_os/onie_release/5.3.0015/dev/115200/onie-updater-x86_64-mlnx_x86-r0",
    }

    ONIE_VERSIONS_PXE_DICT = {
        'OPN': "ONIE_r5.3.0015-115200",
        'IPN': "ONIE_r5.3.0015-115200-dev",
    }

    WGET_ERROR = "wget:.*"
    CMS_VERIFICATION_ERROR = "CMS Verification Failure.*"
