import copy

ADMIN = 'yormnAnb'
ROOT = 'root'
OPENBMC = '0penBmc'
ADMIN_USER_DEFAULT_PASSWORD = 'ABYX12#14artb51'
BMC_USER_DEFAULT_PASSWORD = OPENBMC
BMC_USER_BACKUP_PASSWORD = 'ABYX12#14artb'

FACTORY_RESET_FLAG = 'factory_reset'

CURL_AUTHORIZATION_ERR_MSGS = ['Authorization Error', 'authorization error', 'Invalid username or password']


class BmcCliCmd:
    factory_reset = 'fw_setenv openbmconce factory-reset'
    check_factory_reset_flag = 'fw_printenv'
    enable_mctp_pcie_ctrl_service = 'systemctl enable mctp-pcie-ctrl ; systemctl start mctp-pcie-ctrl'


class BmcUserInfo:
    def __init__(self, username: str, default_password: str, another_password: str):
        self.username = username
        self.default_password = default_password
        self.another_password = another_password

    def copy(self, deep=False):
        if deep:
            return copy.deepcopy(self)
        else:
            return copy.copy(self)


class BmcUsers:
    root = BmcUserInfo(ROOT, BMC_USER_DEFAULT_PASSWORD, BMC_USER_BACKUP_PASSWORD)
    admin = BmcUserInfo(ADMIN, ADMIN_USER_DEFAULT_PASSWORD, BMC_USER_BACKUP_PASSWORD)
