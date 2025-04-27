# todo: combine these with the consts at ngts/tests_nvos/system/factory_reset/helpers.py


class FactoryResetType:
    NO_PARAMS = 'NoParams'
    KEEP_BASIC = 'KeepBasic'
    KEEP_ONLY_FILES = 'KeepOnlyFiles'
    KEEP_ALL_CONFIG = 'KeepAllConfig'
    ALL_TYPES = [NO_PARAMS, KEEP_BASIC, KEEP_ONLY_FILES, KEEP_ALL_CONFIG]


FACTORY_RESET_TYPE_TO_ACTION_PARAM = {
    FactoryResetType.NO_PARAMS: '',
    FactoryResetType.KEEP_BASIC: 'keep basic',
    FactoryResetType.KEEP_ALL_CONFIG: 'keep all-config',
    FactoryResetType.KEEP_ONLY_FILES: 'keep only-files',
}
