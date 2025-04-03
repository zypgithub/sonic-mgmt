import os
import sys
import argparse
import json
import logging

workspace_dir = os.environ['WORKSPACE']
sys.path.append(os.path.join(workspace_dir, 'sonic-mgmt'))

from ngts.tools.mars_test_cases_results.Connect_to_MSSQL import ConnectMSSQL
from ngts.constants.constants import DbConstants, CliType

logger = logging.getLogger(__name__)

# Get env variables
fast_reboot_executors = os.environ.get('fast_reboot_executors')
fast_reboot_iterations_number = os.environ.get('fast_reboot_iterations_number', 1)
warm_reboot_executors = os.environ.get('warm_reboot_executors')
warm_reboot_iterations_number = os.environ.get('warm_reboot_iterations_number', 1)
cold_reboot_executors = os.environ.get('cold_reboot_executors')
cold_reboot_iterations_number = os.environ.get('cold_reboot_iterations_number', 1)
base_version = os.environ.get('base_version')
upgrade_testcase = os.environ.get('upgrade_testcase')
case_timeout = 5400
if upgrade_testcase == "test_warm_upgrade_sad_path":
    case_timeout = 42000
fast_base_version = os.environ.get('fast_base_version')
if not fast_base_version:
    fast_base_version = base_version
warm_base_version = os.environ.get('warm_base_version')
if not warm_base_version:
    warm_base_version = base_version
cold_base_version = os.environ.get('cold_base_version')
if not cold_base_version:
    cold_base_version = base_version
target_version = os.environ.get('target_version')
tests_results_file_path = os.path.join(workspace_dir, 'results.json')
email_report_file_path = os.path.join(workspace_dir, 'email_report.html')

REBOOT_TYPES = ['fast', 'warm', 'cold', 'unknown']
FAST_REBOOT_TEST_IDS = [9, 13]  # 9 and 13 - id's for fast-reboot and fast-reboot upgrade tests
COLD_REBOOT_TEST_IDS = [205]
UNKNOWN = 'unknown'

DB_FILE_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<DBDEF>
<global>
    <default_params_type> basic_setup_step_params </default_params_type>
    <DB>
        <info> {test_name} </info>
        <owner> SONiC </owner>
        <group> SONiC </group>
        <pre></pre>
        <post></post>
    </DB>
    <Test>
    </Test>
    <Case>
        <on_not_success>
        <name> Generate sysdump on not success </name>
        <type> setup_mode </type>
        <cmd>
            <type> reg_exec_cmd </type>
            <players_selection>
                <ep_targets> SONIC_MGMT </ep_targets>
            </players_selection>
            <name> run_on_stm </name>
            <tout> 600 </tout>
            <params>
                <exec> PYTHONPATH=/devts/ /ngts_venv/bin/pytest /root/mars/workspace/sonic-mgmt/ngts/scripts/store_techsupport_on_not_success.py --setup_name=[[conf:extra_info.setup_name]] --tech_support_duration=7200 --session_id=[[run_time:session_id]] --rootdir=/root/mars/workspace/sonic-mgmt/ngts -c /root/mars/workspace/sonic-mgmt/ngts/pytest.ini --log-level=INFO --clean-alluredir --alluredir=/tmp/allure-results</exec>
            </params>
        </cmd>
        <cmd>
            <type> reg_exec_cmd </type>
            <players_selection>
                <ep_targets> SONIC_MGMT </ep_targets>
            </players_selection>
            <name> run_on_stm </name>
            <tout> 600 </tout>
            <params>
                <exec> PYTHONPATH=/devts/ /ngts_venv/bin/pytest /root/mars/workspace/sonic-mgmt/ngts/scripts/collect_ptf_logs_on_not_success.py --setup_name=[[conf:extra_info.setup_name]] --rootdir=/root/mars/workspace/sonic-mgmt/ngts -c /root/mars/workspace/sonic-mgmt/ngts/pytest.ini --log-level=INFO --clean-alluredir --alluredir=/tmp/allure-results</exec>
            </params>
        </cmd>
    </on_not_success>
    </Case>
</global>
<test>
    <cases> sonic-mgmt/{test_type}_reboot.cases </cases>
</test>
</DBDEF>

'''


CASES_FILE_HEADER_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<CASEDEF>
    <global>
        <Test>
            <info> {test_name} Test </info>
            <name> {test_name} </name>
            <owner> </owner>
        </Test>
        <Case>
            <wrapper> [[run_time:db_tests_path]]/sonic-mgmt/sonic-tool/mars/scripts/community_mars_pytest_runner.py  </wrapper>
            <tout> 86400 </tout>
        </Case>
    </global>
'''

CASES_FILE_REBOOT_TESTCASE_TEMPLATE = '''<case>
    <info> {test_name} Case </info>
    <name> {test_name} </name>
    <tout> 3600 </tout>
    <cmd>
         <params>
             <static_args> --sonic-mgmt-dir /root/mars/workspace/[[conf:extra_info.sonic_mgmt_repo_name]] --dut-name [[conf:extra_info.dut_name]] --setup-name [[conf:extra_info.setup_name]] --sonic-topo [[conf:extra_info.topology]] --json-root-dir [[conf:extra_info.json_root_dir]] --raw-options "\\\'--log-cli-level debug  --show-capture=no -ra --showlocals  --clean-alluredir --alluredir=/tmp/allure-results --allure_server_addr=\\\"10.215.11.120\\\"\\\'" --test-scripts platform_tests/test_advanced_reboot.py::test_{test_type}_reboot </static_args>
         </params>
    </cmd>
</case>
'''

CASES_FILE_REBOOT_WITH_UPGRADE_TESTCASE_TEMPLATE = '''<case>
    <info> {test_name} Case </info>
    <name> {test_name} </name>
    <tout> {timeout} </tout>
    <cmd>
         <params>
             <static_args> --sonic-mgmt-dir /root/mars/workspace/[[conf:extra_info.sonic_mgmt_repo_name]] --dut-name [[conf:extra_info.dut_name]] --setup-name [[conf:extra_info.setup_name]] --sonic-topo [[conf:extra_info.topology]] --json-root-dir [[conf:extra_info.json_root_dir]] --raw-options "\\\'--neighbor_type [[conf:extra_info.neighbor_type]] --log-cli-level debug --downgrade_type=onie --show-capture=no -ra --showlocals --upgrade_type={test_type} --base_image_list={base_versions_list} --target_image_list={target_version} --restore_to_image={target_version} --clean-alluredir --alluredir=/tmp/allure-results --allure_server_addr=\\\"10.215.11.120\\\"\\\'" --test-scripts upgrade_path/test_upgrade_path.py::{upgrade_testcase} </static_args>
         </params>
    </cmd>
</case>
'''

CASES_FILE_REBOOT_WITH_MULTI_HOP_UPGRADE_TESTCASE_TEMPLATE = '''<case>
    <info> Multi Hop Upgrade Case </info>
    <name> Multi Hop Upgrade </name>
    <tout> {timeout} </tout>
    <cmd>
         <params>
             <static_args> --sonic-mgmt-dir /root/mars/workspace/[[conf:extra_info.sonic_mgmt_repo_name]] --dut-name [[conf:extra_info.dut_name]] --setup-name [[conf:extra_info.setup_name]] --sonic-topo [[conf:extra_info.topology]] --json-root-dir [[conf:extra_info.json_root_dir]] --raw-options "\\\'--neighbor_type [[conf:extra_info.neighbor_type]] --log-cli-level debug --downgrade_type=onie --show-capture=no -ra --showlocals --upgrade_type={test_type} --multi_hop_upgrade_path={multi_hop_upgrade_path} --restore_to_image={target_version} --clean-alluredir --alluredir=/tmp/allure-results --allure_server_addr=\\\"10.215.11.120\\\"\\\'" --test-scripts upgrade_path/test_multi_hop_upgrade_path.py </static_args>
         </params>
    </cmd>
</case>
'''

CASES_FILE_END_LINE_TEMPLATE = '''
</CASEDEF>

'''


def get_test_name(r_type, is_upgrade_test):
    test_name = '{} Reboot'.format(r_type.upper())
    if is_upgrade_test:
        test_name = test_name + ' with Upgrade'
        if "sad" in upgrade_testcase:
            test_name = "Sad " + test_name
        if "double" in upgrade_testcase:
            test_name = "Double " + test_name
    return test_name


def prepare_db_files(reboot_types_list, is_upgrade_test=False):
    """
    Prepare DB files and store them into sonic-mgmt folder
    """
    for r_type in reboot_types_list:
        test_name = get_test_name(r_type, is_upgrade_test)

        db_file_name = '{}_reboot.db'.format(r_type)
        sonic_mgmt_path = os.path.dirname(os.path.abspath(__file__)).split('sonic-tool')[0]
        db_file_path = os.path.join(sonic_mgmt_path, db_file_name)
        with open(db_file_path, 'w') as file:
            file_data = DB_FILE_TEMPLATE.format(test_name=test_name, test_type=r_type)
            file.write(file_data)


def prepare_cases_files(reboot_type_iterations_dict, reboot_type_base_ver_images=None, target_ver=None):
    """
    Prepare CASES files and store them into sonic-mgmt folder
    """
    for r_type, iterations_number in reboot_type_iterations_dict.items():

        base_ver_images = reboot_type_base_ver_images[r_type]
        is_upgrade_test = base_ver_images and target_ver
        test_name = get_test_name(r_type, is_upgrade_test)
        cases_file_name = '{}_reboot.cases'.format(r_type)
        file_data = CASES_FILE_HEADER_TEMPLATE.format(test_name=test_name)
        for _ in range(iterations_number):
            if upgrade_testcase == "test_multi_hop_upgrade_path":
                file_data += CASES_FILE_REBOOT_WITH_MULTI_HOP_UPGRADE_TESTCASE_TEMPLATE.format(test_type=r_type,
                                                                                               multi_hop_upgrade_path=base_ver_images,
                                                                                               target_version=target_ver,
                                                                                               timeout=10800)
            else:
                if base_ver_images and target_ver:
                    for base_ver in base_ver_images.split(','):
                        file_data += CASES_FILE_REBOOT_WITH_UPGRADE_TESTCASE_TEMPLATE.format(test_name=test_name,
                                                                                             test_type=r_type,
                                                                                             base_versions_list=base_ver,
                                                                                             target_version=target_ver,
                                                                                             upgrade_testcase=upgrade_testcase,
                                                                                             timeout=case_timeout)
                else:
                    file_data += CASES_FILE_REBOOT_TESTCASE_TEMPLATE.format(test_name=test_name, test_type=r_type)
        file_data += CASES_FILE_END_LINE_TEMPLATE

        sonic_mgmt_path = os.path.dirname(os.path.abspath(__file__)).split('sonic-tool')[0]
        cases_file_path = os.path.join(sonic_mgmt_path, cases_file_name)
        with open(cases_file_path, 'w') as file:
            file.write(file_data)


def do_preparation_steps():
    """
    Prepare DB and CASES files and store them into sonic-mgmt folder
    """
    reboot_types_list = []
    reboot_type_iterations_dict = {}
    reboot_type_base_version_dict = {}

    if fast_reboot_executors:
        reboot_types_list.append('fast')
        reboot_type_iterations_dict['fast'] = int(fast_reboot_iterations_number)
        reboot_type_base_version_dict['fast'] = fast_base_version
    if warm_reboot_executors:
        reboot_types_list.append('warm')
        reboot_type_iterations_dict['warm'] = int(warm_reboot_iterations_number)
        reboot_type_base_version_dict['warm'] = warm_base_version

    if cold_reboot_executors:
        reboot_types_list.append('cold')
        reboot_type_iterations_dict['cold'] = int(cold_reboot_iterations_number)
        reboot_type_base_version_dict['cold'] = cold_base_version

    if not reboot_types_list:
        raise Exception('Looks like setups which will run fast/warm/cold reboot tests did not provided. '
                        'Please specify setups which will run fast/warm/cold reboot tests.')

    is_upgrade_test = True if target_version else False
    prepare_db_files(reboot_types_list, is_upgrade_test)
    prepare_cases_files(reboot_type_iterations_dict, reboot_type_base_ver_images=reboot_type_base_version_dict, target_ver=target_version)


def build_summary_report(results):
    """
    Build report email summary table
    """
    email_body = '<table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">' \
                 '<tbody>' \
                 '<tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">' \
                 '<td style="width: 10%;">Setup Name</td>' \
                 '<td style="width: 15%;">HwSKU</td>' \
                 '<td style="width: 5%;">Number of ports</td>' \
                 '<td style="width: 5%;">Reboot Type</td>' \
                 '<td style="width: 5%;">Total Iterations</td>' \
                 '<td style="width: 15%;">Base Version</td>' \
                 '<td style="width: 15%;">Target Version</td>' \
                 '<td style="width: 5%;">Average Dataplane Loss</td>' \
                 '<td style="width: 5%;">Average Controlplane Loss</td>' \
                 '<td style="width: 10%;">Tests Status</td>' \
                 '</tr>'

    for setup_name, setup_data_dict in results.items():
        for reboot_type in REBOOT_TYPES:
            if setup_data_dict[reboot_type]:
                total_iterations = len(setup_data_dict[reboot_type])
                base_ver = ','.join(setup_data_dict['common']['base_ver'][reboot_type])
                target_ver = setup_data_dict['common']['target_ver']
                average_dataplane_loss = setup_data_dict['results'][reboot_type]['dataplane_loss']
                average_controlplane_loss = setup_data_dict['results'][reboot_type]['controlplane_loss']

                passed_tests_num = setup_data_dict['results'][reboot_type]['passed']
                failed_tests_num = setup_data_dict['results'][reboot_type]['failed']
                tests_status = '<span style="font-size:14px; color: green">Passed: {},</span> ' \
                               '<span style="font-size:14px; color: red">Failed: {}</span>'.format(passed_tests_num,
                                                                                                   failed_tests_num)
                hwsku = setup_data_dict['common']['hwsku']
                total_ports_num = setup_data_dict['common']['total_ports']
                active_ports_num = setup_data_dict['common']['active_ports']
                ports = 'Total: {}, Active: {}'.format(total_ports_num, active_ports_num)

                setup_data = '<tr style="height: 18px;">' \
                             '<td style="width: 10%; height: 18px;">{}</td>' \
                             '<td style="width: 15%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 15%; height: 18px;">{}</td>' \
                             '<td style="width: 15%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 10%; height: 18px;">{}</td>' \
                             '</tr>'.format(setup_name, hwsku, ports, reboot_type, total_iterations, base_ver,
                                            target_ver, average_dataplane_loss, average_controlplane_loss, tests_status)

                email_body += setup_data

    email_body += '</tbody>' \
                  '</table>'

    return email_body


def get_downtime_list(setup_data, plane='dataplane_downtime'):
    """
    Get list with data/control plane downtime results
    """
    downtime_list = []
    for test_data in setup_data['data']:
        if test_data[plane] != UNKNOWN:
            downtime_list.append(test_data[plane])

    return downtime_list


def build_setup_report(setup_name, results):
    """
    Build report email table for specific setup
    """
    email_body = '<table style="border-collapse: collapse; width: 100%; height: 36px;" border="1">' \
                 '<tbody>' \
                 '<tr style="height: 18px; background-color: #777; color: white; font-weight: bold;">' \
                 '<td style="width: 5%;">Iteration Number</td>' \
                 '<td style="width: 5%;">Reboot Type</td>' \
                 '<td style="width: 15%;">Base Version</td>' \
                 '<td style="width: 15%;">Target Version</td>' \
                 '<td style="width: 5%;">Test Status</td>' \
                 '<td style="width: 10%;">Dataplane Loss</td>' \
                 '<td style="width: 10%;">Controlplane Loss</td>' \
                 '<td style="width: 20%;">Allure Report URL</td>' \
                 '</tr>'

    iteration_number = 1
    for reboot_type in REBOOT_TYPES:
        for test_run in results[setup_name][reboot_type]:
            base_ver = test_run['base_ver']
            target_ver = test_run['target_ver']
            dataplane_downtime = UNKNOWN
            controlplane_downtime = UNKNOWN
            if reboot_type != UNKNOWN:
                dataplane_downtime = test_run['dataplane'] if int(test_run['dataplane']) != -1 else UNKNOWN
                controlplane_downtime = test_run['controlplane'] if int(test_run['controlplane']) != -1 else UNKNOWN
            allure_report_url = test_run['allure_report']
            test_status = test_run['test_status']
            color = 'green' if test_status == 'passed' else 'red'

            iteration_data = '<tr style="height: 18px;">' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px;">{}</td>' \
                             '<td style="width: 15%; height: 18px;">{}</td>' \
                             '<td style="width: 15%; height: 18px;">{}</td>' \
                             '<td style="width: 5%; height: 18px; color: {}">{}</td>' \
                             '<td style="width: 10%; height: 18px;">{}</td>' \
                             '<td style="width: 10%; height: 18px;">{}</td>' \
                             '<td style="width: 20%; height: 18px;">{}</td>' \
                             '</tr>'.format(iteration_number, reboot_type, base_ver, target_ver, color, test_status,
                                            dataplane_downtime, controlplane_downtime, allure_report_url)

            email_body += iteration_data
            iteration_number += 1

    email_body += '</tbody>' \
                  '</table>'

    return email_body


def parse_args():
    """
    Parse script arguments
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('--do_preparation', dest='do_preparation', action='store_true',
                        help='Generate MARS CASES and DB files')
    parser.add_argument('--session_id', dest='session_id', help='MARS session ID')
    parser.add_argument('--setup_name', dest='setup_name', help='MARS setup name')
    parser.add_argument('--generate_report_email', dest='generate_report_email', action='store_true',
                        help='Provide this arg if want to generate report email')

    return parser.parse_args()


def get_tests_results_dict():
    """
    Get dictionary with tests results(read from file if exist or create new)
    """
    results_dict = {}

    if os.path.exists(tests_results_file_path):
        with open(tests_results_file_path) as data:
            results_dict = json.load(data)

    return results_dict


def get_sql_db_connection():
    """
    Get connection to SQL database
    """
    connections_params = DbConstants.CREDENTIALS[CliType.SONIC]
    sql_connection_obj = ConnectMSSQL(connections_params['server'], connections_params['database'],
                                      connections_params['username'], connections_params['password'])
    sql_connection_obj.connect_db()
    return sql_connection_obj


def get_executed_tests_data_during_mars_session(sql_connection_obj, session_id):
    """
    Get executed tests data during specific MARS session ID
    """
    test_ids_reports_dict = {}
    # Get all executed tests during MARS session: mars_key_id, tests status and allure reports
    query_get = "SELECT mars_key_id,allure_url,mars_result FROM mars_respond WHERE session_id='{}'".format(session_id)
    try:
        sql_connection_obj.cursor.execute(query_get)
        results = sql_connection_obj.cursor.fetchall()
        for item in results:
            mars_key_id = item[0]
            allure_url = item[1]
            test_status = item[2]
            test_ids_reports_dict[mars_key_id] = {'allure': allure_url, 'test_status': test_status}
    except Exception as err:
        logger.error('Got exception during getting data from SQL. Error: {}'.format(err))
    return test_ids_reports_dict


def update_test_data_by_test_run_info(sql_connection_obj, session_id, mars_key_id, test_data):
    # Get test run time and test run id
    query_get = "SELECT test_run_dateTime,test_run_id,test_id,DUTImageVersion FROM tests_runs WHERE MarsSessionId='{}' AND MarsKeyId='{}'".format(
        session_id, mars_key_id)
    try:
        sql_connection_obj.cursor.execute(query_get)
        date, test_run_id, test_id, image_version = sql_connection_obj.cursor.fetchone()
        test_data.update({'exec_date': date, 'test_run_id': test_run_id, 'test_id': test_id, 'base_ver': image_version})
    except Exception as err:
        logger.error('Got exception during getting data from SQL. Error: {}'.format(err))


def update_test_data_with_traffic_loss_info(sql_connection_obj, test_data):
    # Get data/control plane loss
    query_get = "SELECT test_attribute,test_attribute_value FROM test_data WHERE test_run_id='{}'".format(
        test_data.get('test_run_id'))
    try:
        sql_connection_obj.cursor.execute(query_get)
        for data in sql_connection_obj.cursor.fetchall():
            key, value = data
            test_data[key] = value
    except Exception as err:
        logger.error('Got exception during getting data from SQL. Error: {}'.format(err))


def update_results_with_setup_extra_data(sql_connection_obj, test_run_id, results_dict):
    query_get = "SELECT SetupExtraInfo FROM rel_test_run_setup WHERE test_run_id='{}'".format(test_run_id)
    try:
        sql_connection_obj.cursor.execute(query_get)
        extra_data = sql_connection_obj.cursor.fetchone()[0]
        results_dict[setup_name]['common'].update(json.loads(extra_data))
    except Exception as err:
        logger.error('Got exception during getting data from SQL. Error: {}'.format(err))


def sort_results_by_execution_date(setup_name, results_dict):
    """
    Sort test cases results by execution date(when test cases has been uploaded into DB)
    """
    for reboot_type in REBOOT_TYPES:
        if reboot_type == UNKNOWN:
            continue
        tests_data_list = results_dict[setup_name][reboot_type]
        # Sort tests list by execution date
        try:
            tests_data_list_sorted = sorted(tests_data_list, key=lambda d: d.get('exec_date'))
        except Exception as err:
            logger.error('Unable to sort test runs by execution order. Got error: {}'.format(err))
            tests_data_list_sorted = tests_data_list

        results_dict[setup_name][reboot_type] = tests_data_list_sorted


def get_results_for_session(session_id, setup_name):
    """
    Generate JSON report file which can be used for generate email report
    """
    sql_connection_obj = get_sql_db_connection()
    results_dict = get_tests_results_dict()
    results_dict[setup_name] = {
        'common': {'hwsku': None, 'total_ports': None, 'active_ports': None, 'base_ver': {'fast': [], 'warm': [], 'cold': [], 'unknown': []}, 'target_ver': ''},
        'fast': [],  # Example see below in 'test_data' variable
        'warm': [],
        'cold': [],
        'unknown': [],
        'results': {'fast': {'passed': 0, 'failed': 0, 'dataplane_loss': 0, 'controlplane_loss': 0},
                    'warm': {'passed': 0, 'failed': 0, 'dataplane_loss': 0, 'controlplane_loss': 0},
                    'cold': {'passed': 0, 'failed': 0, 'dataplane_loss': 0, 'controlplane_loss': 0},
                    'unknown': {'passed': 0, 'failed': 0, 'dataplane_loss': 0, 'controlplane_loss': 0}
                    }
    }

    test_ids_reports_dict = get_executed_tests_data_during_mars_session(sql_connection_obj, session_id)

    # Get data/control plane loss for specific test cases
    for mars_key_id in test_ids_reports_dict:
        update_results_for_test_case(sql_connection_obj, test_ids_reports_dict, mars_key_id, results_dict)

    sort_results_by_execution_date(setup_name, results_dict)

    update_average_loss(setup_name, results_dict)

    with open(tests_results_file_path, 'w') as data_file_obj:
        json.dump(results_dict, data_file_obj, default=str)


def update_results_for_test_case(sql_connection_obj, test_ids_reports_dict, mars_key_id, results_dict):
    """
    Update results_dict with data for specific test case
    """

    test_status = test_ids_reports_dict[mars_key_id]['test_status']
    allure_report = test_ids_reports_dict[mars_key_id]['allure']

    test_data = {'exec_date': None, 'base_ver': UNKNOWN, 'target_ver': '', 'test_status': test_status,
                 'dataplane': None, 'controlplane': None, 'allure_report': allure_report}

    update_test_data_by_test_run_info(sql_connection_obj, session_id, mars_key_id, test_data)

    update_test_data_with_traffic_loss_info(sql_connection_obj, test_data)

    # Update HwSKU, total/active ports, image version only one time
    test_run_id = test_data.get('test_run_id')
    update_results_with_setup_extra_data(sql_connection_obj, test_run_id, results_dict)
    test_type = 'warm'
    if test_data.get('test_id'):
        if test_data['test_id'] in FAST_REBOOT_TEST_IDS:
            test_type = 'fast'
        if test_data['test_id'] in COLD_REBOOT_TEST_IDS:
            test_type = 'cold'

    else:
        test_type = UNKNOWN

    extra_data_base_version = results_dict[setup_name]['common'].get('base_version')
    if extra_data_base_version:  # then we did upgrade test
        results_dict[setup_name]['common']['base_ver'][test_type].append(extra_data_base_version)
        test_data['target_ver'] = test_data['base_ver']
        test_data['base_ver'] = extra_data_base_version
        if not results_dict[setup_name]['common']['target_ver']:  # update target ver for setup only once
            results_dict[setup_name]['common']['target_ver'] = test_data['target_ver']
        results_dict[setup_name]['common'].pop('base_version')
    else:
        results_dict[setup_name]['common']['base_ver'][test_type].append(test_data['base_ver'])

    if test_status == 'passed':
        results_dict[setup_name]['results'][test_type]['passed'] += 1
    else:
        results_dict[setup_name]['results'][test_type]['failed'] += 1

    # Update results for test iteration
    results_dict[setup_name][test_type].append(test_data)


def update_average_loss(setup_name, results_dict):
    """
    Update results_dict with results for average traffic loss
    """
    for reboot_type in REBOOT_TYPES:
        tests_data_list = results_dict[setup_name][reboot_type]
        dataplane_average_loss = UNKNOWN
        controlplane_average_loss = UNKNOWN
        if reboot_type != UNKNOWN:
            dataplane_loss_list = get_loss_list(tests_data_list, traffic_plane='dataplane')
            controlplane_loss_list = get_loss_list(tests_data_list, traffic_plane='controlplane')
            dataplane_average_loss = count_average_loss(dataplane_loss_list)
            controlplane_average_loss = count_average_loss(controlplane_loss_list)

        # Update average loss for setup and specific reboot type
        results_dict[setup_name]['results'][reboot_type]['dataplane_loss'] = dataplane_average_loss
        results_dict[setup_name]['results'][reboot_type]['controlplane_loss'] = controlplane_average_loss


def get_loss_list(tests_data_list, traffic_plane):
    """
    Get list of traffic loss time values
    """
    loss_list = []
    for test_run_data in tests_data_list:
        if int(test_run_data[traffic_plane]) != -1:
            loss_list.append(test_run_data[traffic_plane])
    return loss_list


def count_average_loss(loss_list):
    """
    Count average traffic loss time
    """
    average_loss = UNKNOWN
    if loss_list:
        average_loss = sum(loss_list) / len(loss_list)
    return average_loss


def generate_email_report_html():
    """
    Generate email HTML report which can be send to users
    """
    email_body = ''
    email_header = '<p style="font-size:14px">Hi All,</p>' \
                   '<p style="font-size:14px">Please see below the results of the reboot tests execution</p>'
    email_body += email_header

    try:
        with open(tests_results_file_path) as data_file_obj:
            results = json.load(data_file_obj)

        email_body += build_summary_report(results)
        email_body += '<br>'

        for setup_name in results:
            email_body += '<p style="font-size:14px"> <b>Setup name: {} </b></p>'.format(setup_name)
            email_body += build_setup_report(setup_name, results)
            email_body += '<br>'
    except Exception as err:
        email_body += '<p style="font-size:14px">Error happen during build report email. ' \
                      'Please check Jenkins job logs. <br> Python traceback: {} </p>'.format(err)

    with open(email_report_file_path, 'w') as report:
        report.write(email_body)


if __name__ == "__main__":

    args = parse_args()

    do_preparation = args.do_preparation
    session_id = args.session_id
    setup_name = args.setup_name
    generate_report_email = args.generate_report_email

    if do_preparation:  # generate db and cases files
        do_preparation_steps()
    elif session_id:  # collect results for session
        get_results_for_session(session_id, setup_name)
    elif generate_report_email:  # generate email report
        generate_email_report_html()
    else:
        raise Exception('Please provide correct script run arguments')
