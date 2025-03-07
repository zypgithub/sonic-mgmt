import argparse
import re
import sys
import argparse
from python_sdk_api.sx_api import *

sys.path.append("/usr/bin")


def getLogport(handle, port='swp1s0'):
    """
    Retrieves the logical port number for a given physical port (swpXsY).
    :param handle: Handle to the switch API.
    :param port: Physical port (e.g., 'swp1s2').
    :return: Logical port number.
    """

    # Extract module and split information from the port name
    match = re.match(r'swp(\d)s*(\d*)', port)
    if match:
        module = int(match.group(1))
        split = int(match.group(2) or 0)  # Default to 0 if there's no split part
    else:
        print(f"Warning: Port {port} doesn't match the expected pattern (swpXsY). Using default values.")
        module = 1
        split = 0

    # Initialize port count and attributes list pointers
    port_cnt_p = new_uint32_t_p()
    uint32_t_p_assign(port_cnt_p, 0)
    port_attributes_list = new_sx_port_attributes_t_arr(0)

    # First, get the number of ports
    rc = sx_api_port_device_get(handle, 1, 253, port_attributes_list, port_cnt_p)
    if rc != SX_STATUS_SUCCESS:
        print(f"Error: Failed to get PORT device count (rc = {rc}).")
        return -1

    port_cnt = uint32_t_p_value(port_cnt_p)

    # Now, allocate memory for the port attributes and get the list
    port_attributes_list = new_sx_port_attributes_t_arr(port_cnt)
    rc = sx_api_port_device_get(handle, 1, 253, port_attributes_list, port_cnt_p)
    if rc != SX_STATUS_SUCCESS:
        print(f"Error: Failed to get PORT device attributes (rc = {rc}).")
        return -1

    # Iterate through the attributes to find the logical port number based on module and split
    last_module_port = 0
    split_count = 0
    log_port = -1  # Default value

    for i in range(0, port_cnt):
        port_attributes = sx_port_attributes_t_arr_getitem(port_attributes_list, i)
        if port_attributes.port_mapping.mapping_mode == 1:
            module_port = port_attributes.port_mapping.module_port + 1
            if last_module_port == module_port:
                split_count += 1
            else:
                split_count = 0
            last_module_port = module_port

            if (module_port == module) and (split_count == split):
                log_port = port_attributes.log_port
                break

    return log_port


def getLogportlist(handle, port_list=[]):
    logport_list = []
    for port in port_list:
        logport_list.append(getLogport(handle, port))
    logport_string = ' '.join(str(x) for x in logport_list)
    return logport_string


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--port", action='store', type=str, help="Port argument to find the log port")
    parser.add_argument("--ports", type=str, nargs='+', help="Physical port list for which we want to find the log ports.")
    args = parser.parse_args()
    handle = 0
    if args.port:
        rc, handle = sx_api_open(None)
        print(getLogport(handle, port=args.port))

    if args.ports:
        rc, handle = sx_api_open(None)
        print(getLogportlist(handle, args.ports))

    if not handle == 0:
        sx_api_close(handle)


if __name__ == '__main__':
    main()
