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
    TRANSCEIVERS_ELS = 'els'
    TRANSCEIVERS_OE = 'oe'
    TRANSCEIVERS_SW = 'sw'
    TRANSCEIVERS_FIELDS = {
        TRANSCEIVERS_ELS: ['channel', 'diagnostics-status', 'els-initialization', 'error-status', 'fault-condition',
                           'fw-version', 'identifier', 'oe-mapping', 'port-mapping', 'status',
                           'temperature', 'vendor-date-code', 'vendor-name', 'vendor-pn', 'vendor-rev', 'vendor-sn',
                           'voltage'],
        TRANSCEIVERS_OE: ['channel', 'diagnostics-status', 'dp-fw-fault', 'els-mapping', 'error-status', 'fw-version',
                          'identifier', 'mod-fw-fault', 'port-mapping', 'status', 'temperature', 'vendor-date-code',
                          'vendor-name', 'vendor-pn', 'vendor-rev', 'vendor-sn', 'voltage'],
        TRANSCEIVERS_SW: ['cable-length', 'cable-type', 'diagnostics-status', 'dp-fw-fault', 'error-status',
                          'fw-version', 'identifier', 'mod-fw-fault', 'status', 'vendor-date-code', 'vendor-name',
                          'vendor-pn', 'vendor-rev', 'vendor-sn']
    }
    TRANSCEIVERS_ELS_PORT_MAPPING = {
        'els1': ['sw137p1', 'sw138p1', 'sw139p1', 'sw140p1', 'sw141p1', 'sw142p1', 'sw143p1', 'sw144p1'],
        'els2': ['sw129p1', 'sw130p1', 'sw131p1', 'sw132p1', 'sw133p1', 'sw134p1', 'sw135p1', 'sw136p1'],
        'els3': ['sw121p1', 'sw122p1', 'sw123p1', 'sw124p1', 'sw125p1', 'sw126p1', 'sw127p1', 'sw128p1'],
        'els4': ['sw113p1', 'sw114p1', 'sw115p1', 'sw116p1', 'sw117p1', 'sw118p1', 'sw119p1', 'sw120p1'],
        'els5': ['sw105p1', 'sw106p1', 'sw107p1', 'sw108p1', 'sw109p1', 'sw110p1', 'sw111p1', 'sw112p1'],
        'els6': ['sw97p1', 'sw98p1', 'sw99p1', 'sw100p1', 'sw101p1', 'sw102p1', 'sw103p1', 'sw104p1'],
        'els7': ['sw89p1', 'sw90p1', 'sw91p1', 'sw92p1', 'sw93p1', 'sw94p1', 'sw95p1', 'sw96p1'],
        'els8': ['sw81p1', 'sw82p1', 'sw83p1', 'sw84p1', 'sw85p1', 'sw86p1', 'sw87p1', 'sw88p1'],
        'els9': ['sw73p1', 'sw74p1', 'sw75p1', 'sw76p1', 'sw77p1', 'sw78p1', 'sw79p1', 'sw80p1'],
        'els10': ['sw65p1', 'sw66p1', 'sw67p1', 'sw68p1', 'sw69p1', 'sw70p1', 'sw71p1', 'sw72p1'],
        'els11': ['sw57p1', 'sw58p1', 'sw59p1', 'sw60p1', 'sw61p1', 'sw62p1', 'sw63p1', 'sw64p1'],
        'els12': ['sw49p1', 'sw50p1', 'sw51p1', 'sw52p1', 'sw53p1', 'sw54p1', 'sw55p1', 'sw56p1'],
        'els13': ['sw41p1', 'sw42p1', 'sw43p1', 'sw44p1', 'sw45p1', 'sw46p1', 'sw47p1', 'sw48p1'],
        'els14': ['sw33p1', 'sw34p1', 'sw35p1', 'sw36p1', 'sw37p1', 'sw38p1', 'sw39p1', 'sw40p1'],
        'els15': ['sw25p1', 'sw26p1', 'sw27p1', 'sw28p1', 'sw29p1', 'sw30p1', 'sw31p1', 'sw32p1'],
        'els16': ['sw17p1', 'sw18p1', 'sw19p1', 'sw20p1', 'sw21p1', 'sw22p1', 'sw23p1', 'sw24p1'],
        'els17': ['sw9p1', 'sw10p1', 'sw11p1', 'sw12p1', 'sw13p1', 'sw14p1', 'sw15p1', 'sw16p1'],
        'els18': ['sw1p1', 'sw2p1', 'sw3p1', 'sw4p1', 'sw5p1', 'sw6p1', 'sw7p1', 'sw8p1']
    }
    TRANSCEIVERS_ELS_OE_MAPPING = {
        'els1': ['oe10', 'oe28', 'oe45', 'oe63'], 'els2': ['oe11', 'oe29', 'oe44', 'oe62'],
        'els3': ['oe12', 'oe30', 'oe43', 'oe61'], 'els4': ['oe13', 'oe31', 'oe42', 'oe60'],
        'els5': ['oe14', 'oe32', 'oe41', 'oe59'], 'els6': ['oe15', 'oe33', 'oe40', 'oe58'],
        'els7': ['oe16', 'oe34', 'oe39', 'oe57'], 'els8': ['oe17', 'oe35', 'oe38', 'oe56'],
        'els9': ['oe18', 'oe36', 'oe37', 'oe55'], 'els10': ['oe1', 'oe19', 'oe54', 'oe72'],
        'els11': ['oe2', 'oe20', 'oe53', 'oe71'], 'els12': ['oe3', 'oe21', 'oe52', 'oe70'],
        'els13': ['oe4', 'oe22', 'oe51', 'oe69'], 'els14': ['oe5', 'oe23', 'oe50', 'oe68'],
        'els15': ['oe6', 'oe24', 'oe49', 'oe67'], 'els16': ['oe7', 'oe25', 'oe48', 'oe66'],
        'els17': ['oe8', 'oe26', 'oe47', 'oe65'], 'els18': ['oe9', 'oe27', 'oe46', 'oe64']
    }

    TRANSCEIVERS_DETAILS = {  # TODO [L.A] Add Taipan transceiver when known
        '39': Transceiver(
            transceiver_type='Xodin',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}39_Xodin/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Xodin/",
            upgrade_version_name="fw_39_230_00032_dev_signed.bin",
            downgrade_version_name="fw_39_230_00030_dev_signed.bin",
            upgrade_version_number="39.230.32",
            downgrade_version_number="39.230.30",
            installation_time=180
        ),
        '70': Transceiver(
            transceiver_type='Wolverine',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}70_Wolverine/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Wolverine/",
            upgrade_version_name="fw_70_250_00097_dev_signed_WOLVERINE_DK.bin",
            downgrade_version_name="fw_70_250_00096_dev_signed_WOLVERINE_DK.bin",
            upgrade_version_number="70.250.97",
            downgrade_version_number="70.250.96",
            installation_time=300
        ),
        '130': Transceiver(
            transceiver_type='Sian2',
            last_release_path=f"TODO",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Sian2/",
            upgrade_version_name="fw_130_245_0000_dev_signed_SIAN2_DK.bin",
            downgrade_version_name="fw_130_245_0000_dev_signed_SIAN2_DK.bin",
            upgrade_version_number="130.245.0",
            downgrade_version_number="130.245.0",
            installation_time=480
        ),
        '46': Transceiver(
            transceiver_type='Bagheera',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}46_Bagheera1_2/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Bagheera/",
            upgrade_version_name="fw_46_230_00018_dev_signed.bin",
            downgrade_version_name="fw_46_230_00014_dev_signed.bin",
            upgrade_version_number="46.230.18",
            downgrade_version_number="46.230.14",
            installation_time=270
        ),
        '47': Transceiver(
            transceiver_type='Louie',
            last_release_path=f"{TRANSCEIVERS_FIRMWARES_PATH}47_Louie1_4/{TRANSCEIVERS_RELEASE}",
            test_versions_path=f"{TRANSCEIVERS_APPROVED_FIRMWARES_PATH}Louie/",
            upgrade_version_name="fw_47_230_01018_dev_signed.bin",
            downgrade_version_name="fw_47_230_01014_dev_signed.bin",
            upgrade_version_number="47.230.18",
            downgrade_version_number="47.230.14",
            installation_time=60
        )
    }
