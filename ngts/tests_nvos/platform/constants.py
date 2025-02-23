class Transceiver:
    def __init__(self, transceiver_type, last_release_path, test_versions_path,
                 upgrade_version_name, downgrade_version_name,
                 upgrade_version_number, downgrade_version_number,
                 installation_time):
        self.transceiver_type = transceiver_type
        self.last_release_path = last_release_path
        self.test_versions_path = test_versions_path
        self.upgrade_version_name = upgrade_version_name
        self.downgrade_version_name = downgrade_version_name
        self.upgrade_version_number = upgrade_version_number
        self.downgrade_version_number = downgrade_version_number
        self.installation_time = installation_time

    def update_versions(self):
        self.upgrade_version_name = self.upgrade_version_name.replace('dev', 'pk')
        self.downgrade_version_name = self.downgrade_version_name.replace('dev', 'pk')


class TransceiversConsts:
    TRANSCEIVER_TYPE = 'type'
    TRANSCEIVER_LAST_RELEASE_PATH = "releases_path"
    TRANSCEIVER_TEST_VERSIONS_PATH = "test_versions_path"
    TRANSCEIVER_UPGRADE_VERSION_NAME = 'upgrade_versions'
    TRANSCEIVER_DOWNGRADE_VERSION_NAME = 'downgrade_versions'
    TRANSCEIVER_UPGRADE_VERSION_NUMBER = 'upgrade_fw'
    TRANSCEIVER_DOWNGRADE_VERSION_NUMBER = 'downgrade_fw'
    TRANSCEIVER_INSTALLATION_TIME = "installation_time"
    TRANSCEIVERS_APPROVED_FIRMWARES_PATH = '/auto/sw_system_project/NVOS_INFRA/verification_files/transceiver_fw/'
    TRANSCEIVERS_FIRMWARES_PATH = '/.autodirect/sw/release/fwshared/linkx/mlnx_linkx_module_aoc_fw/'
    TRANSCEIVERS_RELEASE = '230_00_release'     # the latest approved release

    TRANSCEIVERS_DETAILS = {
        '39': Transceiver(
            transceiver_type='Xodin',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}39_Xodin/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Xodin/",
            upgrade_version_name="fw_39_230_00024_dev_signed.bin",
            downgrade_version_name="fw_39_230_00020_dev_signed.bin",
            upgrade_version_number="39.230.24",
            downgrade_version_number="39.230.20",
            installation_time=180
        ),
        '70': Transceiver(
            transceiver_type='Wolverine',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}70_Wolverine/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Wolverine/",
            upgrade_version_name="fw_70_230_01031_dev_signed_WOLVERINE_DK.bin",
            downgrade_version_name="fw_70_230_01023_dev_signed_WOLVERINE_DK.bin",
            upgrade_version_number="70.230.1031",
            downgrade_version_number="70.230.1023",
            installation_time=360
        ),
        '46': Transceiver(
            transceiver_type='Bagheera',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}46_Bagheera1_2/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Bagheera/",
            upgrade_version_name="fw_46_230_00018_dev_signed.bin",
            downgrade_version_name="fw_46_230_00014_dev_signed.bin",
            upgrade_version_number="46.230.18",
            downgrade_version_number="46.230.14",
            installation_time=180
        ),
        '47': Transceiver(
            transceiver_type='Louie',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}47_Louie1_4/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Louie/",
            upgrade_version_name="fw_47_230_01018_dev_signed.bin",
            downgrade_version_name="fw_47_230_01014_dev_signed.bin",
            upgrade_version_number="47.230.18",
            downgrade_version_number="47.230.14",
            installation_time=180
        )
    }
