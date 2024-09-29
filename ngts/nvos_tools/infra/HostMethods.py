import logging
import time

from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli

logger = logging.getLogger()


class HostMethods:

    @staticmethod
    def host_snmp_get(host_engine, ip_address, community='qwerty12', port='', get_param='sysName.0'):
        with allure_step("Running snmpget command"):
            return host_engine.run_cmd('snmpget -v 2c -c {0} {1}{2} {3}'.format(community, ip_address, port, get_param))

    @staticmethod
    def host_snmp_walk(host_engine, ip_address, community='qwerty12', mib='', param=''):
        with allure_step("Running snmpwalk command"):
            return host_engine.run_cmd('snmpwalk -v 1 -c {0} {1} {2}'.format(community, ip_address, param))

    @staticmethod
    def host_ip_address_set(host_engine, ip_address, interface):
        with allure_step("Set ip address on host"):
            return host_engine.run_cmd('sudo ip addr add {0} dev {1}'.format(ip_address, interface))

    @staticmethod
    def host_ip_address_unset(host_engine, ip_address, interface):
        with allure_step("Unset ip address on host"):
            return host_engine.run_cmd('sudo ip addr del {0} dev {1}'.format(ip_address, interface))

    @staticmethod
    def host_ping(host_engine, ip_address, interface, count=5):
        with allure_step("Running ping from host"):
            return host_engine.run_cmd('ping -I {0} {1} -c {2}'.format(interface, ip_address, count))

    @staticmethod
    def start_snmp_server(engine, state, readonly_community, listening_address):
        system = System(None)
        system.snmp_server.set('state', state).verify_result()
        system.snmp_server.set('readonly-community', readonly_community).verify_result()
        system.snmp_server.set('listening-address', listening_address).verify_result()
        NvueGeneralCli.apply_config(engine)
        logging.info("Snmp enabled successfully")

    @staticmethod
    def wait_for_snmp_is_running(system, state=SystemConsts.SNMP_ENABLED_STATE, tries=5, timeout=2):
        for _ in range(tries):
            system_snmp_output = OutputParsingTool.parse_json_str_to_dictionary(system.snmp_server.show()) \
                .get_returned_value()
            if state in system_snmp_output[SystemConsts.SNMP_STATE]:
                break
            elif state not in system_snmp_output[SystemConsts.SNMP_STATE]:
                time.sleep(timeout)
                continue
            else:
                assert 'SNMP is not in {} state'.format(state)
