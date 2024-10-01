class FactoryResetType:
    NO_PARAMS = 'NoParams'
    KEEP_BASIC = 'KeepBasic'
    KEEP_ALL_CONFIG = 'KeepAllConfig'
    KEEP_ONLY_FILES = 'KeepOnlyFiles'
    ALL_TYPES = [NO_PARAMS, KEEP_BASIC, KEEP_ALL_CONFIG, KEEP_ONLY_FILES]


FACTORY_RESET_TYPE_TO_ACTION_PARAM = {
    FactoryResetType.NO_PARAMS: '',
    FactoryResetType.KEEP_BASIC: 'keep basic',
    FactoryResetType.KEEP_ALL_CONFIG: 'keep all-config',
    FactoryResetType.KEEP_ONLY_FILES: 'keep only-files',
}
