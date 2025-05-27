
SONIC_MARS_BASE_PATH = "/.autodirect/sw_regression/system/SONIC/MARS"

SONIC_MGMT_DEVICE_ID = "SONIC_MGMT"
NGTS_PATH_PYTEST = "/ngts_venv/bin/pytest"
NGTS_PATH_PYTHON = "/ngts_venv/bin/python"
TEST_SERVER_DEVICE_ID = "TEST_SERVER"
NGTS_DEVICE_ID = "NGTS"
DUT_DEVICE_ID = "DUT"
FANOUT_DEVICE_ID = "FANOUT"
SONIC_MGMT_DIR = '/root/mars/workspace/sonic-mgmt/'
UPDATED_FW_TAR_PATH = 'tests/platform_tests/fwutil/firmware.json'
HTTP_SERVER_NBU_NFS = 'http://nbu-mtr-nfs.nvidia.com'

DOCKER_SONIC_MGMT_IMAGE_NAME = "docker-sonic-mgmt"
DOCKER_NGTS_IMAGE_NAME = "docker-ngts"

SONIC_MGMT_REPO_URL = "http://10.7.77.140:8080/switchx/sonic/sonic-mgmt"
SONIC_MGMT_MOUNTPOINTS = {
    '/.autodirect/mswg/projects': '/.autodirect/mswg/projects',
    '/auto/sw_system_project': '/auto/sw_system_project',
    '/auto/sw_system_release': '/auto/sw_system_release',
    '/.autodirect/sw_system_release/': '/.autodirect/sw_system_release/',
    '/auto/sw_regression/system/SONIC/MARS': '/auto/sw_regression/system/SONIC/MARS',
    '/.autodirect/sw_regression/system/SONIC/MARS': '/.autodirect/sw_regression/system/SONIC/MARS',
    '/workspace': '/workspace',
    '/.autodirect/LIT/SCRIPTS': '/.autodirect/LIT/SCRIPTS',
    '/auto/sw_regression/system/NVOS/MARS': '/auto/sw_regression/system/NVOS/MARS',
    '/.autodirect/sw_regression/system/NVOS/MARS': '/.autodirect/sw_regression/system/NVOS/MARS',
    '/.autodirect/sysgwork/G/MARS_conf/stm_nvos/': '/.autodirect/sysgwork/G/MARS_conf/stm_nvos/',
    '/etc/localtime': '/etc/localtime',
    '/auto/sw_tools/Internal/BugHandling/RELEASES': '/auto/sw_tools/Internal/BugHandling/RELEASES',
    "/.autodirect/LIT/LOGS/RR": "/.autodirect/LIT/LOGS/RR",
    '/.autodirect/sw/release/': '/.autodirect/sw/release/',
    '/auto/sw/tools/comet/': '/auto/sw/tools/comet/',
    '/auto/sw/projects/performance/results/mongodb/': '/auto/sw/projects/performance/results/mongodb/',
    '/auto/LIT/SCRIPTS/': '/auto/LIT/SCRIPTS/',
}

SONIC_MGMT_MOUNTPOINTS_MTBC = {
    '/auto/sw_regression/mtbcsw/system/SONIC/MARS': '/auto/sw_regression/mtbcsw/system/SONIC/MARS',
    '/.autodirect/sw_regression/mtbcsw/system/SONIC/MARS': '/.autodirect/sw_regression/mtbcsw/system/SONIC/MARS'
}
MTBC_SERVER_LIST = ['dev-r730-01', '10.75.206.120', 'dev-r730-02', '10.75.207.40', 'dev-r730-03', '10.75.207.5', 'mtbc-r730-04', '10.75.205.21']
MTL_NVOS_SERVER_LIST = ['10.237.116.60']
MTL_NVOS_MOUNTPOINTS = {'/auto/sw/tools/comet/nvos': '/auto/sw/tools/comet/nvos'}
VER_SDK_PATH = "/opt/ver_sdk"
EXTRA_PACKAGE_PATH_LIST = ["/usr/lib64/python2.7/site-packages"]

TOPO_ARRAY = ("t0", "t1-lag", "ptf32", "t0-64", "t0-64-256", "t0-c256", "t0-isolated-d2u254s1", "t1-lag-c224o8", "t1-32-lag", "t1-64-lag", "t1-isolated-d254u2s1", "t0-56", "t0-56-po2vlan", "t0-56-o8v48", "t1-isolated-d28u1", "t1-isolated-d224u8", "t0-isolated-d128u128s1", "t0-isolated-d16u16s1", "t0-isolated-d16u16s2")
REBOOT_TYPES = {
    "reboot": "reboot",
    "fast-reboot": "fast-reboot",
    "warm-reboot": "warm-reboot"
}

DOCKER_REGISTRY = "nbu-harbor.gtm.nvidia.com"

DUT_LOG_BACKUP_PATH = "/.autodirect/sw_system_project/sonic/dut_logs"

BRANCH_PTF_MAPPING = {'master': 'latest',
                      '202012': '42007',
                      '202106': '42007'
                      }
