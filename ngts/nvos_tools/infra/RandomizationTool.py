import logging
import string
from random import randint
from typing import MutableSequence, Optional

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from .RegressionConfigurations import Configurations
from .ResultObj import ResultObj
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts, IbInterfaceConsts
from ngts.nvos_constants.constants_nvos import SystemConsts, PlatformConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
import random
from ngts.tools.test_utils import allure_utils as allure
import datetime as dt
from datetime import timedelta, datetime

logger = logging.getLogger()


class RandomizationTool:

    @staticmethod
    def select_random_port(dut_engine=None, requested_ports_state=NvosConsts.LINK_STATE_UP,
                           requested_ports_logical_state=None, requested_ports_type="ib"):
        """
        Select and return a random port
        :param requested_ports_state: required port state
        :param dut_engine: ssh dut engine.
        :param requested_ports_type: the state of all selected ports should be - requested_ports_type
        :return: Port object in returned_value of ResultObject
        """
        if not dut_engine:
            dut_engine = TestToolkit.engines.dut

        result_obj = RandomizationTool.select_random_ports(dut_engine=dut_engine,
                                                           requested_ports_state=requested_ports_state,
                                                           requested_ports_type=requested_ports_type,
                                                           requested_ports_logical_state=requested_ports_logical_state,
                                                           num_of_ports_to_select=1)
        if result_obj.result:
            result_obj.returned_value = result_obj.returned_value[0]
        return result_obj

    @staticmethod
    def select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_UP,
                            requested_ports_type=IbInterfaceConsts.IB_PORT_TYPE,
                            requested_ports_logical_state=None,
                            num_of_ports_to_select=1, port_requirements_object=None, dut_engine=None):
        """
        Select and return list of random ports
        if num_of_ports_to_select is 0, all relevant ports will be selected
        :param requested_ports_state: the state of all selected ports should be - requested_ports_state
        :param requested_ports_type: the state of all selected ports should be - requested_ports_type
        :param num_of_ports_to_select: number of ports to select
        :param port_requirements_object: PortRequirements object
        :param dut_engine: ssh dut engine
        :return: a list of Port objects in returned_value of ResultObject
        """
        with allure.step('Choose {num_of_ports_to_select} random ports with provided requirements'.format(
                num_of_ports_to_select=num_of_ports_to_select)):

            if not dut_engine:
                logging.info('Using engine object which updated in TestToolkit')
                dut_engine = TestToolkit.engines.dut

            result_obj = ResultObj(False, "")

            logging.info("Verify the number of ports to select is valid")
            if num_of_ports_to_select < 0:
                result_obj.info = "number of ports to select is invalid"
                return result_obj

            logging.info("Verify the provided port state is legal (up/down only)")
            if requested_ports_state and requested_ports_state != NvosConsts.LINK_STATE_UP and \
                    requested_ports_state != NvosConsts.LINK_STATE_DOWN:
                result_obj.info = "Provided an invalid port state"
                return result_obj

            logging.info("Update port requirements object")
            if not port_requirements_object:
                port_requirements_object = PortRequirements()
            port_requirements_object.set_port_state(requested_ports_state)
            port_requirements_object.set_port_type(requested_ports_type)
            port_requirements_object.set_port_logical_state(requested_ports_logical_state)

            logging.info("Get a list of relevant ports")
            all_relevant_ports = Port.get_list_of_ports(dut_engine, port_requirements_object)

            if len(all_relevant_ports) == 0:
                result_obj.info = f"Ports with provided parameters were not found: {port_requirements_object}"
                return result_obj

            if num_of_ports_to_select == 0:
                logging.info("All relevant ports will be selected")
                num_of_ports_to_select = len(all_relevant_ports)

            if len(all_relevant_ports) < num_of_ports_to_select:
                result_obj.info = (f"There are only {len(all_relevant_ports)} relevant ports but requested to select " +
                                   f"{num_of_ports_to_select} ports. {port_requirements_object}")
                return result_obj

            result_obj.returned_value = []
            for i in range(0, num_of_ports_to_select):
                selected_port = random.choice(all_relevant_ports)
                result_obj.returned_value.append(selected_port)
                logging.info("selected port: {selected_port}".format(selected_port=selected_port.name))
                with allure.step("selected port: {selected_port}".format(selected_port=selected_port.name)):
                    all_relevant_ports.remove(selected_port)

            result_obj.result = True
        allure.attach("Selected items", str(result_obj.returned_value))
        return result_obj

    @staticmethod
    def get_random_active_port(number_of_values_to_select=1, port_type=IbInterfaceConsts.IB_PORT_TYPE):
        list_of_ports = Port.get_list_of_active_ports(port_type)
        if number_of_values_to_select == 0:
            return ResultObj(True, "", list_of_ports)
        return RandomizationTool.select_random_values(list_of_ports, None, number_of_values_to_select)

    @staticmethod
    def get_random_traffic_port(engine: Optional[ProxySshEngine] = None, data_rate=None) -> ResultObj:
        engine = engine or TestToolkit.engines.dut
        data_rate = data_rate or TestToolkit.devices.dut.supported_ib_speeds[-1]
        str_list_of_ports = Configurations.ports_by_rate[data_rate].get(engine.ip)
        list_of_ports = []
        if str_list_of_ports:
            for port_name in str_list_of_ports:
                list_of_ports.append(Port(port_name, "", ""))
        else:
            list_of_ports = Port.get_list_of_active_ports()
            list_of_ports = list(port for port in list_of_ports if
                                 port.name.startswith("sw1p") or port.name.startswith("sw2p") or
                                 port.name.startswith("swA1p") or port.name.startswith("swA2p"))

        return RandomizationTool.select_random_values(list_of_ports, None, 1)

    @staticmethod
    def select_random_value(list_of_values, forbidden_values=None) -> ResultObj:
        """
        Select a random value from provided list of values.
        * user can also specify which values shouldn't be chosen (using 'forbidden_values' parameter).
        :param list_of_values: list of values to select from
        :param forbidden_values: forbidden values that should not be selected
        :return: A random value from the list
        """
        result_obj = RandomizationTool.select_random_values(list_of_values, forbidden_values, 1)
        if result_obj.result:
            result_obj.returned_value = result_obj.returned_value[0]
        return result_obj

    @staticmethod
    def select_random_values(list_of_values, forbidden_values=None, number_of_values_to_select=1,
                             allow_repetitions=False) -> ResultObj:
        """
        Select random values from provided list of values.
        * user can also specify which values shouldn't be chosen (using 'forbidden_values' parameter).
        :param list_of_values: list of values to select from
        :param forbidden_values: list of forbidden values that should not be selected
        :param number_of_values_to_select: number of values to select
        :param allow_repetitions: if True then the same value can appear multiple times in the result
        :return: list of random selected values
        """
        with allure.step('Select random values from provided list of values'):
            list_of_values = list_of_values.copy()
            forbidden_values = None if forbidden_values is None else forbidden_values.copy()

            result_obj = ResultObj(False, "")
            list_of_values_to_select_from = list_of_values

            if not list_of_values:
                result_obj.info = "the list of values to select from is empty"
                return result_obj

            if number_of_values_to_select <= 0:
                result_obj.info = "number of values to select is invalid"
                return result_obj

            removed_values = []
            if forbidden_values:
                for value in forbidden_values:
                    if value in list_of_values_to_select_from:
                        list_of_values_to_select_from.remove(value)
                        removed_values.append(value)

            if len(list_of_values_to_select_from) == number_of_values_to_select:
                result_obj.returned_value = list_of_values_to_select_from
                result_obj.result = True
                return result_obj

            if not allow_repetitions and len(list_of_values_to_select_from) < number_of_values_to_select:
                result_obj.info = "The number of values to select is more then the number of values in the list"
                return result_obj

            result_obj.returned_value = []
            for i in range(0, number_of_values_to_select):
                selected_value = random.choice(list_of_values_to_select_from)
                result_obj.returned_value.append(selected_value)
                logging.info("selected value: {selected_value}".format(selected_value=selected_value))
                allure.step("selected value: {selected_value}".format(selected_value=selected_value))
                if not allow_repetitions:
                    list_of_values_to_select_from.remove(selected_value)

            result_obj.result = True
        allure.attach("Selected items", str(result_obj.returned_value))
        return result_obj

    @staticmethod
    def random_list(count, sum):
        """
            generate a list of m random non-negative integers whose sum is n
        :param count:
        :param sum: the
        :return:
        """
        arr = [0] * count
        for i in range(sum):
            arr[randint(0, sum) % count] += 1
        allure.attach("Selected items", str(arr))
        return arr

    @staticmethod
    def get_random_string(length, ascii_letters=string.ascii_lowercase):
        """
            return random string
        :param length: the length of the random string
        :param ascii_letters: which letters can be in the string
        :return: random string from the ascii_letters and of the given length
        """
        result_str = ''.join(random.choice(ascii_letters) for i in range(length))
        return result_str

    @staticmethod
    def select_random_datetime(min_datetime=SystemConsts.MIN_SYSTEM_DATETIME, max_datetime=SystemConsts.MAX_SYSTEM_DATETIME, forbidden_datetimes=[]):
        """
        @summary:
            Selects a random date & time between two given date-time values.
            All date-time values (parameters and returned value) are strings in the format 'YYYY-MM-DD hh:mm:ss'
        @param min_datetime: minimum date-time value
        @param max_datetime: maximal date-time value
        @param forbidden_datetimes: list of date-time values (strings) that should not be picked
        @return: ResultObj object containing a random date-time between min and max
        """
        with allure.step("Select date-time from given range of date-times"):
            min_dt_obj, max_dt_obj = datetime.fromisoformat(min_datetime), datetime.fromisoformat(max_datetime)
            # validate parameters
            if min_dt_obj > max_dt_obj:
                return ResultObj(False, "Invalid datetime range")
            if min_datetime == max_datetime and min_datetime in forbidden_datetimes:
                return ResultObj(False, "Can't pick a random date-time between {dt} and {dt} and shouldn't be {dt}".format(dt=min_datetime))
            diff_timedelta_obj = max_dt_obj - min_dt_obj
            diff_in_seconds = diff_timedelta_obj.total_seconds()
            random_datetime = None
            while random_datetime is None or random_datetime in forbidden_datetimes:
                # randomize delta for the new random time
                random_delta_in_seconds = random.randint(0, int(diff_in_seconds))
                random_delta_timedelta_obj = timedelta(seconds=random_delta_in_seconds)
                # create the random date-time by adding the delta to the min_datetime
                random_dt_obj = min_dt_obj + random_delta_timedelta_obj
                random_datetime = random_dt_obj.strftime("%Y-%m-%d %H:%M:%S")

        allure.attach(str(random_datetime))
        return ResultObj(True, "Picked random date-time success", random_datetime)

    @staticmethod
    def select_random_time(forbidden_time_values=[]):
        """
        @summary:
            Selects a random time in a day.
            all time values (the returned one and given forbidden ones) are strings in the format 'hh:mm:ss'
        @param forbidden_time_values: list of time values (strings) that should not be picked
        @return: ResultObj object containing a random time
        """
        with allure.step("Select a random time"):
            # select random date-time and remove the date
            base_date = "2023-01-01 "
            result_obj = RandomizationTool.select_random_datetime(min_datetime=base_date + "00:00:00",
                                                                  max_datetime=base_date + "23:59:59",
                                                                  forbidden_datetimes=[base_date + t for t in forbidden_time_values])
            if result_obj.result:
                result_obj.returned_value = result_obj.returned_value.split(' ')[1]
            return result_obj

    @staticmethod
    def select_random_date(min_date=SystemConsts.MIN_SYSTEM_DATE, max_date=SystemConsts.MAX_SYSTEM_DATE, forbidden_dates=[]):
        """
        @summary:
            Selects a random date between two given dates.
            All date values (parameters and returned value) are strings in the format 'YYYY-MM-DD'
        @param min_date: minimum date value
        @param max_date: maximal date value
        @param forbidden_dates: list of date values (strings) that should not be picked
        @return: ResultObj object containing a random date between min and max
        """
        with allure.step("Select date from given range of date"):
            min_date_obj, max_date_obj = dt.date.fromisoformat(min_date), dt.date.fromisoformat(max_date)
            # validate parameters
            if min_date_obj > max_date_obj:
                return ResultObj(False, "Invalid date range")
            if min_date == max_date and min_date in forbidden_dates:
                return ResultObj(False, "Can't pick a random date between {dt} and {dt} and shouldn't be {dt}".format(dt=min_date))
            diff_timedelta_obj = max_date_obj - min_date_obj
            diff_in_seconds = diff_timedelta_obj.total_seconds()
            random_date = None
            while random_date is None or random_date in forbidden_dates:
                # randomize delta for the new random time
                random_delta_in_seconds = random.randint(0, int(diff_in_seconds))
                random_delta_timedelta_obj = timedelta(seconds=random_delta_in_seconds)
                # create the random date-time by adding the delta to the min_datetime
                random_date_obj = min_date_obj + random_delta_timedelta_obj
                random_date = random_date_obj.strftime("%Y-%m-%d")

            return ResultObj(True, "Picked random date success", random_date)

    @staticmethod
    def select_random_transceiver(transceivers_output, field_name, expected_value, number_of_transceiver_to_select=1):
        """
        :summary: select random transceiver with a specific cable type
        :param transceivers_output:
        :param expected_value:
        :param number_of_transceiver_to_select:
        :return:
        """
        with allure.step("Select {} random transceiver with {}: {}".format(number_of_transceiver_to_select, field_name, expected_value)):
            transceivers_list = []
            for transceiver, transceiver_data in transceivers_output.items():
                if field_name in transceiver_data and transceiver_data[field_name] == expected_value:
                    transceivers_list.append(transceiver)

            if len(transceivers_list) < number_of_transceiver_to_select:
                return ResultObj(False, "Failed to select {} {} transceivers. Only {} were found".format(number_of_transceiver_to_select, expected_value, len(transceivers_list)))

        output = random.sample(transceivers_list, number_of_transceiver_to_select)
        allure.attach("Selected transceivers", str(output))
        return ResultObj(True, "picked transceivers success", output)

    @staticmethod
    def select_random_asics(dut_device=None, forbidden_values=None, how_many=1) -> ResultObj:
        """Returns a list of distinct numbers between 1 and asic_amount."""
        asic_amount = (dut_device or TestToolkit.devices.dut).asic_amount
        return RandomizationTool.select_random_values(list(range(1, asic_amount + 1)), forbidden_values, how_many)

    @staticmethod
    def shuffle_in_place(items: MutableSequence) -> None:
        random.shuffle(items)
        allure.attach("Shuffle result", str(items))
