class OnieConsts:
    '''
    Class contains ONIE-related commands and constants.
    '''
    OPN = 'OPN'
    IPN = 'IPN'
    ONIE_UPDATER_FILE = 'onie-updater-x86_64-mlnx_x86-r0'
    ONIE_UPDATE_COMMAND = f'onie-self-update ./{ONIE_UPDATER_FILE}'
    UPDATE_ONIE_MENU_ENTRY = 'ONIE: Update ONIE'
    RESCUE_MENU_ENTRY = 'ONIE: Rescue'
    UPDATE_SUCCESS_PATTERN = '.*ONIE: Success.*'

    ONIE_FILES_DICT = {
        'OPN': "http://nbu-nfs.mellanox.com/auto/sw_system_release/sx_mlnx_os/onie_release/5.3.0017/prod/115200/onie-updater-x86_64-mlnx_x86-r0",
        'IPN': "http://nbu-nfs.mellanox.com/auto/sw_system_release/sx_mlnx_os/onie_release/5.3.0017/dev/115200/onie-updater-x86_64-mlnx_x86-r0",
    }

    ONIE_VERSIONS_PXE_DICT = {
        'OPN': "ONIE_r5.3.0017-115200",
        'IPN': "ONIE_r5.3.0017-115200-dev",
    }

    WGET_ERROR = "wget:.*"
    CMS_VERIFICATION_ERROR = "CMS Verification Failure.*"


class ProvisionConsts:
    VERSION = "83.03.0009"
    VERSIONS_DICT = {
        'OPN': {
            'version': VERSION,
            'provisioning_url': f'https://urm.nvidia.com/artifactory/sw-nbu-sws-low-level-generic-local/sedutil/SED_PBA/{VERSION}/sed_provisioning_{VERSION}.tgz',
        },
        'IPN': {
            'version': VERSION + "-dev",
            'provisioning_url': f'https://urm.nvidia.com/artifactory/sw-nbu-sws-low-level-generic-local/sedutil/SED_PBA/{VERSION}_dev/sed_provisioning_{VERSION}-dev_dev.tgz',
        }
    }
