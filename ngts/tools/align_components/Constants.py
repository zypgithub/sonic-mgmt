class RedfishCollection:
    MANAGERS = "redfish/v1/Managers"
    SYSTEM = "redfish/v1/Systems"
    TASK_SERVICE = "redfish/v1/TaskService/Tasks"
    UPDATE_SERVICE = "redfish/v1/UpdateService"
    SESSION_SERVICE = "redfish/v1/SessionService"
    FIRMWARE_INVENTORY = "redfish/v1/UpdateService/FirmwareInventory"
    SYSTEM_ACTIONS = f"{SYSTEM}/System_0/Actions"
    RESET = f"{SYSTEM_ACTIONS}/ComputerSystem.Reset"


class Defaults:
    DEFAULT_SWITCH_USERNAME = 'admin'
    DEFAULT_SWITCH_PASSWORD = 'admin'
    DEFAULT_BMC_USER = 'root'
    DEFAULT_BMC_PASSWORD = 'ABYX12#14artb'
    DEFAULT_BRANCH_NAME = 'develop'
    CPLD_NAME = 'cpld'
    BMC_NAME = 'bmc'
    BIOS_NAME = 'bios'
    FPGA_NAME = 'fpga'
    FPGA_ENCRYPTED_NAME = 'fpga_encrypted'
    EROT_NAME = 'erot'
    PLDM_NAME = 'pldm'


class NogaConstants:
    """
    NogaConstants class
    """
    RELATIONS = "relations"
    HAS_A = "has a"
    TYPE_TITLE = "TYPE_TITLE"
    NAME = "NAME"
    ATTRIBUTES = 'attributes'
    BMC_IP = 'bmc_ip'
    REMOTE_REBOOT = 'remote_reboot'
    SPECIFIC = 'Specific'
    BIOS_VERSION = 'bios_version'
    HARDWARE_COMPONENTS = 'Hardware Components'
    COMMON = 'Common'
    SWITCH = 'Switch'
