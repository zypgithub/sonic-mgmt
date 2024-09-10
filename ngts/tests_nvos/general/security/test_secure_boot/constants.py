'''
This file includes the constants used
for secure boot testing
'''


import os


class ChainOfTrustNode:
    SHIM = 'shim'
    GRUB = 'grub'
    VMLINUZ = 'vmlinuz'
    ALL_NODES = [SHIM, GRUB, VMLINUZ]


class SigningState:
    SIGNED = 'signed'
    UNSIGNED = 'unsigned'
    ALL_STATES = [SIGNED, UNSIGNED]


class SecureBootConsts:
    '''
    class contains commands and consts
    '''
    ROOT_PRIVILAGE = 'sudo su'
    TMP_FOLDER = '/tmp'
    MOUNT_FOLDER = '/UEFI'
    EFI_PARTITION_CMD = "fdisk -l | grep \"EFI System\" | awk \'{print $1}\'"
    LAST_OCCURENCE_REGEX = "({})(?!.*\1)"
    LOCAL_SECURE_BOOT_DIR = '/auto/sw_system_project/NVOS_INFRA/security/verification/secure_boot'
    EFI_SECURE_COMPONENT = '{}/EFI/nvos/{}'  # '{}/EFI/debian/{}'
    SHIM_FILEPATH = EFI_SECURE_COMPONENT.format(MOUNT_FOLDER, 'shimx64.efi')
    GRUB_FILEPATH = EFI_SECURE_COMPONENT.format(MOUNT_FOLDER, 'grubx64.efi')
    VMLINUZ_REGEX = '(vmlinuz-.*-amd64)'
    VMLINUZ_DIR = '/boot/'
    INVALID_SIGNATURE = ["Invalid signature detected",
                         "Malformed binary after Attribute Certificate Table",
                         "bad.*signature"]
    REBOOT_CMD = "sudo reboot -f"

    # numerical expressions
    SLEEP_AFTER_ONIE_INSTALL = 45
    SIG_START = -10
    SIG_END = -1

    FILE_DEFAULT_SCP_TIMEOUT = 240

    ONIE_STOP_CMD = 'onie-stop'
    ONIE_NOS_INSTALL_CMD = 'onie-nos-install'
    INSTALL_SUCCESS_PATTERN = 'Installed.*base image.*successfully'

    NBU_NFS_PREFIX = 'http://nbu-mtr-nfs.nvidia.com'

    NVOS_INSTALL_TIME_MINUTES = 5
    NVOS_INSTALL_TIMEOUT = NVOS_INSTALL_TIME_MINUTES * 60

    ONIE_GRUB_MENU_PATTERNS = ['ONIE: Install OS', 'ONIE: Rescue', 'ONIE: Uninstall OS', 'ONIE: Update ONIE',
                               'ONIE: Embed ONIE']
    # ONIE_GRUB_MENU_PATTERN = 'ONIE: Install OS'

    TEST_KERNEL_MODULES_DIR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kernel_modules')
    UNSIGNED_KERNEL_MODULE_PATH = os.path.join(TEST_KERNEL_MODULES_DIR_PATH, 'unsigned_kernel_modules', 'unsecure_kernel_module.ko')
    SIGNED_KERNEL_MODULE_PATH = '/auto/sw_system_project/NVOS_INFRA/security/verification/secure_boot/signed_kernel_module/leds_mlxreg.ko'
    SIGNED_KERNEL_MODULE_KO_FILENAME = 'leds_mlxreg'

    KERNEL_MODULE_KO_PATH = {
        SigningState.SIGNED: SIGNED_KERNEL_MODULE_PATH,
        SigningState.UNSIGNED: UNSIGNED_KERNEL_MODULE_PATH
    }
