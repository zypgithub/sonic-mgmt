import logging
import importlib.util
import threading

logger = logging.getLogger()


class PerformanceHelpers:
    def __init__(self) -> None:
        pass

    def apply_basic_configuration(self, players, engines, scenario):

        dut_cli_object = players['dut']['cli']
        right_tg_cli_object = players['right_tg']['cli']
        path = importlib.util.find_spec("ngts").submodule_search_locations[0]
        dut_full_path = dut_cli_object.general.get_configuration_file_path(path, scenario=scenario, switch_name="dut")
        right_tg_full_path = right_tg_cli_object.general.get_configuration_file_path(path, scenario=scenario, switch_name="right_tg")

        threads_list = []

        thread = threading.Thread(target=dut_cli_object.general.apply_configuration_file, args=(engines.dut, dut_full_path))
        threads_list.append(thread)

        thread = threading.Thread(target=right_tg_cli_object.general.apply_configuration_file, args=(engines.right_tg, right_tg_full_path))
        threads_list.append(thread)

        for th in threads_list:
            th.start()

        for th in threads_list:
            th.join()
