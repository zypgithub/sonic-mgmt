import json
import logging
import math
import os
from collections import defaultdict

import allure
import pytest

from ngts.conftest import update_topology_with_cli_class
from ngts.constants.constants import PytestConst
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
    outcome = yield
    rep = outcome.get_result()

    if rep.failed and os.environ.get(PytestConst.GET_DUMP_AT_TEST_FALIURE) != "False":
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


def generate_and_copy_sonic_dump(topology_obj, dut_engine, dumps_folder, duration, item):
    with allure.step('Generate Techsupport of last {} seconds'.format(duration)):
        output = dut_engine.run_cmd('sudo generate_dump -s \"-{} seconds\"'.format(duration), validate=True)
        remote_dump_path = output.splitlines()[-1]

    dest_file = dumps_folder + '/sysdump_' + item.name.replace('/', '_') + '.tar.gz'
    copy_dump_file(dut_engine, remote_dump_path, dest_file)

    is_simx = item.funcargs.get('is_simx')
    is_air = item.funcargs.get('is_air')
    if is_simx and not is_air:
        with allure.step('Dump SIMX VM logs'):
            dump_simx_data(topology_obj, dumps_folder, name_prefix=item.name.replace('/', '_'))
    store_dest_file_path(dest_file, item.name.replace('/', '_'))


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
