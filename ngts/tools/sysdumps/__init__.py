import json
import logging
import math
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import allure
import pytest

from ngts.conftest import update_topology_with_cli_class
from ngts.constants.constants import PytestConst, InfraConst
from ngts.helpers.general_helper import get_dut_cli_obj_from_topo_obj
from ngts.scripts.store_techsupport_on_not_success import dump_simx_data
from ngts.tools.allure_report.allure_report_attacher import collect_stored_cmds_then_attach_to_allure_report, \
    clean_stored_cmds_with_fixture_scope_list
from ngts.tools.test_utils.nvos_general_utils import get_switch_type
from ngts.nvos_constants.constants_nvos import TopologyConsts
from ngts.tools.infra import get_dumps_folder
from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases

logger = logging.getLogger()

test_suites_dumps = defaultdict(int)


def get_topology_obj(item):
    topology = get_topology_by_setup_name_and_aliases(item.config.option.setup_name, slow_cli=False)
    update_topology_with_cli_class(topology, item._request)
    return topology


def generate_and_copy_dump(item, dumps_folder, topology_obj, duration):
    switch_type = get_switch_type(topology_obj)
    dut_engine = topology_obj.players['dut']['engine']
    collect_stored_cmds_then_attach_to_allure_report(topology_obj)
    generate_dump_method[switch_type](topology_obj, dut_engine, dumps_folder, duration, item)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Techsupport creator. Will be executed at the end of test call in case of failure.
    """
    logger.debug(f"Executing pytest_runtest_makereport for {item.name}")
    outcome = yield
    rep = outcome.get_result()

    if rep.failed and os.environ.get(PytestConst.GET_DUMP_AT_TEST_FALIURE) != "False":
        logger.debug(f"Entering sysdump creation for {item.name}")
        os.environ.pop(item.name, None)
        session_id = item.config.option.session_id
        if session_id is None and item.config.option.store_dump_on_fail != True:
            logger.info('### `session_id` and `store_dump_on_fail` flags were not provided, '
                        'sysdump will not be created ###')
            return
        suite_name = item.parent.name
        if test_suites_dumps.get(suite_name, 0) > 2:
            logger.info('### The number of sysdumps for this test suite is more than 3, '
                        'sysdump will not be created ###')
            return
        test_suites_dumps[suite_name] += 1

        with allure.step('The test case has failed, generating a sysdump'):
            try:
                test_name = item.name.replace('/', '_')
                # Set up configuration for Community test infra as it doesn't have topology_obj
                if (topology_obj := item.funcargs.get('topology_obj')) is None:
                    topology_obj = get_topology_obj(item)
                    duration = 7200
                else:
                    duration = get_test_duration(item)
                if (dumps_folder := item.funcargs.get('dumps_folder')) is None:
                    dumps_folder = get_dumps_folder(item.config.option.setup_name, session_id, topology_obj)
                existing_dump_file = next(
                    (dump_file for dump_file in os.listdir(dumps_folder) if test_name in dump_file), None)
                if existing_dump_file and session_id:
                    dump_path = f'{dumps_folder}/{existing_dump_file}'
                    with allure.step(f'The test case has failed, dump already exists at log folder {dump_path}'):
                        pass
                else:
                    with allure.step('The test case has failed, generating a sysdump'):
                        generate_and_copy_dump(item, dumps_folder, topology_obj, duration)
            except BaseException as err:
                error_message = f'Failed to generate/store techsupport dump.\nGot error: {err}'
                logger.error(error_message)
        topology_obj = item.funcargs.get('topology_obj')
        if topology_obj:
            clean_stored_cmds_with_fixture_scope_list(topology_obj)
        os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "True"
    else:
        logger.debug(f"Skipping sysdump creation for {item.name}")


def generate_and_copy_nvos_dump(topology_obj, dut_engine, dumps_folder, duration, item):
    with allure.step("Generating NVOS tech-support"):
        logging.info("disconnect dut engine")
        dut_engine.disconnect()
        logging.info("Generating tech-support")
        dut_engine.run_cmd('nv action generate system tech-support', validate=True)
        output = dut_engine.run_cmd('nv show system tech-support files -o json', validate=True)
        tech_support_file_on_switch = json.loads(output)["latest"]["path"]

    dest_tech_support_file = dumps_folder + '/sysdump_' + item.name.replace('/', '_') + '.tar.gz'
    copy_dump_file(dut_engine, tech_support_file_on_switch, dest_tech_support_file)
    store_dest_file_path(dest_tech_support_file, item.name.replace('/', '_'))


def generate_and_copy_cumulus_dump(topology_obj, dut_engine, dumps_folder, duration, item):
    logging.info("Generate dump for Cumulus - not implemented yet")
    pass


def need_implicit_dpu_dump(item):
    """The adapter function to check if the DPUs need to be dumped implicitly

    Args:
        item (_type_): The reference to the pytest test called

    Returns:
        bool: True if need to dump all DPUs available in the topology
    """
    if "smart_switch" in item.location[0]:
        return True
    if "smartswitch" in item.location[0]:
        return True
    if "dash" in item.location[0]:
        return True
    return False


def generate_and_copy_sonic_dump_runner(topology_obj, device_engine, device_alias, dumps_folder, duration, item_clean_name):
    """The function to run the separate thread to generate and copy the sysdump for the DUT

    Args:
        topology_obj (_type_): The reference to the topology object
        device_engine (_type_): The reference to the device engine
        device_alias (_type_): The alias of the device to dump
        dumps_folder (_type_): The reference to the dumps folder
        duration (_type_): The duration/timeout to generate the sysdump
        item_clean_name (_type_): The clean name of the test

    Returns:
        str: The path to the generated sysdump file
    """
    logger.info(f"Started {device_alias} sysdump")
    output = device_engine.run_cmd('sudo generate_dump -s \"-{} seconds\"'.format(duration), validate=True)
    remote_dump_path = output.splitlines()[-1]
    logger.debug(f"Remote dump path for {device_alias}: {remote_dump_path}")
    dest_file = dumps_folder + f'/sysdump_{device_alias}_' + item_clean_name + '.tar.gz'
    logger.info(f"Destination file for {device_alias}: {dest_file}")
    copy_dump_file(device_engine, remote_dump_path, dest_file)
    logger.info(f"Completed {device_alias} sysdump: {dest_file}")
    return dest_file


def get_dpus_to_dump(topology_obj, item):
    """The function to get the DPUs to dump

    Args:
        topology_obj (_type_): The reference to the topology object
        item (_type_): The reference to the pytest test called

    Returns:
        dict: The dictionary of the DPUs to with the DPU device info structure
    """
    cli_obj = get_dut_cli_obj_from_topo_obj(topology_obj)
    try:
        dpu_status = cli_obj.get_dpus_status()
    except Exception as err:
        logger.info(f"Error getting DPUs status, skipping the DPU dumps: {err}")
        return dict()

    dpus_to_dump = dict()
    for device_alias, status_dict in dpu_status.items():
        device_alias = device_alias.lower()
        if status_dict['Admin-Status'] != 'up' or status_dict['Oper-Status'] != 'Online':
            logger.warning(f"DPU {device_alias} is down or offline: {status_dict}, skipping the DPU dump")
            continue

        dpu_info = topology_obj.players.get(device_alias)
        if not dpu_info:
            logger.warning(f"No DPU player available for {device_alias}, skipping the DPU dump")
            continue
        dpus_to_dump[device_alias] = dpu_info['engine']
    return dpus_to_dump


def collect_all_dumps(topology_obj, duts_to_dump, dumps_folder, duration, item_clean_name):
    """The function to collect all the sysdumps running in parallel

    Args:
        topology_obj (_type_): The reference to the topology object
        duts_to_dump (_type_): The dictionary of the DUTs to dump
        dumps_folder (_type_): The reference to the dumps folder
        duration (_type_): The duration/timeout to generate the sysdump
        item_clean_name (_type_): The clean name of the test, removed special characters

    Returns:
        str: The path to the generated sysdump DUT file
    """
    futures = dict()
    # run the sysdump in parallel for the DUT and DPUs
    logger.debug(f"Topology players counter: {len(topology_obj.players)}")
    with ThreadPoolExecutor(max_workers=len(topology_obj.players)) as executor:
        for dut_alias, dut_engine in duts_to_dump.items():
            futures[dut_alias] = executor.submit(generate_and_copy_sonic_dump_runner,
                                                 topology_obj, dut_engine, dut_alias,
                                                 dumps_folder, duration, item_clean_name)
        logger.debug("Waiting for all sysdumps to complete")
        for done_future in as_completed(futures.values()):
            try:
                complete_msg = f"Completed sysdump: {done_future.result()}"
                with allure.step(complete_msg):
                    logger.info(complete_msg)
            except Exception as err:
                logger.error(f"Error generating sysdump: {err}")
    return futures["dut"].result()


def get_dpus_from_duthosts(topology_obj, duthosts_value):
    """The function to get the DUTs to dump from the duthosts fixture. Matches the dut hosts to the available players in the topology

    Args:
        duthosts_value (_type_): The reference to the duthosts fixture

    Returns:
        dict: The dictionary of the DUTs to dump
    """
    duts_to_dump = dict()
    # Obtain the host name for all duts
    try:
        dut_hosts_set = set(dut_host.hostname for dut_host in duthosts_value)
        logger.info(f"DUT hosts set: {dut_hosts_set}")
    except Exception as err:
        dut_hosts_set = set()
        logger.warning(f"Unable to obtain the duthosts, using empty set. Error: {err}")
        # Add add the matching DUT to the duts to dump
    for dut_alias, dut_info in topology_obj.players.items():
        if dut_alias.endswith('_serial'):
            continue
        try:
            dut_hostname = dut_info['attributes'].noga_query_data['attributes']['Common']['Name']
        except Exception as err:
            logger.warning(f"Unable to obtain the DUT hostname for {dut_alias} from nog attributes")
            continue

        if dut_hostname not in dut_hosts_set:
            logger.info(f"DUT {dut_alias} is not in the duthosts of the caller function, dumps is not required")
            continue
        logger.info(f"Adding the DUT {dut_alias} to the duts_to_dump")
        duts_to_dump[dut_alias] = dut_info['engine']
    return duts_to_dump


def generate_and_copy_sonic_dump(topology_obj, dut_engine, dumps_folder, duration, item):
    item_clean_name = item.name.replace('/', '_').replace('[', '_').replace(']', '_')
    with allure.step('Generate Techsupport of last {} seconds'.format(duration)):
        logger.debug(f"item.location: {item.location}, item.name: {item.name}, item.originalname: {item.originalname}")
        if item.originalname == "test_check_errors_in_log_during_deploy_sonic_image":
            # log analyzer is special since it runs on specific DUT parameter "switch" or "dpu"
            # this is to avoid the duplicate dumps of the DPU and SWITCH
            duts_to_dump = {"dut": item.funcargs['dut_host']}
        elif need_implicit_dpu_dump(item):
            # tests that need to dump all available DPUs
            logger.info(f"Implicit DPU dumps required per {item.name}")
            # get dpus to dump implicitly
            duts_to_dump = get_dpus_to_dump(topology_obj, item)
        elif not item.module.__name__.startswith('ngts.'):
            # for community tests, check 'duthosts' fixture and add all available DPUs from it
            logger.info("Checking 'duthosts' fixture for the DPUs to dump")
            duts_to_dump = get_dpus_from_duthosts(topology_obj, item.funcargs['duthosts'])
        else:
            logger.info(f"DPU dumps are not required per {item.name}")
            duts_to_dump = dict()

        # always add the DUT itself
        if ("dut" not in duts_to_dump):
            duts_to_dump["dut"] = topology_obj.players["dut"]['engine']

        # send the sysdumps requests to the worker threads
        dut_dump_file = collect_all_dumps(topology_obj, duts_to_dump, dumps_folder, duration, item_clean_name)

    is_simx = item.funcargs.get('is_simx')
    is_air = item.funcargs.get('is_air')
    if is_simx and not is_air:
        with allure.step('Dump SIMX VM logs'):
            dump_simx_data(topology_obj, dumps_folder, name_prefix=item_clean_name)
    logger.debug(f"Storing the DUT sysdump {dut_dump_file}")
    store_dest_file_path(dut_dump_file, item_clean_name)


generate_dump_method = {TopologyConsts.NVOS: generate_and_copy_nvos_dump,
                        TopologyConsts.CL: generate_and_copy_cumulus_dump,
                        TopologyConsts.SONIC: generate_and_copy_sonic_dump}


def copy_dump_file(dut_engine, source_file, dest_file):
    copy_msg = 'Copy dump {} to log folder {}'.format(source_file, dest_file)
    with allure.step(copy_msg):
        logger.info(copy_msg)
        dut_engine.copy_file(source_file=source_file,
                             dest_file=dest_file,
                             file_system='/',
                             direction='get',
                             overwrite_file=True,
                             verify_file=False)
        os.chmod(dest_file, 0o777)


def get_test_duration(item):
    """
    Get duration of test case. Init time + test body time + 120 seconds
    :param item: pytest build-in
    :return: integer, test duration
    """
    duration = math.ceil(item.rep_setup.duration) + 120
    if hasattr(item, "rep_call"):
        duration = duration + math.ceil(item.rep_call.duration)
    if hasattr(item, "rep_teardown"):
        duration = duration + math.ceil(item.rep_teardown.duration)
    return duration


def store_dest_file_path(dest_file, test_name):
    """
    Store the dump path to environment variables to later usage by pytest_terminal_summary
    :param dest_file: dump file
    :param test_name: test_name
    """
    os.environ[test_name] = dest_file
