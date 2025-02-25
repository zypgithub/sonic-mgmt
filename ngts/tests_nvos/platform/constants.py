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
        TRANSCEIVERS_ELS: ['channel', 'diagnostics-status', 'dp-fw-fault', 'error-status', 'fault-condition',
                           'fw-version', 'identifier', 'mod-fw-fault', 'oe-mapping', 'port-mapping', 'status',
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
        'els1': ['sw1p1', 'sw1p2', 'sw2p1', 'sw2p2', 'sw3p1', 'sw3p2', 'sw4p1', 'sw4p2'],
        'els2': ['sw5p1', 'sw5p2', 'sw6p1', 'sw6p2', 'sw7p1', 'sw7p2', 'sw8p1', 'sw8p2'],
        'els3': ['sw9p1', 'sw9p2', 'sw10p1', 'sw10p2', 'sw11p1', 'sw11p2', 'sw12p1', 'sw12p2'],
        'els4': ['sw13p1', 'sw13p2', 'sw14p1', 'sw14p2', 'sw15p1', 'sw15p2', 'sw16p1', 'sw16p2'],
        'els5': ['sw17p1', 'sw17p2', 'sw18p1', 'sw18p2', 'sw19p1', 'sw19p2', 'sw20p1', 'sw20p2'],
        'els6': ['sw21p1', 'sw21p2', 'sw22p1', 'sw22p2', 'sw23p1', 'sw23p2', 'sw24p1', 'sw24p2'],
        'els7': ['sw25p1', 'sw25p2', 'sw26p1', 'sw26p2', 'sw27p1', 'sw27p2', 'sw28p1', 'sw28p2'],
        'els8': ['sw29p1', 'sw29p2', 'sw30p1', 'sw30p2', 'sw31p1', 'sw31p2', 'sw32p1', 'sw32p2'],
        'els9': ['sw33p1', 'sw33p2', 'sw34p1', 'sw34p2', 'sw35p1', 'sw35p2', 'sw36p1', 'sw36p2'],
        'els10': ['sw37p1', 'sw37p2', 'sw38p1', 'sw38p2', 'sw39p1', 'sw39p2', 'sw40p1', 'sw40p2'],
        'els11': ['sw41p1', 'sw41p2', 'sw42p1', 'sw42p2', 'sw43p1', 'sw43p2', 'sw44p1', 'sw44p2'],
        'els12': ['sw45p1', 'sw45p2', 'sw46p1', 'sw46p2', 'sw47p1', 'sw47p2', 'sw48p1', 'sw48p2'],
        'els13': ['sw49p1', 'sw49p2', 'sw50p1', 'sw50p2', 'sw51p1', 'sw51p2', 'sw52p1', 'sw52p2'],
        'els14': ['sw53p1', 'sw53p2', 'sw54p1', 'sw54p2', 'sw55p1', 'sw55p2', 'sw56p1', 'sw56p2'],
        'els15': ['sw57p1', 'sw57p2', 'sw58p1', 'sw58p2', 'sw59p1', 'sw59p2', 'sw60p1', 'sw60p2'],
        'els16': ['sw61p1', 'sw61p2', 'sw62p1', 'sw62p2', 'sw63p1', 'sw63p2', 'sw64p1', 'sw64p2'],
        'els17': ['sw65p1', 'sw65p2', 'sw66p1', 'sw66p2', 'sw67p1', 'sw67p2', 'sw68p1', 'sw68p2'],
        'els18': ['sw69p1', 'sw69p2', 'sw70p1', 'sw70p2', 'sw71p1', 'sw71p2', 'sw72p1', 'sw72p2']
    }
    TRANSCEIVERS_ELS_OE_MAPPING = {
        'els1': ['oe1', 'oe19', 'oe37', 'oe55'], 'els2': ['oe2', 'oe20', 'oe38', 'oe56'],
        'els3': ['oe3', 'oe21', 'oe39', 'oe57'], 'els2': ['oe4', 'oe22', 'oe40', 'oe58'],
        'els5': ['oe5', 'oe23', 'oe41', 'oe59'], 'els2': ['oe6', 'oe24', 'oe42', 'oe60'],
        'els7': ['oe7', 'oe25', 'oe43', 'oe61'], 'els2': ['oe8', 'oe26', 'oe44', 'oe62'],
        'els9': ['oe9', 'oe27', 'oe45', 'oe63'], 'els2': ['oe10', 'oe28', 'oe46', 'oe64'],
        'els11': ['oe11', 'oe29', 'oe47', 'oe65'], 'els2': ['oe12', 'oe30', 'oe48', 'oe66'],
        'els13': ['oe13', 'oe31', 'oe49', 'oe67'], 'els2': ['oe14', 'oe32', 'oe50', 'oe68'],
        'els15': ['oe15', 'oe33', 'oe51', 'oe69'], 'els2': ['oe16', 'oe34', 'oe52', 'oe70'],
        'els17': ['oe17', 'oe35', 'oe53', 'oe71'], 'els2': ['oe18', 'oe36', 'oe54', 'oe72']
    }
    TRANSCEIVERS_DETAILS = {  # TODO [L.A] Add Taipan transceiver when known
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
            upgrade_version_name="fw_70_220_01073_dev_signed_WOLVERINE_DK.bin",
            downgrade_version_name="fw_70_220_01070_dev_signed_WOLVERINE_DK.bin",
            upgrade_version_number="70.220.1073",
            downgrade_version_number="70.220.1070",
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
            upgrade_version_name="",
            downgrade_version_name="",
            upgrade_version_number="",
            downgrade_version_number="",
            installation_time=90
        )
    }
