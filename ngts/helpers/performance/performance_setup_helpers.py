import logging
import logging.config
import allure
import os
import json
import pytest
from datetime import datetime
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.constants.constants import BugHandlerConst, CliType
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts
from ngts.helpers.thread_log_filter import redirect_thread_stdout, config_root_logger
from ngts.helpers.custom_catch_exception_thread import CatchExceptionThread, parse_threads_exceptions_at_join
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata, get_perf_test_name
from ngts.helpers.performance.traffic_helpers import validate_bw, validate_tc, validate_counters
from ngts.helpers.performance.topology_helpers import get_dvs_topology_obj, get_nvue_sonic_topology_obj
from ngts.helpers.performance.power_temp_helpers import validate_temperature, validate_power
from ngts.cli_wrappers.dvs.dvs_cli import DvsCli
from ngts.cli_wrappers.nvue.nvue_cli import NvueCli
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple
from collections import namedtuple

logger = logging.getLogger()


# Type alias for validation functions that take Any, float, and List[str] parameters
ValidationFunc = Callable[[Any, float, List[str]], None]


@dataclass
class Validation:
    """
    Represents a validation operation with its function and additional arguments.
    """
    func: ValidationFunc
    extra_args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationConfig:
    """
    Configuration class for managing various validation settings and thresholds.

    Attributes:
        players: Test players configuration
        test_name (str): Name of the test being run
        scenario (str): Test scenario identifier
        chip_type (str): Type of chip being tested
        run_validate_counters (bool): Whether to run counter validations
        samples_params_dict (Dict): Parameters for sampling configuration
        tc_occ_threshold (Dict): Traffic class occupancy threshold
        temperature_threshold (float): Maximum allowed temperature
        bw_threshold (float, optional): Bandwidth threshold
        power_threshold (float, optional): Power consumption threshold
        port_list (List[str], optional): List of ports to validate
        skip_first_counters_iteration (bool): Whether to skip first counter check
        additional_validations (List[Validation], optional): Additional validations to run from test
    """
    players: Any
    test_name: str
    scenario: str
    chip_type: str
    run_validate_counters: bool = True
    samples_params_dict: Dict = field(default_factory=lambda: PerfConsts.SAMPLES_PARAMS)
    tc_occ_threshold: Dict = field(default_factory=lambda: PerfConsts.OCC_TH_DICT)
    temperature_threshold: float = PerfConsts.TEMPERATURE_TH
    bw_threshold: Optional[float] = None
    power_threshold: Optional[float] = None
    port_list: Optional[List[str]] = None
    counters_list: List = field(default_factory=lambda: PerfConsts.COUNTERS)
    skip_first_counters_iteration: Optional[bool] = False
    additional_validations: Optional[List[Validation]] = field(default_factory=dict)

    def get_validations(self) -> Dict[str, Validation]:
        """
        Returns a dictionary of enabled validation configurations.

        Each validation is only included if its corresponding threshold/flag is set.

        Validation is of type (function_pointer, {'name of function argument': function argument value})
        E.G: Validation(validate_counters, {'skip_first_counters_iteration': True})

        Returns:
            Dict[str, Validation]: Dictionary mapping validation names to their configurations
        """
        validations = {
            # Counter validation - checks for drops and other counters (such as POC)
            'counters': Validation(
                validate_counters,
                {'skip_first_counters_iteration': self.skip_first_counters_iteration, 'counters_list': self.counters_list}
            ) if self.run_validate_counters else None,

            # Bandwidth validation - ensures bandwidth meets threshold
            'bandwidth': Validation(
                validate_bw,
                {'bw_threshold': self.bw_threshold}
            ) if self.bw_threshold is not None else None,

            # Traffic class validation - checks occupancy levels
            'tc': Validation(
                validate_tc,
                {'tc_occ_threshold': self.tc_occ_threshold}
            ) if self.tc_occ_threshold is not None else None,

            # Temperature validation - ensures within limits
            'temperature': Validation(
                validate_temperature,
                {'temperature_threshold': self.temperature_threshold}
            ) if self.temperature_threshold is not None else None,

            # Power consumption validation - checks power usage
            'power': Validation(
                validate_power,
                {
                    'players': self.players,
                    'test_name': self.test_name,
                    'chip_type': self.chip_type,
                    'power_threshold': self.power_threshold
                }
            ) if self.power_threshold is not None else None,
        }
        validations.update(self.additional_validations)
        return validations


def apply_test_configuration(players, scenario, conf_args,
                             players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                             step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=players_aliases,
                                           action="apply test configuration",
                                           performance_clis_function_name="apply_configuration_file",
                                           performance_clis_function_args=(scenario, conf_args), step=step)


def configure_mloops(players, step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="configure mloops",
                                           performance_clis_function_name="configure_mloops",
                                           performance_clis_function_args=(), step=step)


def save_base_configuration(players, step="basic_test_configuration - set-up"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                           action="save base configuration",
                                           performance_clis_function_name="save_basic_configuration",
                                           performance_clis_function_args=(players,), step=step)


def restore_basic_configuration(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                step="basic_test_configuration - tear-down"):
    call_performance_function_with_threads(players, players_aliases=players_aliases,
                                           action="restore base configuration",
                                           performance_clis_function_name="restore_basic_configuration",
                                           performance_clis_function_args=(), step=step)


def run_traffic(players, scenario, traffic_jsons, step="Running Traffic - Test body", attach_traffic_json=True):

    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="run traffic",
                                           performance_clis_function_name="run_traffic",
                                           performance_clis_function_args=(scenario, traffic_jsons),
                                           step=step)
    if attach_traffic_json:
        attach_json_traffic_to_allure(players, tg_players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                      traffic_jsons=traffic_jsons)


def attach_json_traffic_to_allure(players, tg_players_aliases, traffic_jsons):
    for alias in tg_players_aliases:
        traffic_json_path = traffic_jsons[alias]
        cli_obj = players[alias]['cli']
        hostname = cli_obj.chassis.get_hostname()
        attach_json_to_allure(traffic_json_path, f'Traffic JSON configuration on {alias} - {hostname}')


def stop_traffic(players, step="Stopping Traffic - Tear down"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="stop traffic",
                                           performance_clis_function_name="stop_traffic",
                                           performance_clis_function_args=(),
                                           step=step)


def validate_traffic_results(players, test_name, scenario, samples_params_dict,
                             players_to_be_validated=PerfConsts.PERF_SETUP_DUT_ALIASES):
    traffic_validation_jsons_list = []
    for player_alias in players_to_be_validated:
        cli_object = players[player_alias]['cli']
        hostname = cli_object.chassis.get_hostname()
        time_now = datetime.now()
        hour_str = time_now.strftime("%H:%M:%S")
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 "traffic_validation_json_files",
                                 scenario, f"{hour_str}_{player_alias}_{hostname}_{test_name}_TrafficValidator.json")
        call_performance_function_with_threads(players, players_aliases=[player_alias],
                                               action="run traffic validator",
                                               performance_clis_function_name="validate_traffic",
                                               performance_clis_function_args=(full_path, samples_params_dict),
                                               step="Test Body")
        traffic_json = attach_json_to_allure(full_path,
                                             f'Traffic Validation JSON results on {player_alias} - {hostname}')
        traffic_validation_jsons_list.append(traffic_json)

        add_test_mongo_metadata(test_name, {MongoDbConsts.VALIDATOR_RESULTS: traffic_json})
    return traffic_validation_jsons_list


def attach_json_to_allure(json_path, attachment_name):
    with open(json_path) as f:
        json_str = f.read()
        allure.attach(json_str, attachment_name, allure.attachment_type.JSON)
        json_obj = json.loads(json_str)
    return json_obj


def run_validation(config: ValidationConfig):
    """
    Executes traffic validation based on the provided configuration.

    Args:
        config (ValidationConfig): Configuration object containing validation settings

    Returns:
        list: List of traffic validation JSON results

    Raises:
        TestIssue: If any validation violations are detected
    """
    with allure.step("Run traffic validation on Json results"):
        # Get traffic validation results for the configured test
        traffic_validation_jsons_list = validate_traffic_results(players=config.players, test_name=config.test_name,
                                                                 scenario=config.scenario,
                                                                 samples_params_dict=config.samples_params_dict)

        # Process each traffic validation JSON result
        for traffic_json in traffic_validation_jsons_list:
            violations_list = []
            skipped_validations = []
            validations = {}

            # Separate enabled and disabled validations from config
            for name, validation in config.get_validations().items():
                if validation is None:
                    # Track disabled/skipped validations
                    skipped_validations.append(name)
                else:
                    # Store enabled validations
                    validations[name] = validation

            # Log validation execution plan
            logger.info(f"Skipped validations: {skipped_validations}\n")
            logger.info(f"Validations to run: {list(validations.keys())}\n")

            for name, validation in validations.items():
                # Run validation function with its extra arguments and collect violations
                validation.func(traffic_json, **(validation.extra_args or {}), violations_list=violations_list)

            if violations_list:
                raise TestIssue("\n".join(violations_list))

        return traffic_validation_jsons_list


def set_ports_admin_state(players, port_list, port_state="up", step="Test Body"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES,
                                           action=f"set ports: {port_list} to {port_state}",
                                           performance_clis_function_name="set_ports",
                                           performance_clis_function_args=(port_list, port_state),
                                           step=step)


def call_performance_function_with_threads(players, players_aliases, action,
                                           performance_clis_function_name,
                                           performance_clis_function_args, step):
    config_root_logger()
    players_aliases_str = ",".join(players_aliases)
    logging.info(f"Start {action} on {players_aliases_str}")
    threads_list = []
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for player_alias in players_aliases:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"[{current_time}] Start {action} on player {player_alias}"):
            performance_method = get_obj_method(player_cli_obj.performance, performance_clis_function_name)
            thread = CatchExceptionThread(target=redirect_thread_stdout,
                                          args=(performance_method,
                                                performance_clis_function_args),
                                          name=player_alias)
            threads_list.append(thread)
    for th in threads_list:
        th.start()
    with allure.step(f"Check {action} on {players_aliases_str} was applied correctly"):
        parse_threads_exceptions_at_join(threads_list, players, step)
    completion_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for player_alias in players_aliases:
        player_cli_obj = players[player_alias]['cli']
        with allure.step(f"[{completion_time}] Action {action} completed on {player_alias}"):
            logging.info(f"Finished {action} on {players_aliases_str}")


def get_obj_method(cli_obj, method_name):
    if hasattr(cli_obj, method_name):
        method = getattr(cli_obj, method_name)
        if callable(method):
            return method
    raise TestIssue(f"Failed to find a callable function with name \"{method_name}\" "
                    f"in {cli_obj.__class__.__name__}")


def skip_test_on_unsupported_os(cli_obj, unsupported_os):
    if unsupported_os == CliType.NVUE and isinstance(cli_obj, NvueCli):
        pytest.skip(f"This test is not supported in {CliType.NVUE}")
    elif unsupported_os == CliType.DVS and isinstance(cli_obj, DvsCli):
        pytest.skip(f"This test is not supported in {CliType.DVS}")
    elif unsupported_os == CliType.SONIC and isinstance(cli_obj, SonicCli):
        pytest.skip(f"This test is not supported in {CliType.SONIC}")


def get_topology_obj(players):
    cli_obj = players['dut']['cli']
    if isinstance(cli_obj, DvsCli):
        return get_dvs_topology_obj(players)
    else:
        return get_nvue_sonic_topology_obj(players)


def get_performance_pytest_test_name(request, is_ipv6):
    """
    Args:
        request: pytest request fixture
        ip: the ip type (IPv4/IPv6)

    Returns:
        the test name with the ip parameter, i.e, test_ar_perf_max_bandwidth[4096-IPv6]
    """
    test_name_with_ip_param = get_perf_test_name(request, is_ipv6)
    return test_name_with_ip_param


def set_allure_title(request, is_ipv6):
    test_name = get_performance_pytest_test_name(request, is_ipv6)
    allure.dynamic.title(test_name)
    return test_name
