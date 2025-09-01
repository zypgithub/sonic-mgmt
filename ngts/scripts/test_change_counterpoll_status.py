#!/usr/bin/env python
import allure
import logging
import pytest
from retry import retry

logger = logging.getLogger()

counterpoll_name_list = ["flowcnt-trap", "pg-drop", "port", "port-buffer-drop", "queue", "rif", "acl", "tunnel", "watermark", "wredqueue"]


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize("action", ["enable", "disable"])
@allure.title('Workaround: change counterpoll status')
def test_change_counterpoll_status(topology_obj, action):
    """
    This test will change counterpoll status.
    It is a workaround due to the the bug of https://redmine.mellanox.com/issues/3047059.
    Before running qos sai test, disable all counterpolls.
    After running qos sai test, enable all counterpolls.
    :param topology_obj: topology object fixture
    :param action: enable or disable
    :return: raise assertion error in case of script failure
    """
    try:
        dut_cli_object = topology_obj.players['dut']['cli']
        with allure.step(" {} counterpoll status".format(action)):
            for counter_name in counterpoll_name_list:
                if action == "enable":
                    try:
                        dut_cli_object.counterpoll.enable_counterpoll(counter_name)
                    except Exception as err:
                        logging.error(err)
                elif action == "disable":
                    try:
                        dut_cli_object.counterpoll.disable_counterpoll(counter_name)
                    except Exception as err:
                        logging.error(err)
        with allure.step("Verify counterpoll status is {}".format(action)):
            veify_counter_status(dut_cli_object, excepted_status=action)
    except Exception as err:
        raise AssertionError(err)


@retry(Exception, tries=10, delay=5)
def veify_counter_status(dut_cli_object, excepted_status):
    counterpoll_status_dict = dut_cli_object.counterpoll.parse_counterpoll_show()
    for counter, value in counterpoll_status_dict.items():
        assert value['Status'] == excepted_status, "The status of {} is: {}".format(counter, value['Status'])
