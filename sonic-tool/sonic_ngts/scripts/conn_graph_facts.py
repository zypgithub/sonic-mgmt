#!/usr/bin/python

import logging
import sys
import os
sys.path.append('{}/../ansible/library'.format(os.path.abspath(os.curdir)))
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.debug_utils import config_module_logging
from ansible.module_utils import conn_graph_facts_community
from retry.api import retry_call
from minigraph_facts import get_config_db_json_from_hostname, get_dut_ports

config_module_logging('conn_graph_facts')
logger = logging.getLogger(__name__)
SONIC_SSH_PORT = 22

def add_device_conn_info(device_facts, hostname, port=SONIC_SSH_PORT):
    """
    Add device connection information to the device facts.

    Args:
        device_facts (dict): The existing device facts.
        hostname (str): The hostname of the device.

    Returns:
        dict: Updated device facts with connection information.
    """
    logs = []
    logs.append('Getting conn_facts')
    config_db = retry_call(get_config_db_json_from_hostname, fargs=[hostname, logs, port], tries=5, delay=6, logger=None)
    all_dut_ports = get_dut_ports(config_db, logs)
    for port_name in all_dut_ports.keys():
        speed = config_db['PORT'][port_name]['speed']
        port_info_dict = {port_name: {'peerdevice': 'stub_device', 'speed': speed, 'peerport': 'stub_port'}}
        device_facts['ansible_facts']['device_conn'][hostname].update(port_info_dict)

    return device_facts

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=False),
            hosts=dict(required=False, type='list'),
            filepath=dict(required=False),
            group=dict(required=False),
            anchor=dict(required=False, type='list'),
            ignore_errors=dict(required=False, type='bool', default=False),
            ansible_port=dict(required=False, type='int', default=SONIC_SSH_PORT),
        ),
        mutually_exclusive=[['host', 'hosts', 'anchor']],
        supports_check_mode=True
    )

    try:
        # Call the ansible module conn_graph_facts_community
        results = conn_graph_facts_community.main()
        logger.debug("The conn graph facts is: {}".format(results))

        if results:
            logger.debug("Start to add device_conn info for host {}".format(module.params.get('hosts')))
            for host in module.params.get('hosts'):
                results = add_device_conn_info(results, host, module.params.get('ansible_port'))
            logger.debug("The conn graph facts after adding device_conn info is: {}".format(results))
            module.exit_json(**results)
        else:
            module.fail_json(msg="Failed to retrieve conn graph facts")

    except Exception as e:
        logger.exception("Error executing conn_graph_facts_community module")
        module.fail_json(msg="Error executing conn_graph_facts_community module: {}".format(str(e)))

if __name__ == '__main__':
    main()
