import os
import pytest
import logging
import json

from ngts.constants.constants import DbConstants, CliType, RebootTestConstants
from ngts.tools.infra import get_infra_type, CANONICAL_INFRA_TYPE
from infra.tools.sql.connect_to_mssql import ConnectMSSQL
from infra.tools.sql.skynet_collector import SkynetGenericCollector

logger = logging.getLogger()


@pytest.fixture(autouse=True)
def collect_tests_data_to_sql(request):
    skynet_run = False
    setup_name = ''
    if hasattr(request.config.option, 'skynet'):
        skynet_run = request.config.getoption("skynet")
    if hasattr(request.config.option, 'setup_name'):
        setup_name = request.config.getoption('setup_name')
    if skynet_run:
        cpu_ram_usage_collector = SkynetNvosCpuRamUsageCollector if "NVOS" in setup_name else SkynetSonicCpuRamUsageCollector
    else:
        cpu_ram_usage_collector = NgtsCpuRamUsageCollector
    pytest_node_ids_which_should_be_collected = {
        'tests/push_build_tests/system/test_reboot_reload.py::test_push_gate_reboot_policer': NgtsPushGateRebootLossTimeCollector,
        'tests/push_build_tests/system/test_cpu_ram_hdd_usage.py::TestCpuRamHddUsage::test_cpu_usage': cpu_ram_usage_collector,
        'tests/push_build_tests/system/test_cpu_ram_hdd_usage.py::TestCpuRamHddUsage::test_ram_usage': cpu_ram_usage_collector,
        'tests_nvos/skynet/test_cpu_ram_hdd_usage.py::TestCpuRamHddUsage::test_cpu_usage': cpu_ram_usage_collector,
        'tests_nvos/skynet/test_cpu_ram_hdd_usage.py::TestCpuRamHddUsage::test_ram_usage': cpu_ram_usage_collector,
        'tests/push_build_tests/system/test_startup_time_degradation.py::TestStartupTime::test_startup_time_degradation': StartupTimeCollector,
        'platform_tests/test_advanced_reboot.py::test_fast_reboot': AdvancedRebootCollector,
        'platform_tests/test_advanced_reboot.py::test_warm_reboot': AdvancedRebootCollector,
        'upgrade_path/test_upgrade_path.py::test_upgrade_path': UpgradePathCollector
    }

    yield
    for test_prefix in pytest_node_ids_which_should_be_collected.keys():
        if test_prefix in request.node.nodeid:
            try:
                data_collector = pytest_node_ids_which_should_be_collected[test_prefix](request)
                data_collector.update_database_with_test_results()
            except Exception as err:
                logger.error('Unable to upload test: %s results to SQL DB. Got error: %s', request.node.nodeid, err)
            break


class SonicDataCollector(object):
    """
    Basic class from which all other collector classes will be inherited
    """

    def __init__(self, request):

        self.request = request
        self.test_name = self.request.node.nodeid
        self.is_canonical_setup = get_infra_type(self.request) == CANONICAL_INFRA_TYPE
        connections_params = DbConstants.CREDENTIALS[CliType.SONIC]
        self.mssql_connection_obj = ConnectMSSQL(connections_params['server'], connections_params['database'],
                                                 connections_params['username'], connections_params['password'])
        self.mssql_connection_obj.connect_db()

        self.setup_name = None
        self.topology = None
        self.dut_engine = None
        self.sonic_branch = None
        self.sonic_version = None
        self.hwsku = None
        self.platform = None
        self.mars_session_id = self.request.session.config.option.session_id
        self.mars_key_id = self.request.session.config.option.mars_key_id
        self.get_general_setup_info()
        self.get_dut_engine()
        self.get_sonic_image_info()
        self.setup_extra_info = {'hwsku': self.hwsku}
        self.test_data = None

    def get_dut_engine(self):
        if self.is_canonical_setup:
            self.dut_engine = self.request.getfixturevalue('engines')['dut']
        else:
            self.dut_engine = self.request.getfixturevalue('duthost')

    def get_sonic_image_info(self):
        if self.is_canonical_setup:
            self.sonic_branch = self.request.getfixturevalue('sonic_branch')
            self.sonic_version = self.request.getfixturevalue('sonic_version')
            self.hwsku = self.request.getfixturevalue('platform_params').hwsku
            self.platform = self.request.getfixturevalue('platform_params').platform
        else:
            sonic_branch = self.dut_engine.sonic_release
            if sonic_branch == 'none':
                sonic_branch = 'master'
            self.sonic_branch = sonic_branch
            self.sonic_version = self.dut_engine.os_version
            self.hwsku = self.dut_engine.facts['hwsku']
            self.platform = self.dut_engine.facts['platform']

    def get_general_setup_info(self):
        if self.is_canonical_setup:
            self.setup_name = self.request.config.option.setup_name
            self.topology = 'ptf-any'
        else:
            self.setup_name = self.request.config.option.ansible_host_pattern
            testbed = self.request.config.option.testbed
            self.topology = testbed.split(self.setup_name)[-1].lstrip('-')  # example: get t0 from: 'arc-switch1004-t0'

    def update_database_with_test_results(self):

        if 'simx' in self.platform:
            logger.info('Test results data for uploading into SQL database will not be collected for SIMX setup')
            return

        self.get_test_results()

        if self.test_data:
            test_results = {'TestName': self.test_name,
                            'DUTImageVersion': self.sonic_version, 'DUTImageBranch': self.sonic_branch,
                            'Topology': self.topology, 'SetupName': self.setup_name,
                            'MarsSessionId': self.mars_session_id, 'MarsKeyId': self.mars_key_id,
                            'ExtraInfo': self.setup_extra_info, 'TestData': self.test_data}
            logger.info('Going to upload to SQL DB next data: \n{}\n'.format(test_results))

            test_id = self.get_test_id_from_db()
            test_setup_id = self.get_test_setup_id_from_db()
            test_run_id = self.insert_data_into_test_runs_table(test_id)
            self.insert_data_into_rel_test_run_setup_table(test_setup_id, test_run_id)
            self.insert_data_into_test_data_table(test_run_id)

        else:
            logger.warning('Can not get test data to upload into SQL database')

    def get_test_id_from_db(self):
        """
        Get test_id from SQL table "test"
        :return: test_id
        """
        query_get = "SELECT test_id FROM test WHERE test_name='{}'".format(self.test_name)
        self.mssql_connection_obj.cursor.execute(query_get)
        result_id = self.mssql_connection_obj.cursor.fetchone()
        if result_id:
            test_id = result_id[0]
        else:
            query = "INSERT into test (test_name) values('{}')".format(self.test_name)
            test_id = self.mssql_connection_obj.query_insert(query, query_get)
        return test_id

    def get_test_setup_id_from_db(self):
        """
        Get test_setup_id from SQL table tests_setup
        :return: test_setup_id
        """
        query_get = "SELECT test_setup_id FROM tests_setup WHERE setup_name='{}'".format(self.setup_name)
        self.mssql_connection_obj.cursor.execute(query_get)
        result_id = self.mssql_connection_obj.cursor.fetchone()
        if result_id:
            test_setup_id = result_id[0]
        else:
            query = "INSERT into tests_setup (setup_name) values('{}')".format(self.setup_name)
            test_setup_id = self.mssql_connection_obj.query_insert(query, query_get)
        return test_setup_id

    def insert_data_into_test_runs_table(self, test_id):
        """
        Insert data into tests_runs table
        :param test_id: SQL table test ID
        :return: test_run_id
        """
        query = "INSERT tests_runs (test_run_dateTime, DUTImageVersion,DUTImageBranch,test_id,Topology,MarsSessionId,MarsKeyId) " \
            "values (GETDATE(), '{DUTImageVersion}', '{DUTImageBranch}', {test_name_id}, '{Topology}', '{MarsSessionId}', '{MarsKeyId}')".format(
                DUTImageVersion=self.sonic_version,
                DUTImageBranch=self.sonic_branch,
                test_name_id=test_id,
                Topology=self.topology,
                MarsSessionId=self.mars_session_id,
                MarsKeyId=self.mars_key_id
            )
        self.mssql_connection_obj.query_insert(query)

        query = "SELECT SCOPE_IDENTITY() AS [SCOPE_IDENTITY]"
        self.mssql_connection_obj.cursor.execute(query)
        test_run_id = self.mssql_connection_obj.cursor.fetchone()[0]
        return test_run_id

    def insert_data_into_rel_test_run_setup_table(self, test_setup_id, test_run_id):
        """
        Insert data into rel_test_run_setup table
        :param test_setup_id: SQL table test setup ID
        :param test_run_id: SQL table test run ID
        """
        query = "INSERT rel_test_run_setup (test_setup_id,test_run_id,SetupExtraInfo) " \
            "values({setup_name_id}, {test_run_id}, '{SetupExtraInfo}')".format(
                setup_name_id=test_setup_id,
                test_run_id=test_run_id,
                SetupExtraInfo=json.dumps(self.setup_extra_info)
            )
        self.mssql_connection_obj.query_insert(query)

    def insert_data_into_test_data_table(self, test_run_id):
        """
        Insert data into test_data table
        :param test_run_id:  SQL table test run ID
        """
        for key, value in self.test_data.items():
            query = "INSERT test_data (test_run_id, test_attribute, test_attribute_value) values({}, '{}', {})".format(
                test_run_id, key, value)
            self.mssql_connection_obj.query_insert(query)

    def get_test_results(self):
        raise NotImplementedError('This method must be implemented in child class')


class NgtsPushGateRebootLossTimeCollector(SonicDataCollector):
    """
    Class which collects dataplane and controlplane loss for NGTS PushGate reboot test case
    """

    def __init__(self, request):
        super(NgtsPushGateRebootLossTimeCollector, self).__init__(request)

    def get_test_results(self):
        reboot_result_dict = {}
        validation_type = self.request.node.funcargs['validation_type']
        self.test_name = '{}[{}]'.format(self.test_name, validation_type)

        with open(RebootTestConstants.DATAPLANE_TRAFFIC_RESULTS_FILE) as dataplane:
            dataplane_results = json.load(dataplane)
            reboot_result_dict['dataplane'] = dataplane_results['actual_traffic_loss_time']

        with open(RebootTestConstants.CONTROLPLANE_TRAFFIC_RESULTS_FILE) as controlplane:
            controlplane_results = json.load(controlplane)
            reboot_result_dict['controlplane'] = controlplane_results['actual_traffic_loss_time']

        with open(RebootTestConstants.IFACES_STATUS_FILE) as ports:
            ports_results = json.load(ports)
            self.setup_extra_info['total_ports'] = ports_results['total_ports']
            self.setup_extra_info['active_ports'] = ports_results['active_ports']

        if reboot_result_dict:
            self.test_data = reboot_result_dict


class NgtsCpuRamUsageCollector(SonicDataCollector):
    """
    Class which collects CPU/RAM usage for NGTS PushGate CPU/RAM usage test cases
    """

    def __init__(self, request):
        super(NgtsCpuRamUsageCollector, self).__init__(request)

    def get_test_results(self):

        test_report_filename = os.path.join('/tmp/', self.request.node.originalname)
        with open(test_report_filename) as test_report_file_obj:
            test_report_dict = json.load(test_report_file_obj)
            self.test_data = test_report_dict


class AdvancedRebootCollector(SonicDataCollector):
    """
    Class which collects dataplane and controlplane loss for community AdvancedReboot reboot test case
    """

    def __init__(self, request):
        super(AdvancedRebootCollector, self).__init__(request)

        self.supported_tests_by_collector = ['platform_tests/test_advanced_reboot.py::test_fast_reboot',
                                             'platform_tests/test_advanced_reboot.py::test_warm_reboot']

        self.test_name = self.test_name.split('[')[0]  # Remove hostname ...boot.py::test_fast_reboot[arc-switch1004]
        self.ptfhost_engine = self.request.getfixturevalue('ptfhost')

    def get_ports_info(self):
        config_facts = self.dut_engine.config_facts(host=self.dut_engine.hostname, source="running")['ansible_facts']
        self.setup_extra_info['total_ports'] = len(config_facts.get('PORT', {}))
        active_ports = 0
        for port, port_data in config_facts.get('PORT', {}).items():
            if port_data.get('admin_status') == 'up':
                active_ports += 1
        self.setup_extra_info['active_ports'] = active_ports

    def get_test_results(self):

        if self.test_name not in self.supported_tests_by_collector:
            logger.info('Collecting test data not supported for test case: %s', self.test_name)
            return

        # Get DUT ports
        self.get_ports_info()

        # Get control/data plane loss
        ptf_test_log_path = '/tmp/fast-reboot-report.json'
        if 'warm' in self.test_name:
            ptf_test_log_path = '/tmp/warm-reboot-report.json'
        if 'cold' in self.test_name:
            ptf_test_log_path = '/tmp/cold-reboot-report.json'
        default_loss_value = '-1'
        self.test_data = {'dataplane': default_loss_value, 'controlplane': default_loss_value}

        md5sum_log_file = '/tmp/advanced_reboot_sql_collected.log'
        try:
            md5sum = self.ptfhost_engine.shell('md5sum {}'.format(ptf_test_log_path))['stdout']
            if md5sum in self.ptfhost_engine.shell('cat {}'.format(md5sum_log_file), module_ignore_errors=True)['stdout_lines']:
                raise Exception('Test report file: {} already collected by previous SQL data upload session.'.format(
                    ptf_test_log_path))

            ptf_test_report = self.ptfhost_engine.shell('cat {}'.format(ptf_test_log_path))['stdout']
            ptf_test_report_dict = json.loads(ptf_test_report)
            dataplane_downtime = ptf_test_report_dict['dataplane']['downtime']
            controlplane_downtime = ptf_test_report_dict['controlplane']['downtime']
            lacp_max_downtime = self.get_lacp_max_loss(ptf_test_report_dict)

            # if not able to check dataplane loss or control plane loss - then use '-1' value as default
            if not ptf_test_report_dict['dataplane']['checked_successfully']:
                dataplane_downtime = default_loss_value
            if not controlplane_downtime:
                controlplane_downtime = default_loss_value

            self.test_data = {'dataplane': dataplane_downtime, 'controlplane': controlplane_downtime,
                              'lacp': lacp_max_downtime}

        except Exception as err:
            logger.error('Can not get data/control plane loss for test: {}. Got err: {}'.format(self.test_name, err))
        finally:
            self.ptfhost_engine.shell('md5sum {} >> {}'.format(ptf_test_log_path, md5sum_log_file),
                                      module_ignore_errors=True)

    @staticmethod
    def get_lacp_max_loss(ptf_test_report_dict):
        lacp_sessions = ptf_test_report_dict['controlplane'].get("lacp_sessions", {})
        lacp_values = lacp_sessions.values()
        if lacp_values:
            max_lacp = max(lacp_values)
        else:
            max_lacp = -1
        return max_lacp


class UpgradePathCollector(AdvancedRebootCollector):
    """
    Class which collects dataplane and controlplane loss for community Upgrade Path reboot test case
    """

    def __init__(self, request):
        super(UpgradePathCollector, self).__init__(request)

        self.supported_tests_by_collector = ['upgrade_path/test_upgrade_path.py::test_upgrade_path[fast]',
                                             'upgrade_path/test_upgrade_path.py::test_upgrade_path[warm]',
                                             'upgrade_path/test_upgrade_path.py::test_upgrade_path[cold]']

        reboot_type = self.request.getfixturevalue('upgrade_path_lists')[0]
        self.test_name = '{}[{}]'.format(self.test_name, reboot_type)

        self.get_images_info()

    def get_images_info(self):
        images = self.dut_engine.get_image_info()
        target_ver = images['current']
        if target_ver in images['installed_list']:
            images['installed_list'].remove(target_ver)
        base_ver = images['installed_list'][0]  # supported only one base version
        self.setup_extra_info['base_version'] = base_ver


class StartupTimeCollector(SonicDataCollector):
    """
    Class which collects reboot time for the Canonical test_startup_time_degradation test case
    """
    def __init__(self, request):
        super(StartupTimeCollector, self).__init__(request)

    def get_test_results(self):
        try:
            self.test_data = {'reboot_time': self.request.instance.elapsed_time}

        except Exception as err:
            logger.error("Couldn't get reboot time data for test: {}. Got err: {}".format(self.test_name, err))


class SkynetSonicCpuRamUsageCollector(SkynetGenericCollector):
    """
    Class which collects CPU/RAM usage for Skynet CPU/RAM usage test cases
    """
    def __init__(self, request):
        self.request = request
        setup_name = self.request.getfixturevalue('setup_name')
        project_name = 'sonic'
        sonic_version = self.request.getfixturevalue('sonic_version')
        platform = self.request.getfixturevalue('platform_params').platform
        test_name = self.request.node.nodeid
        topology = 'ptf-any'
        test_rc = 'failed' if self.request.node.rep_call.failed else 'passed'
        super(SkynetSonicCpuRamUsageCollector, self).__init__(setup_name, topology, sonic_version, project_name,
                                                              platform, test_name, test_rc)

    def get_test_results(self):
        test_report_filename = os.path.join('/tmp/', self.request.node.originalname)
        with open(test_report_filename) as test_report_file_obj:
            test_report_dict = json.load(test_report_file_obj)
            self.test_data = test_report_dict


class SkynetNvosCpuRamUsageCollector(SkynetGenericCollector):
    """
    Class which collects CPU/RAM usage for Skynet CPU/RAM usage test cases
    """
    def __init__(self, request):
        self.request = request
        setup_name = self.request.getfixturevalue('setup_name')
        project_name = 'nvos'
        nvos_version = self.request.getfixturevalue('sonic_version')
        platform = self.request.getfixturevalue('platform_params').platform
        test_name = self.request.node.nodeid
        topology = 'ptf-any'
        test_rc = 'failed' if self.request.node.rep_call.failed else 'passed'
        super(SkynetNvosCpuRamUsageCollector, self).__init__(setup_name, topology, nvos_version, project_name,
                                                             platform, test_name, test_rc)

    def get_test_results(self):
        test_report_filename = os.path.join('/tmp/', self.request.node.originalname)
        with open(test_report_filename) as test_report_file_obj:
            test_report_dict = json.load(test_report_file_obj)
            self.test_data = test_report_dict
