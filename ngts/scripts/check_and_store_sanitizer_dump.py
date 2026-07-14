import allure
import os
import logging
import pytest
from ngts.constants.constants import PytestConst
from ngts.helpers.sanitizer_helper import get_asan_apps, get_mail_address, disable_asan_apps, \
    check_sanitizer_and_store_dump, aggregate_asan_and_send_mail
from devts.infra.tools.validations.traffic_validations.port_check.port_checker import \
    check_port_status_till_alive
from concurrent.futures import ThreadPoolExecutor, as_completed
from ngts.common.util import get_dpu_engines

logger = logging.getLogger()


@pytest.fixture(scope='function')
def test_name(request):
    """
    Method for getting the test name parameter for script check_and_store_sanitizer_dump.py,
    the script will check for sanitizer failures and store dump under test name
    :param request: pytest builtin
    :return: the test name, i.e, push_gate
    """
    return request.config.getoption('--test_name')


@pytest.fixture(scope='function')
def send_mail(request):
    """
    Method for getting the send_mail boolean parameter for script check_and_store_sanitizer_dump.py,
    true, to send the report by mail
    :param request: pytest builtin
    :return: True/False, True to send mail.
    """
    value = request.config.getoption('--send_mail')
    return True if value in ['t', 'T', 'True', 'true', 'TRUE'] else False


@pytest.mark.disable_loganalyzer
def test_sanitizer(topology_obj, cli_objects, dumps_folder, test_name, send_mail, setup_name, dpu_asan):
    os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"
    switch_engine = topology_obj.players['dut']['engine']
    if dpu_asan:
        dut_engines = get_dpu_engines(topology_obj)
    else:
        dut_engines = [switch_engine]

    asan_apps = [] if dpu_asan else get_asan_apps(topology_obj, cli_objects.dut)
    mail_address = get_mail_address()
    is_sanitizer = dut_engines[0].run_cmd("sonic-cfggen -y /etc/sonic/sonic_version.yml -v asan").strip() == "yes"

    if dpu_asan:
        if not is_sanitizer:
            logger.info("Image doesn't include sanitizer - script is not checking for sanitizer dumps")
            return
    else:
        if not is_sanitizer and not asan_apps:
            logger.info("Image doesn't include sanitizer - script is not checking for sanitizer dumps")
            return

    if asan_apps:
        disable_asan_apps(cli_objects, asan_apps)

    if is_sanitizer:
        with allure.step('Reboot DUT'):
            cli_objects.dut.general.safe_reboot_flow(
                topology_obj=topology_obj,
                reboot_type='reboot',
                check_sanitizer_after_reboot=False,
            )

    if dpu_asan:
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(check_port_status_till_alive,
                                True, dpu_engine.ip, dpu_engine.ssh_port,
                                tries=30, delay=10): dpu_engine
                for dpu_engine in dut_engines
            }
            for future in as_completed(futures):
                future.result()

    for dut_engine in dut_engines:
        with allure.step('Check sanitizer output after reboot/disable of asan apps'):
            sanitizer_dump_path = check_sanitizer_and_store_dump(dut_engine, dumps_folder, test_name)
            if sanitizer_dump_path and send_mail:
                with allure.step(f'Sending mail with the sanitizer failures to {mail_address}'):
                    aggregate_asan_and_send_mail(mail_address, sanitizer_dump_path, dumps_folder, setup_name)
