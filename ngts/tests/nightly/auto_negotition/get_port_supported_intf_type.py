import sys
import errno
import os
from python_sdk_api.sx_api import *
from python_sdk_api.sxd_api import *
import logging

logger = logging.getLogger(__name__)


def redirect_stdout():
    sys.stdout.flush()
    stdout_bak = os.dup(1)
    devnull = os.open('/dev/null', os.O_WRONLY)
    os.dup2(devnull, 1)
    os.close(devnull)
    return stdout_bak


def init():
    old_stdout = redirect_stdout()
    rc, handle = sx_api_open(None)
    sys.stdout = os.fdopen(old_stdout, 'w')
    if (rc != SX_STATUS_SUCCESS):
        print("Failed to open api handle.\nPlease check that SDK is running.")
        sys.exit(errno.EACCES)
    return handle


def deinit(handle):
    sx_api_close(handle)


def is_port_mapped(handle, port_attributes, log_port):
    return (
        port_attributes.port_mapping.mapping_mode and
        is_port_swid_bound(handle, log_port)
    )


def is_port_swid_bound(handle, log_port):
    swid_p = new_sx_swid_t_p()
    rc = sx_api_port_swid_bind_get(handle, log_port, swid_p)
    return rc == SX_STATUS_SUCCESS


def print_all_object_attributes(obj, obj_name="Object", indent=0, max_depth=5):
    """Print all non-private, non-callable attributes of an object recursively"""
    prefix = "  " * indent
    if indent == 0:
        print(f"\n{obj_name} Attributes:")
        print("=" * 70)
    for attr in dir(obj):
        if not attr.startswith('_') and attr not in ['this', 'thisown']:  # Skip SWIG internals
            try:
                value = getattr(obj, attr)
                if not callable(value):  # Skip methods
                    value_str = str(value)
                    is_swig_object = 'Swig Object' in value_str or 'proxy of' in value_str
                    if is_swig_object and indent < max_depth:
                        print(f"{prefix}{attr}:")
                        print_all_object_attributes(value, attr, indent + 1, max_depth)
                    else:
                        print(f"{prefix}{attr}: {value}")
            except Exception as e:
                print(f"{prefix}{attr}: <error accessing: {e}>")
    if indent == 0:
        print("=" * 70)


def get_lable_port_log_port_map(handle):
    lable_port_log_port_map = {}
    port_cnt_p = new_uint32_t_p()
    uint32_t_p_assign(port_cnt_p, 0)
    port_attributes_list = new_sx_port_attributes_t_arr(0)
    rc = sx_api_port_device_get(handle, 1, 253, port_attributes_list, port_cnt_p)
    if rc != SX_STATUS_SUCCESS:
        print("sx_api_port_device_get failed, rc = %d" % (rc))
        sys.exit(rc)
    port_cnt = uint32_t_p_value(port_cnt_p)
    port_attributes_list = new_sx_port_attributes_t_arr(port_cnt)
    rc = sx_api_port_device_get(handle, 1, 253, port_attributes_list, port_cnt_p)
    if (rc != SX_STATUS_SUCCESS):
        print("sx_api_port_device_get failed, rc = %d")
        sys.exit(rc)
    port_attributes_dict = {}
    for i in range(0, port_cnt):
        port_attributes = sx_port_attributes_t_arr_getitem(port_attributes_list, i)
        port_attributes_dict[port_attributes.log_port] = port_attributes
        if is_port_mapped(handle, port_attributes, port_attributes.log_port):
            module_port = port_attributes.port_mapping.module_port + 1
            lable_port_log_port_map[module_port] = port_attributes.log_port
    return lable_port_log_port_map, port_attributes_dict


def get_port_capability(handle, log_port, port_attributes):
    admin_sx_port_rate_bitmask_t = new_sx_port_rate_bitmask_t_p()
    cap_sx_port_rate_bitmask_t = new_sx_port_rate_bitmask_t_p()
    sx_port_phy_module_type_bitmask_t = new_sx_port_phy_module_type_bitmask_t_p()
    rc = sx_api_port_rate_capability_get(handle, log_port, admin_sx_port_rate_bitmask_t, cap_sx_port_rate_bitmask_t,
                                         sx_port_phy_module_type_bitmask_t)
    if rc != SX_STATUS_SUCCESS:
        print("sx_api_port_rate_capability_get failed, rc = %d" % (rc))
        print_all_object_attributes(port_attributes, "port_attributes")
        sys.exit(rc)
    remote_capability = sx_port_rate_bitmask_t_p_value(cap_sx_port_rate_bitmask_t)

    potential_intf_type_supported_rate = {
        "CR": ["rate_100M", "rate_1G", "rate_10G", "rate_25G", "rate_50Gx1", "rate_100Gx1"],
        "CR2": ["rate_50Gx2", "rate_100Gx2", "rate_200Gx2"],
        "CR4": ["rate_40G", "rate_100Gx4", "rate_200Gx4", "rate_400Gx4"],
        "CR8": ["rate_400Gx8", "rate_800Gx8"]
    }
    intf_type_supported_rate = {}
    for intf_type, rate_list in potential_intf_type_supported_rate.items():
        for rate in rate_list:
            if getattr(remote_capability, rate):
                if intf_type not in intf_type_supported_rate:
                    intf_type_supported_rate[intf_type] = []
                rate = rate.split("_")[1].split("x")[0]
                intf_type_supported_rate[intf_type].append(rate)
    return intf_type_supported_rate


def get_ports_cap_map():
    handle = init()
    port_cap_map = {}
    lable_port_log_port_map, port_attributes_dict = get_lable_port_log_port_map(handle)
    for lable_port, log_port in lable_port_log_port_map.items():
        logger.info(f"Get port capability: lable_port: {lable_port}, log_port: {log_port}")
        port_cap_map[str(lable_port)] = get_port_capability(handle, int(log_port), port_attributes_dict[log_port])

    deinit(handle)
    print(port_cap_map)


if __name__ == "__main__":
    get_ports_cap_map()
