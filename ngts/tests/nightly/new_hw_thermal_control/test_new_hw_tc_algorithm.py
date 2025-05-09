import allure
import logging
import pytest
import random
import os
import time
import operator
import re


from ngts.helpers.new_hw_thermal_control_helper import TC_CONST, MockSensors, SENSOR_DATA, \
    verify_pwd_and_rpm_are_expected_value, get_sensor_temperature_file_name, get_sensor_err_test_data, get_pwm, \
    get_temperature_digit, SENSOR_ERR_TEST_DATA, compare_pwd_with_expected_value, verify_rpm_is_expected_value
from ngts.common.checkers import is_ver1_greater_or_equal_ver2

logger = logging.getLogger()


class TestNewTc:

    @pytest.fixture(autouse=True)
    def setup_param(self, topology_obj, engines, cli_objects, interfaces, players):
        self.cli_objects = cli_objects
        self.dut_engine = engines.dut
        self.topology_obj = topology_obj

    @pytest.fixture(autouse=False)
    def hide_hw_management_sync_service(self):
        """
        The hw_management_sync service will update the thermal sensor value,
        specially since the hw-mgmt V.7.0040.4007, the minimal driver has been
        disabled on platforms SPC2-SPC5.
        This fixture is to hide the hw_management_sync service to avoid the thermal
        sensor value being updated by the hw_management_sync service. test_temperature_sweep
        needs to mock the temperature value so we need to stop the hw_management_sync service
        before the test and start it after the test.
        """
        self.dut_engine.run_cmd("sudo systemctl stop hw-management-sync")
        yield
        self.dut_engine.run_cmd("sudo systemctl start hw-management-sync")

    @allure.title('test temperature sweep')
    @pytest.mark.usefixtures("hide_hw_management_sync_service")
    def test_temperature_sweep(self, request, get_dut_supported_sensors_and_tc_config, platform_params):
        """
        This test is to verify temperature sweep
        1. Mock tested sensor temperature to val_min/10000-1. Wait poll_time secs
        2. Mock temperature increase
            Increase sensor temperature value with step 10
            Calculate the expected PWM with below formula:
            expected_pwm = pwm_min + ((new_temp - val_min)/(val_max-val_min)) * (pwm_max - pwm_min)
            Wait poll_time secs, and get current system PWM by reading /var/run/hw-management/thermal/pwm1
            Check current_system_pwm >= expected_pwm
            Check FAN speed is set to correct range
            Iterate the above steps until temperature is over val_max
        3. Mock temperature decrease
            decrease sensor temperature value with step 10
            Calculate the expected PWM with below formula:
            expected_pwm = pwm_min + ((new_temp - val_min)/(val_max-val_min)) * (pwm_max - pwm_min)
            Wait poll_time secs, and get current system PWM
            Check current_system_pwm >= expected_pwm
            Check FAN speed is set to correct range
            Iterate the above steps until temperature is under val_min
        4. Repeat step 1~ step 5 for following sensors or randomly select one sensor to test
           (Need to check if dut includes this sensor. if no, skip testing this sensor):
            asic
            cpu-pack
            voltmon1_temp_input
            module{X}
            ambient
            Gearbox
        """
        sensor_temperature_test_list, tc_config_dict = get_dut_supported_sensors_and_tc_config
        sensor_type = request.config.getoption("--sensor_type")
        if sensor_type == "all":
            tested_sensors = sensor_temperature_test_list
        elif sensor_type in sensor_temperature_test_list:
            tested_sensors = [sensor_type]
        else:
            tested_sensors = [random.choice(sensor_temperature_test_list)]

        logger.info(f"The sensors tested are: {tested_sensors}")

        # For IM enabled setup, 'module' and 'asic' sensor test are need be skipped as it created by kernel sysfs and
        # from user space we don't have permission to write it
        if tested_sensors[0] in ['module', 'asic'] and self.cli_objects.dut.im.is_im_enabled():
            pytest.skip(f"Skip mock temperature for sensor {tested_sensors} as it is not supported in IM enabled setup")

        def mock_temp_and_check(file_path, temperature):
            mock_sensor.mock_temperature(file_path, temperature)
            verify_pwd_and_rpm_are_expected_value(mock_sensor, tc_config_dict, sensor_type, temperature)

        for sensor_type in tested_sensors:
            with MockSensors(self.dut_engine, self.cli_objects) as mock_sensor:
                file_path_list = get_sensor_temperature_file_name(sensor_type, platform_params)
                dev_parameters_name = SENSOR_DATA[sensor_type]['dev_parameters_name']

                temperature_max = get_temperature_digit(
                    tc_config_dict['dev_parameters'][dev_parameters_name]['val_max'])
                temperature_min = get_temperature_digit(
                    tc_config_dict['dev_parameters'][dev_parameters_name]['val_min'])
                logger.info(
                    f"\n sensor_type:{sensor_type}, \n sensor_path: {file_path_list},"
                    f" \n dev_parameters_name :{dev_parameters_name},"
                    f" \n temp max:{temperature_max}, \ntemp min: {temperature_min}")

                tested_temperature_file = file_path_list[0]
                with allure.step(f'Mock {tested_temperature_file} to  temperature_min:{temperature_min}'):
                    mock_temp_and_check(tested_temperature_file, temperature_min)

                if sensor_type == "ambient":
                    # for ambient, we have port_amb and fan_amb,
                    # pwm will be changed based on the min(port_amb_temp, fan_amb_temp).
                    # to test pwm will be changed based the tested amb, set the temp of the other one amb to max
                    with allure.step(f'For ambient, Mock {file_path_list[1]} to  temperature_max:{temperature_max}'):
                        mock_sensor.mock_temperature(file_path_list[1], temperature_max)

                # 10 degree centigrade
                temp_change_step = 10000
                temperature = temperature_min + temp_change_step
                with allure.step(
                        f'Mock temperature of {tested_temperature_file} increase from {temperature_min} to {temperature_max} with step {temp_change_step}'):
                    while temperature <= temperature_max:
                        with allure.step(f'mock {sensor_type} temperature increase to {temperature}'):
                            mock_temp_and_check(tested_temperature_file, temperature)
                            temperature += temp_change_step

                temperature = temperature_max - temp_change_step
                with allure.step(
                        f'Mock temperature of {tested_temperature_file} decrease from {temperature_max} to {temperature_min} with step {temp_change_step}'):
                    while temperature >= temperature_min:
                        with allure.step(f'mock {sensor_type} temperature decrease to {temperature}'):
                            mock_temp_and_check(tested_temperature_file, temperature)
                            temperature -= temp_change_step

    @pytest.mark.parametrize("sensor_err_type", SENSOR_ERR_TEST_DATA.keys())
    @allure.title('test sensor errors')
    def test_sensor_errors(self, get_dut_supported_sensors_and_tc_config, sensor_err_type):
        """
        This test is to verify sensor errors behaviors
        1. Mock the temperature for tested sensors to a minimum(30c)
        2. Inject errors by writing err values to corresponding static files
        3. Check expected PWM is changed to the value from Dmin table. We can get the Dim table from /var/run/hw-management/config/tc_config.json
        4. Check FAN speed is set to correct range
        5. Repeat step 1 ~ step 4 for below scenarios
            FAN present err (FAN not present)
              e.g. echo 0 >> /run/hw-management/thermal/fan1_status
            FAN direction err (One or more FANs have opposite dir)
              e.g. echo 0 >> /run/hw-management/thermal/fan1_dir
            FAN tacho err (Current FAN RPM is not correct and does not correspond to expected)
              e.g. echo 10 >> /run/hw-management/thermal/fan1_speed_set
            PSU present err (PSU not present)
              e.g. echo 0 >> /run/hw-management/thermal/psu1_status
            PSU FAN direction err (PSU FAN dir is opposite to system FAN)
              e.g. echo 0 >> /run/hw-management/thermal/psu1_fan_dir
            Thermal sensor reading error (cpu_pack, amb, module) file missing
              remove the corresponding files
            Thermal sensor reading error (cpu_pack, amb, module) file including incompatible value (reading null/none/wrong format numeric value from the file)
              e.g. echo an incompatible value into the corresponding files
        """
        _, tc_config_dict = get_dut_supported_sensors_and_tc_config

        with allure.step(f"Mock {sensor_err_type}"):
            with MockSensors(self.dut_engine, self.cli_objects) as mock_sensor:
                if sensor_err_type.startswith("psu_err") and SENSOR_DATA["psu"]["total_number"] < 2:
                    pytest.skip("Only one psu, skipping this test")
                sensor_err_file, expected_pwm, mock_value = get_sensor_err_test_data(
                    sensor_err_type, mock_sensor, tc_config_dict, self.cli_objects)
                sensor_read_error_type = None
                if "sensor_read_error" == sensor_err_file:
                    sensor_read_error_type = random.choice(SENSOR_ERR_TEST_DATA["sensor_read_error"])
                    logging.info(f"sensor read error type is {sensor_read_error_type}")
                if "missing_file" == sensor_read_error_type:
                    with allure.step(f"Mock remove {sensor_err_file}"):
                        mock_sensor.remove_file(sensor_err_file)
                else:
                    with allure.step(f"Mock {sensor_err_file} with {mock_value}"):
                        mock_sensor.mock_value(sensor_err_file, mock_value)
                compare_pwd_with_expected_value(mock_sensor, expected_pwm, operator.ge)
                verify_rpm_is_expected_value(mock_sensor, tc_config_dict)

    @allure.title('test sensor blacklist')
    def test_sensor_blacklist(self, get_dut_supported_sensors_and_tc_config):
        """
        This test is to verify sensor blacklist function
        1. Add asic sensor to blacklist
           Touch /var/run/hw-management/thermal/asic_blacklist
           echo 1 > /var/run/hw-management/thermal/asic_blacklist
        2. Mock asic temperature to val_max
        3. Check PWM is not PWM_MAX(100).
        """
        _, tc_config_dict = get_dut_supported_sensors_and_tc_config
        # Due to bug of https://redmine.mellanox.com/issues/3537782, change asic_blacklist to asic1_blacklist
        asic_blacklist_file = f"{TC_CONST.HW_THERMAL_FOLDER}/asic1_blacklist"
        try:
            with MockSensors(self.dut_engine, self.cli_objects) as mock_sensor:
                pwm_before_adding_blacklist = get_pwm(mock_sensor)
                if "asic" in list(tc_config_dict["dev_parameters"].keys()):
                    asci_dev_param_info = tc_config_dict["dev_parameters"]["asic"]
                else:
                    pytest.skip('"asic" sensor does not exist')
                pwm_max = asci_dev_param_info["pwm_max"]
                with allure.step(f'Verify pwm {pwm_before_adding_blacklist} before adding blacklist is smaller than max pwm {pwm_max}'):
                    if pwm_before_adding_blacklist >= pwm_max:
                        pytest.skip(
                            f"pwm {pwm_before_adding_blacklist} before adding asic to blacklist is ge max pwm {pwm_max},"
                            f" skipping this test")
                with allure.step(f'Create {asic_blacklist_file}, and enable it'):
                    self.dut_engine.run_cmd(f"sudo touch {asic_blacklist_file}")
                    self.dut_engine.run_cmd(f"sudo chown admin {asic_blacklist_file}")
                    self.dut_engine.run_cmd(f"sudo echo 1 > {asic_blacklist_file}")
                with allure.step(f'Mock asic temperature to val_max'):
                    with MockSensors(self.dut_engine, self.cli_objects) as mock_sensor:
                        poll_time = asci_dev_param_info["poll_time"]
                        asci_sensor_file = os.path.join(TC_CONST.HW_THERMAL_FOLDER, "asic")
                        mock_temp = get_temperature_digit(asci_dev_param_info["val_max"])
                        logger.info(f"mock_temperature: {mock_temp} \n poll_time:{poll_time} \n pwm_max:{pwm_max}\n")
                        mock_sensor.mock_temperature(asci_sensor_file, mock_temp)

                        time.sleep(poll_time + TC_CONST.PWM_GROW_TIME)
                        pwm_curr = get_pwm(mock_sensor)
                        assert pwm_curr < pwm_max, f"" \
                            f"sensor blacklist doesn't work, pwm_curr:{pwm_curr} >= pwm_max {pwm_max}," \
                            f"pwm_before_adding_blacklist is:{pwm_before_adding_blacklist} "
        except Exception as err:
            raise err
        finally:
            with allure.step(f'Remove {asic_blacklist_file}'):
                self.dut_engine.run_cmd(f"sudo rm -f {asic_blacklist_file}")

    @allure.title('test check tc_config link')
    def test_check_tc_config_link(self, platform_params):
        """
        This tests is to check tc_config is linked to the correct file
        """
        # For some platforms, tc_config is linked to the file with the specific hwsku name
        # The below map includes these info
        special_hwsku_to_tc_config_map = {"ACS-MSN4410": "msn4700"}

        with allure.step("Get sku info"):
            hwsku = platform_params.hwsku
            reg_hwsku = r'(ACS|Mellanox)-(?P<hwsku>\w+).*'
            sku_res = re.search(reg_hwsku, hwsku)
            if sku_res:
                expected_hwsku_in_tc_config_file = sku_res.groupdict()['hwsku']
            else:
                assert False, f" Does not find sku name in {platform_params.hwsku}"
            expected_hwsku_in_tc_config_file = special_hwsku_to_tc_config_map.get(hwsku,
                                                                                  expected_hwsku_in_tc_config_file)
            expected_hwsku_in_tc_config_file = expected_hwsku_in_tc_config_file.replace('_', '')

        # In case platform name exists in NO_TC_CONFIG_LINK_PLATFORMS list, it means there is no link to TC_CONFIG_FILE,
        # and therefore just verifying config file contains the hwsku name. otherwise checking the tc_config link.
        if expected_hwsku_in_tc_config_file in TC_CONST.PLATFORMS_WITHOUT_TC_CONFIG_LINK:
            with allure.step(f"verify config file contains the hwsku name"):
                tc_config_content = self.dut_engine.run_cmd(f'sudo cat {TC_CONST.TC_CONFIG_FILE}')
                assert expected_hwsku_in_tc_config_file.lower() or \
                    expected_hwsku_in_tc_config_file.replace('QM', 'Q').lower() in tc_config_content, \
                    f"tc_config file should contains hwsku name: {expected_hwsku_in_tc_config_file.lower()}"

        # RM issue 3769500
        current_hw_version = self.cli_objects.dut.hw_mgmt.get_hw_version()
        base_hw_version = "7.0030.2013"
        logger.info(f'current hw_version: {current_hw_version}, base hw_version:{base_hw_version}')
        if is_ver1_greater_or_equal_ver2(current_hw_version, base_hw_version):
            with allure.step(f"Use {TC_CONST.HW_MGMT_THERMAL_FOLDER}/tc_config_*.json file to verify hwsku"):
                cmd = f'ls {TC_CONST.HW_MGMT_THERMAL_FOLDER} | grep -i {expected_hwsku_in_tc_config_file.lower()}.json'
                output = self.dut_engine.run_cmd(cmd)
                assert expected_hwsku_in_tc_config_file.lower() or \
                    expected_hwsku_in_tc_config_file.replace('QM', 'Q').lower() in output.lower(), \
                    "SKU not found in the expected file."
        else:
            with allure.step("Use tc_config link to verify hwsku"):
                tc_config_link = self.dut_engine.run_cmd(f'sudo readlink {TC_CONST.TC_CONFIG_FILE}')
                assert expected_hwsku_in_tc_config_file.lower() in tc_config_link.lower(), \
                    f"tc_config is linked to wrong file. tc_config link:{tc_config_link}, " \
                    f"platform sku: {platform_params.hwsku}"
