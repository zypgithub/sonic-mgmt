import logging
import pytest
import time
import re
import json

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.HostMethods import HostMethods
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool

log = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_watchdog_good_kill(engines, test_api):
    """
    Name: Watchdog Good Kill
    ===============================================

    Description:
    ===============================================
    This test ensures that when the watchdog is killed correctly the system
    does not restart due to a watchdog timeout

    Steps:
    ===============================================
    1. Enable the watchdog if it is not enabled
    2. Kill the watchdog
    3. Ensure the system does not restart
    """
    TestToolkit.tested_api = test_api

    with allure.step("If watchdog is not running, Skip the test"):
        pid_wd = engines.dut.run_cmd("pidof wd_keepalive")
        if not pid_wd:
            pytest.skip("No pid for wd_keep_alive skipping test.")

    with allure.step("Getting the current timeout of the watchdog."):
        watchdog_timeout = int(get_current_watchdog_time(engines))
        log.info(f"Current watchdog timeout - {watchdog_timeout}")

    # Need to get the boot id to see if it actually shuts down
    with allure.step("Get boot id before shutting down watchdog."):
        cmd = "cat /proc/sys/kernel/random/boot_id"
        start_boot_id = engines.dut.run_cmd(cmd)

    # Kill watchdog
    with allure.step("Killing the watchdog process correctly."):
        engines.dut.run_cmd("sudo kill -TERM %s" % pid_wd)

    # Give enough time for the reset to occur
    with allure.step("Wait to ensure DUT doesn't reboot."):
        log.info(
            "Waiting %d seconds to ensure DUT stays up." %
            (
                (watchdog_timeout * 4) + 5
            )
        )
        time.sleep((watchdog_timeout * 4) + 5)

        try:
            code = check_shutdown_state(engines, start_boot_id)
        except Exception:
            assert False, "DUT never came back after the watchdog fired"

        # Code of 1 means the DUT did not shutdown, good
        if code != 1:
            assert (False), "DUT either shutdown or rebooted when the correct \
shutdown for the watchdog was used."
        else:
            log.info("DUT correctly stayed up with a 'good' kill of watchdog")

    with allure.step("Restart watchdog"):
        engines.dut.run_cmd("sudo systemctl start wd_keepalive")
        new_pid_wd = engines.dut.run_cmd("pidof wd_keepalive")
        if not new_pid_wd or (new_pid_wd == pid_wd):
            assert False, "Watchdog restart failed"

    log.info("Pass")


@pytest.mark.platform
@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_watchdog_bad_kill(engines, test_api):
    """
    Name: Watchdog Bad Kill
    ===============================================

    Description:
    ===============================================
    This test ensures that when the watchdog is killed incorrectly (kill -9)
    that the system will reset after the timer expires

    Steps:
    ===============================================
    1. Enable the watchdog if it is not enabled
    2. Kill the watchdog incorrectly
    3. Ensure the system restarts
    """
    TestToolkit.tested_api = test_api

    with allure.step("If watchdog is not running, Skip the test"):
        pid_wd = engines.dut.run_cmd("pidof wd_keepalive")
        if not pid_wd:
            pytest.skip("No pid for wd_keep_alive skipping test.")

    with allure.step("Getting the current timeout of the watchdog."):
        watchdog_timeout = int(get_current_watchdog_time(engines))
        log.info(f"Current watchdog timeout - {watchdog_timeout}")

    # Need to get the boot id to see if it actually shuts down
    with allure.step("Get boot id before shutting down watchdog."):
        cmd = "cat /proc/sys/kernel/random/boot_id"
        start_boot_id = engines.dut.run_cmd(cmd)
        log.info(f"Boot ID before killing watchdog - {start_boot_id}")

    # Kill watchdog
    with allure.step("Killing the watchdog process INCORRECTLY."):
        engines.dut.run_cmd("sudo kill -9 %s" % pid_wd)

    # Give enough time for the reset to occur
    with allure.step("Wait to ensure DUT eventually reboots."):
        log.info(
            "Waiting %d seconds to ensure DUT eventually resets."
            % ((watchdog_timeout * 6) + 5)
        )
        time.sleep((watchdog_timeout * 6) + 5)
        engines.dut.disconnect()

        try:
            code = check_shutdown_state(engines, start_boot_id)
        except Exception:
            assert False, "DUT never came back after the watchdog fired"

        # Code of 2 means the DUT restarted, good
        if code != 2:
            assert False, "DUT did not reset when the watchdog was killed \
incorrectly."
        else:
            log.info(
                "DUT correctly restarted when the watchdog was killed \
incorrectly."
            )

    with allure.step("Restart watchdog"):
        engines.dut.run_cmd("sudo systemctl start wd_keepalive")
        new_pid_wd = engines.dut.run_cmd("pidof wd_keepalive")
        if not new_pid_wd or (new_pid_wd == pid_wd):
            assert False, "Watchdog restart failed"

    log.info("Pass")


def get_current_watchdog_time(engines):
    """Grabs the amount of time the watchdog uses before reset

    This function is used to know the time the watchdog takes before it will
    actually reset the device

    :Returns:
        Returns the time in seconds that the watchdog takes before reset
    """

    timer_location = "/etc/watchdog.conf"

    time_for_reset = engines.dut.run_cmd("sudo grep 'watchdog-timeout' %s"
                                         % timer_location).split("=")[1]
    time_for_reset = time_for_reset.strip()

    return time_for_reset


def check_shutdown_state(engines, start_boot_id):
    """
    Returns 0 for good shutdown
    Returns 1 for a system that did not shutdown
    Returns 2 for a system that shutdown but also restarted
    """
    cmd = "cat /proc/sys/kernel/random/boot_id"
    new_boot_id = engines.dut.run_cmd(cmd)

    if new_boot_id == start_boot_id:
        # This means the DUT never actually shutdown
        return 1
    else:
        # This means that the DUT rebooted
        return 2


@pytest.mark.cumulus_only
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_platform_port_amount(engines, devices, test_api):
    """
    Validates the actual number of ports is equal to the expected number of ports
    defined in the HW specification for the platform. This test is specific to
    Cumulus Linux.
    Test flow:
       1. nv show platform interface
       2. Parse output to dict
       3. Count the number of ports excluding breakout ports
       4. Validate the actual number of ports is equal to the expected number of ports
    """
    TestToolkit.tested_api = test_api

    output_dictionary = OutputParsingTool.parse_show_all_interfaces_output_to_dictionary(
        Port.show_interface()).get_returned_value()

    # dont count breakout ports
    breakout_ports = {'s1', 's2', 's3'}
    port_amount = 0
    for key in output_dictionary:
        if not any(ele in key for ele in breakout_ports) and key.startswith("swp"):
            port_amount += 1
    assert port_amount == devices.dut.get_ib_ports_num(), f'Found {port_amount} ports, expected {devices.dut.get_ib_ports_num()}'
    log.info(f'Found expected amount of ports {port_amount}')


@pytest.mark.cumulus_only
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_fan_speed_change(engines, devices, test_api, output_format):
    """
    Name: Fan Speed Change
    ===============================================

    Description:
    ===============================================
    This test ensures that when the temperature is increased, the
    system will increase the fan speeds. When the temperature is lowered
    the fans speeds will decrease accordingly.

    Steps:
    ===============================================
    1. Get Original Fan Speeds
    2. Fake (simulate) a Temperature Change
    3. Ensure the fan speeds increase accordingly
    4. Set temperature back to normal.
    5. Endure the fan speeds are reduced.
    """

    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Capture Original Fan Speed"):
        fan_db = {}
        raw_output = platform.environment.fan.show(output_format=output_format)
        field_names = OutputParsingTool.parse_show_output_to_field_names(
            raw_output, output_format=output_format, field_name_dict=devices.dut.fan_prop_auto).get_returned_value()
        ValidationTool.validate_set_equal(field_names, devices.dut.platform_environment_fan_values.keys()
                                          ).verify_result()
        fan_dict = OutputParsingTool.parse_show_output_to_dict(
            raw_output, output_format=output_format, field_name_dict=devices.dut.fan_prop_auto).get_returned_value()
        actual_fan_list = fan_dict.keys()
        ValidationTool.validate_set_equal(actual_fan_list, devices.dut.fan_list + devices.dut.psu_fan_list
                                          ).verify_result()
        for fan in devices.dut.fan_list:
            fan_db[fan] = {}
            fan_db[fan]['speed'] = int(fan_dict[fan]['current-speed'])
            fan_db[fan]['variance'] = int(fan_dict[fan]['current-speed']) * .15
            log.info(f'{fan}: Speed: {fan_db[fan]["speed"]} Variance: {fan_db[fan]["variance"]}')

    with allure.step("Fake Temperature Change"):
        fake_temperature = '70000'
        output = engines.dut.run_cmd('ls -ls /var/run/hw-management/thermal/fan_amb')
        fan_amb = str(re.findall('>\\s+([0-9a-z\\-_/\\.]+)', output)[0])
        output = engines.dut.run_cmd('ls -ls /var/run/hw-management/thermal/port_amb')
        port_amb = str(re.findall('>\\s+([0-9a-z\\-_/\\.]+)', output)[0])
        log.info(f'fan_amb register: {fan_amb} port_amb register: {port_amb}')
        engines.dut.run_cmd(f'sudo bash -c "echo {fake_temperature} > /var/run/hw-management/thermal/port_amb_fake_temp"')
        engines.dut.run_cmd(f'sudo bash -c "echo {fake_temperature} > /var/run/hw-management/thermal/fan_amb_fake_temp"')
        engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/fan_amb')
        engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/port_amb')
        engines.dut.run_cmd('sudo ln -s /var/run/hw-management/thermal/fan_amb_fake_temp /var/run/hw-management/thermal/fan_amb')
        engines.dut.run_cmd('sudo ln -s /var/run/hw-management/thermal/port_amb_fake_temp /var/run/hw-management/thermal/port_amb')

    with allure.step("Check Fan Speed Increased"):
        max_wait_time = 60  # seconds
        sleep_interval = 2  # seconds
        start_time = time.time()
        for fan in devices.dut.fan_list:
            passed = False
            target_speed = int(fan_db[fan]['speed'] + fan_db[fan]['variance'])

            while time.time() - start_time < max_wait_time:
                fan_output = OutputParsingTool.parse_show_output_to_dict(
                    platform.environment.fan.show(fan, output_format=output_format),
                    output_format=output_format
                ).get_returned_value()

                current_speed = int(fan_output['current-speed'])
                if current_speed > target_speed:
                    log.info(f"{fan} fan speed has increased. New speed is {current_speed}, the original speed was {fan_db[fan]['speed']}")
                    passed = True
                    break

                time.sleep(sleep_interval)

            if not passed:
                # Set fake temperature back to real temperature
                engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/fan_amb')
                engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/port_amb')
                engines.dut.run_cmd(f'sudo ln -s {fan_amb} /var/run/hw-management/thermal/fan_amb')
                engines.dut.run_cmd(f'sudo ln -s {port_amb} /var/run/hw-management/thermal/port_amb')
                log.info(f"{fan} fan new speed is {current_speed}, the original speed was {fan_db[fan]['speed']} target speed was {target_speed}")
                assert False, 'Fan speed did not increase after the temperature changed'

    with allure.step("Check Fan Speed Decreased"):
        # Set fake temperature back to real temperature
        engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/fan_amb')
        engines.dut.run_cmd('sudo unlink /var/run/hw-management/thermal/port_amb')
        engines.dut.run_cmd(f'sudo ln -s {fan_amb} /var/run/hw-management/thermal/fan_amb')
        engines.dut.run_cmd(f'sudo ln -s {port_amb} /var/run/hw-management/thermal/port_amb')

        max_wait_time = 60  # seconds
        sleep_interval = 2  # seconds
        start_time = time.time()
        for fan in devices.dut.fan_list:
            passed = False
            target_speed = int(fan_db[fan]['speed'] + fan_db[fan]['variance'])

            while time.time() - start_time < max_wait_time:
                fan_output = OutputParsingTool.parse_show_output_to_dict(
                    platform.environment.fan.show(fan, output_format=output_format),
                    output_format=output_format
                ).get_returned_value()

                current_speed = int(fan_output['current-speed'])
                if current_speed <= target_speed:
                    log.info(f"{fan} fan speed has decreased. New speed is {current_speed}, the original speed was {fan_db[fan]['speed']}")
                    passed = True
                    break

                time.sleep(sleep_interval)

            if not passed:
                log.info(f"{fan} fan new speed is {current_speed}, the original speed was {target_speed} target speed was {target_speed}")
                assert False, 'Fan speed did not decrease after the temperature changed'


@pytest.mark.cumulus_only
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_fan_speed_restart_switchd(engines, devices, test_api, output_format):
    """
        Name: Fan Speed Restart Switchd
        ===============================================
        Description:

        This test ensures that the fan speed goes back to target speed (original speed plus variance)
        Steps:
        ===============================================
        1. Read current fan speed
        2. Restart switchd.services
        4. Poll fans and verify speed returns to target speed within 800 seconds

    """

    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Capture Original Fan Speed"):
        fan_db = {}
        raw_output = platform.environment.fan.show(output_format=output_format)
        field_names = OutputParsingTool.parse_show_output_to_field_names(
            raw_output, output_format=output_format, field_name_dict=devices.dut.fan_prop_auto).get_returned_value()
        ValidationTool.validate_set_equal(field_names, devices.dut.platform_environment_fan_values.keys()
                                          ).verify_result()
        fan_dict = OutputParsingTool.parse_show_output_to_dict(
            raw_output, output_format=output_format, field_name_dict=devices.dut.fan_prop_auto).get_returned_value()
        actual_fan_list = fan_dict.keys()
        ValidationTool.validate_set_equal(actual_fan_list, devices.dut.fan_list + devices.dut.psu_fan_list
                                          ).verify_result()
        for fan in devices.dut.fan_list:
            fan_db[fan] = {}
            fan_db[fan]['speed'] = int(fan_dict[fan]['current-speed'])
            fan_db[fan]['variance'] = int(fan_dict[fan]['current-speed']) * .15
            log.info(f'{fan}: Speed: {fan_db[fan]["speed"]} Variance: {fan_db[fan]["variance"]}')

    with allure.step("Restart watchdog"):
        engines.dut.run_cmd("sudo systemctl reset-failed switchd")
        engines.dut.run_cmd("sudo systemctl restart switchd")

    with allure.step("Check Fan Speeds Return to Normal"):
        max_wait_time = 800  # seconds
        sleep_interval = 5  # seconds
        start_time = time.time()
        for fan in devices.dut.fan_list:
            passed = False
            target_speed = int(fan_db[fan]['speed'] + fan_db[fan]['variance'])
            while time.time() - start_time < max_wait_time:
                fan_output = OutputParsingTool.parse_show_output_to_dict(
                    platform.environment.fan.show(fan, output_format=output_format),
                    output_format=output_format
                ).get_returned_value()

                current_speed = int(fan_output['current-speed'])
                if current_speed <= target_speed:
                    log.info(f'{fan} target speed = {target_speed}, current speed: {current_speed}. The difference is {current_speed - target_speed}')
                    passed = True
                    break

                time.sleep(sleep_interval)

            if not passed:
                log.info(f'Fan speed {current_speed} is not within the original speed + variance: {target_speed}')
                assert False, f'Fan speed did not return to normal for {fan} after switch restart'


# SNMP Testcases


def verify_CUMULUS_SENSOR_MIB(engines, port=None):
    with allure.step("Checking: CUMULUS-SENSOR-MIB::entitySensorObjects"):
        output = HostMethods.host_snmp_walk_v2(engines.dut,
                                               ip_address='localhost',
                                               mib='1.3.6.1.4.1.40310.6',
                                               param='', port=port)

    sensor_obj = ["entPhySensorIndex", "entPhySensorType",
                  "entPhySensorScale", "entPhySensorPrecision",
                  "entPhySensorValue", "entPhySensorOperStatus",
                  "entPhySensorUnitsDisplay", "entPhySensorValueTimeStamp",
                  "entPhySensorValueUpdateRate", "entPhySensorDescr",
                  "entPhySensorMin", "entPhySensorMax", "entPhySensorAlarm",
                  "entPhySensorAdminStatus"]
    with allure.step(f"Check snmpwalk has these OIDs : {sensor_obj} "):
        for sensorobj in sensor_obj:
            if (output.find(sensorobj) == -1):
                log.error(f"Failed: {sensorobj} missing")
                assert False, f"Failed: {sensorobj} missing"

    log.info("Success: CUMULUS-SENSOR-MIB::entitySensorObjects")


def verify_CUMULUS_STATUS_MIB(engines, port=None):
    with allure.step("Checking: CUMULUS-STATUS-MIB::cumulusSystemStatus"):
        output = HostMethods.host_snmp_walk_v2(engines.dut,
                                               ip_address='localhost',
                                               mib='1.3.6.1.4.1.40310.5',
                                               param='', port=port)

    status_obj = ["agentSwitchCpuProcessMemFree",
                  "agentSwitchCpuProcessMemAvailable",
                  "agentSwitchCpuProcessMemTotal",
                  "agentSwitchCpuProcessMemPrecision",
                  "agentSwitchCpuProcessRisingThreshold",
                  "agentSwitchCpuProcessRisingThresholdInterval",
                  "agentSwitchCpuProcessFallingThreshold",
                  "agentSwitchCpuProcessFallingThresholdInterval",
                  "agentSwitchCpuProcessFreeMemoryThreshold",
                  "agentSwitchCpuProcessTotalUtilization",
                  "agentSwitchCpuProcess5SecUtilization",
                  "agentSwitchCpuProcess1minUtilization",
                  "agentSwitchCpuProcess5minUtilization",
                  "agentSwitchCpuUtzPrecision", "agentSwitchCpuCores",
                  "agentSwitchCPUUtzErrorFlag", "agentSwitchCPUUtzErrorMsg",
                  "agentSwitchMemErrorFlag", "agentSwitchMemErrorMsg",
                  "agentSwitchCpuutilizationStatus", "agentSwitchMemStatus"]
    with allure.step(f"Check snmpwalk has these OIDs : {status_obj} "):
        for statusobj in status_obj:
            if (output.find(statusobj) == -1):
                log.error(f"Failed: {statusobj} missing")
                assert False, f"Failed: {statusobj} missing"

    log.info("Success: CUMULUS-SENSOR-MIB::entitySensorObjects")


def obj_index(output, object):
    index = [i for i, s in enumerate(output) if object in s]
    if "STRING" in output[index[0]]:
        object_value = output[index[0]].split('\"')[-2]
    else:
        if object == "agentSwitchCpuProcessMemFree":
            object_value = output[index[0]].split(' ')[-2]
        elif object == "agentSwitchCpuProcessMemTotal":
            object_value = output[index[0]].split(' ')[-2]
        else:
            object_value = output[index[0]].split(' ')[-1]
    return object_value


def verify_CPU_MEMORY_utilization(engines, port=None):

    with allure.step("Checking CPU and Memory utilization status"):
        out = HostMethods.host_snmp_walk_v2(engines.dut,
                                            ip_address='localhost',
                                            mib='1.3.6.1.4.1.40310.5',
                                            param='', port=port)

        out = out.split('\n')

        oneMinUtz = int(obj_index(out, "agentSwitchCpuProcess1minUtilization"))
        CpuutilizationStatus = obj_index(out, "agentSwitchCpuutilizationStatus")
        CPUUtzErrorFlag = obj_index(out, "agentSwitchCPUUtzErrorFlag")
        CPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")
        fullUtz = 100
        freeMem = obj_index(out, "agentSwitchCpuProcessMemFree")
        totalMem = obj_index(out, "agentSwitchCpuProcessMemTotal")
        freeMemPercentage = int(int(freeMem) * 100 / int(totalMem))
        SwitchMemStatus = obj_index(out, "agentSwitchMemStatus")
        SwitchMemErrorFlag = obj_index(out, "agentSwitchMemErrorFlag")
        SwitchCPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")

        with allure.step("Checking CPU utilization status"):
            if oneMinUtz <= fullUtz / 4:
                log.info(f"Current CPU utilization {oneMinUtz} ")
            if CpuutilizationStatus != "normal(3)":
                log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status NORMAL")
                assert False, "Failed: CPU utilization status incorrect"
            if CPUUtzErrorFlag != "noError(0)":
                log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                assert False, "Failed: CPU utilization Error flag incorrect"
            if CPUUtzErrorMsg != "No Error":
                log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz / 4 <= oneMinUtz < fullUtz / 2:
                log.info(f"Current CPU utilization {oneMinUtz} ")
                if CpuutilizationStatus != "warning(4)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status WARNING ")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "noError(0)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz / 2 <= oneMinUtz < fullUtz * 3 / 4:
                log.info(f"Current CPU utilization {oneMinUtz}")
                if CpuutilizationStatus != "alert(5)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "noError(0)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz * 3 / 4 <= oneMinUtz:
                log.info(f"Current CPU utilization {oneMinUtz}")
                if CpuutilizationStatus != "critical(6)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status CRITICAL")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "error(1)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'error(1)' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "CPU Utilization exceeds threshold":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'CPU Utilization exceeds threshol' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"

        with allure.step("Checking Memory utilization status"):
            if freeMemPercentage >= 75:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "normal(3)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status NORMAL ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "noError(0)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 75 > freeMemPercentage >= 50:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "warning(4)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status WARNING ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "noError(0)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 50 > freeMemPercentage >= 25:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "alert(5)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "error(1)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'error(1)' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 25 > freeMemPercentage:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "error(1)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'error(1)' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "Free Memory gone below threshold":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. \
Expected 'Free Memory gone below threshold' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"


def verify_mem_utilization(engines, port=None):
    with allure.step("Checking Memory utilization status"):
        out = HostMethods.host_snmp_walk_v2(engines.dut,
                                            ip_address='localhost',
                                            mib='1.3.6.1.4.1.40310.5',
                                            param='', port=port)
        out = out.split('\n')
        freeMem = obj_index(out, "agentSwitchCpuProcessMemFree")
        totalMem = obj_index(out, "agentSwitchCpuProcessMemTotal")
        freeMemPercentage = int(int(freeMem) * 100 / int(totalMem))
        SwitchMemStatus = obj_index(out, "agentSwitchMemStatus")
        SwitchMemErrorFlag = obj_index(out, "agentSwitchMemErrorFlag")
        SwitchCPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")
        if freeMemPercentage >= 75:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "normal(3)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status NORMAL ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
        if SwitchCPUUtzErrorMsg != "No Error":
            log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
            assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 75 > freeMemPercentage >= 50:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "warning(4)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status WARNING ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error("Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 50 > freeMemPercentage >= 25:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "alert(5)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect. Expected status ALERT ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect. Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 25 > freeMemPercentage:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect. Expected status ALERT ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "error(1)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect. Expected 'error(1)' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "Free Memory gone below threshold":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'Free Memory gone below threshold' \
flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test01_snmp_support_on_EntitySensor_mib(engines, topology_obj):
    """
        Verify snmpwalk(v1/v2) support on Sensor/Status MIB using localhost
        SNMP support should present for Sensor/Status MIB
    """
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify Sensor and Status MIB using localhost v2 snmpwalk"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test02_verify_CPU_MEMORY_utilization(engines):
    """
        Verify Status MIB is showing various CPU and Memory utilization
        states/ErrorFlag using localhost.
        SNMP support should present for various CPU and Memory utilization
        states/ErrorFlag.
    """
    snmp_port = 1
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port, cumulus=True)

    with allure.step("Verify CPU Memory Utilization using localhost v2 snmpwalk"):
        verify_CPU_MEMORY_utilization(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test03_verify_memory_utilization(engines):
    """
        Verify Status MIB is showing various MEM utilization states/ErrorFlag
        using localhost.
        SNMP support should present for various MEM utilization
        states/ErrorFlag.
    """
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify memory utilization using localhost v2 snmpwalk"):
        verify_mem_utilization(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test10_verify_snmp_on_EntitySensorMib_after_snmp_restart(engines):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after snmpd restart
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    snmp_port = 65535
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port, cumulus=True)

    with allure.step("Verify MIBs before SNMP service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)
    with allure.step("Restart SNMP service"):
        cmd1 = "sudo systemctl reset-failed"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd1)
        cmd2 = "sudo systemctl restart snmpd"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After SNMP service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test11_verify_snmp_on_EntitySensorMib_after_networking_restart(engines):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after networking restart
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify MIBs before networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("Restart Networking service"):
        cmd1 = "sudo systemctl restart networking"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd1)
        cmd2 = "sudo systemctl restart snmpd.service"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After Networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test12_verify_snmp_on_EntitySensorMib_after_switch_reboot(engines, devices):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after switch reboot
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    snmp_port = 333
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port,
                                      cumulus=True)

    with allure.step("Verify MIBs before networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("Reboot Dut"):
        engines.dut.run_cmd("sudo reboot")
        DutUtilsTool.wait_on_system_reboot(engines.dut)
        cmd2 = "sudo systemctl restart snmpd.service"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After Networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()

# Commenting out below testcases till there is more common OM alignment
# @pytest.mark.system
# def test_CUMULUS_SNMP_MIB(engines, topology_obj):
#     """
#     Verify that walk includes CUMULUS-RESOURCES-MIB, and CUMULUS-COUNTERS-MIB
#     mibs. CUMULUS-SNMP-MIB is just an anchor.
#     """
#     #skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     #host_engine = engines.ha
#     host_engine = LinuxSshEngine(snmp_host, snmp_host_user, snmp_host_pass)
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     snmp_mib_oids = [
#         'CUMULUS-RESOURCES-MIB',
#         'CUMULUS-COUNTERS-MIB'
#     ]
#     with allure.step("Checking: CUMULUS-SNMP-MIB::cumulusMib"):
#         output = HostMethods.host_snmp_walk_v2(host_engine,
#                                                ip_address=ip_address,
#                                                community='public',
#                                                mib='CUMULUS-SNMP-MIB::cumulusMib')

#         for mib in snmp_mib_oids:
#             if not re.search("{0}.*".format(mib), output):
#                 log.error("Failed: {0} missing".format(mib))
#                 assert False, "Failed: {0} missing".format(mib)

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


# @pytest.mark.system
# def test_ENTITY_MIB(engines, topology_obj):
#     """
#     Verify OIDs under ENTITY-MIB via snmp getnext
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: ENTITY-MIB::entPhysicalDescr"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalDescr')
#         if not re.search(".entPhysicalDescr.*", out):
#             log.error("Failed: entPhysicalDescr missing")
#             assert False, "Failed: entPhysicalDescr missing"
#         log.info("Success: ENTITY-MIB::entPhysicalDescr")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalVendorType"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalVendorType')
#         if not re.search(".entPhysicalVendorType.*%s" % ("SNMPv2-SMI::zeroDotZero"), out):
#             log.error("Failed: entPhysicalVendorType missing or wrong")
#             assert False, "Failed: entPhysicalVendorType missing or wrong"
#         log.info("Success: ENTITY-MIB::entPhysicalVendorType")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalContainedIn"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalContainedIn')
#         if not re.search(".entPhysicalContainedIn.*", out):
#             log.error("Failed: entPhysicalContainedIn missing")
#             assert False, "Failed: entPhysicalContainedIn missing"
#         log.info("Success: ENTITY-MIB::entPhysicalContainedIn")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalClass"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalClass')
#         if not re.search(".entPhysicalClass.*", out):
#             log.error("Failed: entPhysicalClass missing")
#             assert False, "Failed: entPhysicalClass missing"
#         log.info("Success: ENTITY-MIB::entPhysicalClass")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalParentRelPos"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalParentRelPos')
#         if not re.search(".entPhysicalParentRelPos.*", out):
#             log.error("Failed: entPhysicalParentRelPos missing")
#             assert False, "Failed: entPhysicalParentRelPos missing"
#         log.info("Success: ENTITY-MIB::entPhysicalParentRelPos")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalName"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalName')
#         if not re.search(".entPhysicalName.*", out):
#             log.error("Failed: entPhysicalName missing")
#             assert False, "Failed: entPhysicalName missing"
#         log.info("Success: ENTITY-MIB::entPhysicalName")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalHardwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalHardwareRev')
#         if not re.search(".entPhysicalHardwareRev.*", out):
#             log.error("Failed: entPhysicalHardwareRev missing")
#             assert False, "Failed: entPhysicalHardwareRev missing"
#         log.info("Success: ENTITY-MIB::entPhysicalHardwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalFirmwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalFirmwareRev')
#         if not re.search(".entPhysicalFirmwareRev.*", out):
#             log.error("Failed: entPhysicalFirmwareRev missing")
#             assert False, "Failed: entPhysicalFirmwareRev missing"
#         log.info("Success: ENTITY-MIB::entPhysicalFirmwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalSoftwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalSoftwareRev')
#         if not re.search(".entPhysicalSoftwareRev.*%s" % ("Cumulus-linux"), out):
#             log.error("Failed: entPhysicalSoftwareRev missing or wrong")
#             assert False, "Failed: entPhysicalSoftwareRev missing or wrong"
#         log.info("Success: ENTITY-MIB::entPhysicalSoftwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalSerialNum"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalSerialNum')
#         if not re.search(".entPhysicalSerialNum.*", out):
#             log.error("Failed: entPhysicalSerialNum missing")
#             assert False, "Failed: entPhysicalSerialNum missing"
#         log.info("Success: ENTITY-MIB::entPhysicalSerialNum")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalMfgName"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalMfgName')
#         if not re.search(".entPhysicalMfgName.*", out):
#             log.error("Failed: entPhysicalMfgName missing")
#             assert False, "Failed: entPhysicalMfgName missing"
#         log.info("Success: ENTITY-MIB::entPhysicalMfgName")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalAlias"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalAlias')
#         if not re.search(".entPhysicalAlias.*", out):
#             log.error("Failed: entPhysicalAlias missing")
#             assert False, "Failed: entPhysicalAlias missing"
#         log.info("Success: ENTITY-MIB::entPhysicalAlias")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalAssetID"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalAssetID')
#     if not re.search(".entPhysicalAssetID.*", out):
#         log.error("Failed: entPhysicalAssetID missing")
#         assert False, "Failed: entPhysicalAssetID missing"
#     log.info("Success: ENTITY-MIB::entPhysicalAssetID")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalIsFRU"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalIsFRU')
#         if not re.search(".entPhysicalIsFRU.*", out):
#             log.error("Failed: entPhysicalIsFRU missing")
#             assert False, "Failed: entPhysicalIsFRU missing"
#         log.info("Success: ENTITY-MIB::entPhysicalIsFRU")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalMfgDate"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalMfgDate')
#         if not re.search(".entPhysicalMfgDate.*", out):
#             log.error("Failed: entPhysicalMfgDate missing")
#             assert False, "Failed: entPhysicalMfgDate missing"
#         log.info("Success: ENTITY-MIB::entPhysicalMfgDate")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalUris"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalUris')
#         if not re.search(".entPhysicalUris.*", out):
#             log.error("Failed: entPhysicalUris missing")
#             assert False, "Failed: entPhysicalUris missing"
#         log.info("Success: ENTITY-MIB::entPhysicalUris")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_MPD_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Mpd MIB
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Mpd MIB"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.11')
#         oids_list = [
#             'snmpUnknownSecurityModels',
#             'snmpInvalidMsgs',
#             'snmpUnknownPDUHandlers'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Snmp Mpd Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_VACM_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Vacm Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Vacm Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.4.1.8072.1.9')
#         oids_list = [
#             'nsVacmContextMatch',
#             'nsVacmViewName',
#             'nsVacmStorageType',
#             'nsVacmStatus'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Snmp Vacm Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Notification_Log_MIB(engines, topology_obj):
#     """
#     Checking: Notification Log Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Notification Log Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.2.1.92')
#         oids_list = [
#             'nlmConfigGlobalEntryLimit',
#             'nlmConfigGlobalAgeOut',
#             'nlmStatsGlobalNotificationsLogged',
#             'nlmStatsGlobalNotificationsBumped'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Notification Log Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_Target_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Target MIB
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Target MIB"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.12')
#         oids_list = [
#             'snmpTargetSpinLock',
#             'snmpUnavailableContexts',
#             'snmpUnknownContexts'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)
#         log.info("Success: Snmp Target Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_System_MIB(engines, topology_obj):
#     """
#     Checking: SNMPv2-MIB::system
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: SNMPv2-MIB::system"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='SNMPv2-MIB::system')

#         if not re.search(".*sysDescr.*%s.*%s.*" % ("Cumulus-linux", "Linux Kernel"), out):
#             log.error("Failed: sysDescr missing or wrong")
#             assert False, "Failed: sysDescr missing or wrong"

#         if not re.search(".*sysContact.*", out):
#             log.error("Failed: sysContact missing")
#             assert False, "Failed: sysContact missing"

#         snmpname = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['hostname']
#         if not re.search(".*sysName.*%s.*" % (snmpname), out):
#             log.error("Failed: sysName missing or wrong")
#             assert False, "Failed: sysName missing or wrong"

#         if not re.search(".*sysLocation.*", out):
#             log.error("Failed: sysLocation missing")
#             assert False, "Failed: sysLocation missing"

#         log.info("Success: SNMPv2-MIB::system")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_User_Base_Cm_MIB(engines, topology_obj):
#     """
#     Checking: Snmp User Based Cm Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp User Based Cm Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.15')

#         oids_list = [
#             'usmStatsUnsupportedSecLevels',
#             'usmStatsNotInTimeWindows',
#             'usmStatsUnknownUserNames',
#             'usmStatsUnknownEngineIDs',
#             'usmStatsWrongDigests',
#             'usmStatsDecryptionErrors',
#             'usmUserSpinLock',
#             'usmUserSecurityName',
#             'usmUserCloneFrom',
#             'usmUserAuthProtocol',
#             'usmUserAuthKeyChange',
#             'usmUserOwnAuthKeyChange',
#             'usmUserPrivProtocol',
#             'usmUserPrivKeyChange',
#             'usmUserOwnPrivKeyChange',
#             'usmUserPublic',
#             'usmUserStorageType',
#             'usmUserStatus'
#         ]

#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: SNMP-USER-BASED-SM-MIB")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()
