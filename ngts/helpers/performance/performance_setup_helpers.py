import logging
import logging.config
import allure
import os
import json
import pytest
from datetime import datetime
from ngts.helpers.general_helper import get_pytest_test_name
from ngts.constants.constants import BugHandlerConst, CliType
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, ValidationConsts
from ngts.helpers.thread_log_filter import redirect_thread_stdout
from ngts.helpers.custom_catch_exception_thread import CatchExceptionThread, parse_threads_exceptions_at_join
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata, get_perf_test_name
from ngts.helpers.performance.traffic_helpers import validate_bw, validate_tc, validate_counters, validate_no_drops_on_tg_ports
from ngts.helpers.performance.performance_counter_helpers import validate_performance_counters
from ngts.helpers.performance.topology_helpers import get_dvs_topology_obj, get_nvue_sonic_topology_obj
from ngts.helpers.performance.power_temp_helpers import validate_temperature, validate_power
from ngts.cli_wrappers.dvs.dvs_cli import DvsCli
from ngts.cli_wrappers.nvue.nvue_cli import NvueCli
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.tools.infra import get_chip_type

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
        players_to_be_validated (List[str], optional): List of player aliases to run validation on.
            Defaults to DUT only. Can be set to TG aliases for traffic generator validation.
    """
    players: Any
    test_name: str
    scenario: str
    chip_type: str
    run_validate_counters: bool = True
    run_validate_no_drops_on_tg_ports: bool = True
    validate_bw_rx: bool = True
    samples_params_dict: Dict = field(default_factory=lambda: PerfConsts.SAMPLES_PARAMS)
    tc_occ_threshold: Dict = field(default_factory=lambda: PerfConsts.OCC_TH_DICT)
    run_validate_performance_counters: bool = False
    allowed_deviation: float = PerfConsts.PERF_COUNTERS_ALLOWED_DEVIATION
    packet_size: Optional[int] = None
    temperature_threshold: float = PerfConsts.TEMPERATURE_TH
    bw_threshold: Optional[float] = None
    power_threshold: Optional[float] = None
    port_list: Optional[List[str]] = None
    ignore_counter_list: List = field(default_factory=list)
    skip_first_counters_iteration: Optional[bool] = False
    additional_validations: Optional[List[Validation]] = field(default_factory=dict)
    players_to_be_validated: List[str] = field(default_factory=lambda: PerfConsts.PERF_SETUP_DUT_ALIASES)

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
                {'skip_first_counters_iteration': self.skip_first_counters_iteration, ValidationConsts.IGNORE_COUNTER_LIST: self.ignore_counter_list}
            ) if self.run_validate_counters else None,

            # Bandwidth validation - ensures bandwidth meets threshold
            'bandwidth': Validation(
                validate_bw,
                {'bw_threshold': self.bw_threshold, 'validate_bw_rx': self.validate_bw_rx}
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

            # Traffic pattern validation - checks for dropped packets on mloop ports
            'traffic_pattern': Validation(
                validate_no_drops_on_tg_ports,
                {'players': self.players}
            ) if self.run_validate_no_drops_on_tg_ports else None,
            'performance_counters': Validation(
                validate_performance_counters,
                {'cli_object': self.players['dut']['cli'],
                 'allowed_deviation': self.allowed_deviation,
                 'packet_size': self.packet_size,
                 'test_name': self.test_name}) if self.run_validate_performance_counters and self.packet_size else None

        }
        validations.update(self.additional_validations)
        return validations


def unsplit_all_ports(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                      step="basic_test_configuration - unsplit_all_ports", parallel_run=True):
    """
    Unsplit all ports on SPC5 before applying test configuration.
    This is needed because SPC5 comes up with ports already split after dvs_start.sh

    Args:
        players (dict): Dictionary containing player information and CLI interfaces
        players_aliases (list): List of player aliases to unsplit. Defaults to PerfConsts.PERF_SETUP_PLAYERS_ALIASES
        step (str): Description of the current setup step
        parallel_run (bool): If True, unsplits in parallel. If False, unsplits sequentially. Defaults to True
    """
    spc5_aliases = []
    try:
        for player_alias in players_aliases:
            switch_attributes = players[player_alias]['attributes'].noga_query_data['attributes']
            chip_type = get_chip_type(switch_attributes)
            if chip_type == "SPC5":
                spc5_aliases.append(player_alias)
    except (KeyError, AttributeError) as e:
        raise TestIssue(f"Could not determine chip_type from topology: {e}")

    if not spc5_aliases:
        return

    logger.info(f"Detected SPC5 - unsplitting all ports on all players: {spc5_aliases}")

    if parallel_run:
        call_performance_function_with_threads(players, players_aliases=spc5_aliases,
                                               action="unsplit all ports",
                                               performance_clis_function_name="unsplit_all_ports",
                                               performance_clis_function_args=(), step=step)
    else:
        for player_alias in spc5_aliases:
            players[player_alias]['cli'].performance.unsplit_all_ports()


def apply_test_configuration(players, scenario, conf_args,
                             players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                             step="basic_test_configuration - apply_test_configuration", parallel_run=True):
    """
    Applies test configuration to multiple players either sequentially (debug mode) or in parallel.

    Args:
        players (dict): Dictionary containing player information and CLI interfaces
        scenario (str): The test scenario to be configured
        conf_args (dict): Configuration arguments to be applied
        players_aliases (list): List of player aliases to configure. Defaults to PerfConsts.PERF_SETUP_PLAYERS_ALIASES
        step (str): Description of the current setup step. Defaults to "basic_test_configuration - set-up"
        parallel_run (bool): If True, applies configuration parallel using threads. If False, applies in sequentially. Defaults to True

    The function either:
    - In debug mode (parallel_run=False): Sequentially applies configuration to each player
    - In normal mode (parallel_run=True): Uses threading to apply configuration to all players in parallel
    """
    unsplit_all_ports(players, players_aliases, parallel_run=parallel_run)

    if parallel_run:
        call_performance_function_with_threads(players, players_aliases=players_aliases,
                                               action="apply test configuration",
                                               performance_clis_function_name="apply_configuration_file",
                                               performance_clis_function_args=(scenario, conf_args), step=step)
    else:
        for player_alias in players_aliases:
            players[player_alias]['cli'].performance.apply_configuration_file(scenario, conf_args)


def configure_mloops(players, validate_mloops=True, step="basic_test_configuration - configure_mloops", parallel_run=True):
    if parallel_run:
        call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                               action="configure mloops",
                                               performance_clis_function_name="configure_mloops",
                                               performance_clis_function_args=(validate_mloops,), step=step)
    else:
        for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            players[player_alias]['cli'].performance.configure_mloops(validate_mloops)


def save_base_configuration(players, step="basic_test_configuration - save_base_configuration"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                           action="save base configuration",
                                           performance_clis_function_name="save_basic_configuration",
                                           performance_clis_function_args=(players,), step=step)


def restore_basic_configuration(players, players_aliases=PerfConsts.PERF_SETUP_PLAYERS_ALIASES,
                                step="Tear down - restore_base_configuration"):
    call_performance_function_with_threads(players, players_aliases=players_aliases,
                                           action="restore base configuration",
                                           performance_clis_function_name="restore_basic_configuration",
                                           performance_clis_function_args=(), step=step)


def dynamic_configuration_helper(players, scenario, performance_parameters, step="basic_test_configuration - dynamic_configuration_helper"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES,
                                           action="dynamic configuration",
                                           performance_clis_function_name="dynamic_configuration_helper",
                                           performance_clis_function_args=(scenario, performance_parameters), step=step)


def run_traffic(players, scenario, traffic_jsons, step="Running Traffic - Test body", attach_traffic_json=True, parallel_run=True):

    if parallel_run:
        call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                               action="run traffic",
                                               performance_clis_function_name="run_traffic",
                                               performance_clis_function_args=(scenario, traffic_jsons),
                                               step=step)
    else:
        for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            players[player_alias]['cli'].performance.run_traffic(scenario, traffic_jsons)
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
                             players_to_be_validated=PerfConsts.PERF_SETUP_DUT_ALIASES,
                             attach_to_allure=True,
                             add_validator_results_to_mongo_db=True):
    traffic_validation_results = []
    for player_alias in players_to_be_validated:
        cli_object = players[player_alias]['cli']
        hostname = cli_object.chassis.get_hostname()
        time_now = datetime.now()
        hour_str = time_now.strftime("%H:%M:%S")
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 "traffic_validation_json_files",
                                 scenario, f"{hour_str}_{player_alias}_{hostname}_{test_name}_TrafficValidator.json")
        os.environ[PerfConsts.TRAFFIC_VALIDATION_JSON_PATH] = full_path
        call_performance_function_with_threads(players, players_aliases=[player_alias],
                                               action="run traffic validator",
                                               performance_clis_function_name="validate_traffic",
                                               performance_clis_function_args=(full_path, samples_params_dict),
                                               step="Traffic Validation - Test Body")
        traffic_json = attach_json_to_allure(full_path,
                                             f'Traffic Validation JSON results on {player_alias} - {hostname}',
                                             attach_to_allure)
        traffic_validation_results.append({
            'player_alias': player_alias,
            'traffic_json': traffic_json
        })

        if add_validator_results_to_mongo_db:
            add_test_mongo_metadata(test_name, {MongoDbConsts.VALIDATOR_RESULTS: traffic_json})
    return traffic_validation_results


def attach_json_to_allure(json_path, attachment_name, attach_to_allure=True):
    if not os.path.exists(json_path):
        raise TestIssue(f"Traffic validation JSON file was not created at expected path: {json_path}. "
                        f"This may indicate that the traffic validator failed to run or the file copy from DUT failed. "
                        f"Check the DUT logs for more details.")
    with open(json_path) as f:
        json_str = f.read()
        if attach_to_allure:
            allure.attach(json_str, attachment_name, allure.attachment_type.JSON)
        json_obj = json.loads(json_str)
    return json_obj


def run_validation(config: ValidationConfig, ignore_violations=False, attach_to_allure=True, add_validator_results_to_mongo_db=True):
    """
    Executes traffic validation based on the provided configuration.

    Args:
        config (ValidationConfig): Configuration object containing validation settings

    Returns:
        tuple: (list of traffic validation results, list of all violations)

    Raises:
        TestIssue: If any validation violations are detected
    """
    with allure.step("Run traffic validation on Json results"):
        # Get traffic validation results for the configured test
        traffic_validation_results = validate_traffic_results(players=config.players, test_name=config.test_name,
                                                              scenario=config.scenario,
                                                              samples_params_dict=config.samples_params_dict,
                                                              players_to_be_validated=config.players_to_be_validated,
                                                              attach_to_allure=attach_to_allure,
                                                              add_validator_results_to_mongo_db=add_validator_results_to_mongo_db)

        # Process each traffic validation JSON result
        all_violations = []

        for result in traffic_validation_results:
            player_alias = result['player_alias']
            traffic_json = result['traffic_json']

            player_violations = []
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
            logging.info(f"[{player_alias}] Skipped validations: {skipped_validations}\n")
            logging.info(f"[{player_alias}] Validations to run: {list(validations.keys())}\n")

            for name, validation in validations.items():
                # Run validation function with its extra arguments and collect violations
                validation.func(traffic_json, **(validation.extra_args or {}), violations_list=player_violations)

            if player_violations:
                player_header = f"Validation failures on {player_alias}:"
                all_violations.append(player_header)
                all_violations.extend([f"  - {violation}" for violation in player_violations])
                all_violations.append("")  # Add empty line for readability

        if all_violations and not ignore_violations:
            raise TestIssue("\n".join(all_violations))

        traffic_validation_jsons_list = [result['traffic_json'] for result in traffic_validation_results]

        return traffic_validation_jsons_list, all_violations


def set_ports_admin_state(players, port_list, port_state="up", step="Test Body - set_ports_admin_state"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_DUT_ALIASES,
                                           action=f"set ports: {port_list} to {port_state}",
                                           performance_clis_function_name="set_ports",
                                           performance_clis_function_args=(port_list, port_state),
                                           step=step)


def set_shaper_on_traffic_gen(players, speed, shaper_value, shaper_profile="default-global", step="Test Body - set_shaper_on_traffic_gen"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="set shaper on traffic gen",
                                           performance_clis_function_name="set_shaper",
                                           performance_clis_function_args=(speed, shaper_value, shaper_profile), step=step)


def call_performance_function_with_threads(players, players_aliases, action,
                                           performance_clis_function_name,
                                           performance_clis_function_args, step):

    players_aliases_str = ",".join(players_aliases)
    logging.info(f"Start {action} on {players_aliases_str}")
    threads_list = []
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for player_alias in players_aliases:
        player_cli_obj = players[player_alias]['cli']
        ip_route = player_cli_obj.performance.retrieve_default_route()
        logger.debug(f"{current_time} Action {action} started on {player_alias}. IP Route: {ip_route}")
        with allure.step(f"[{current_time}] Start {action} on player {player_alias}."):
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
        ip_route = player_cli_obj.performance.retrieve_default_route()
        logger.debug(f"{completion_time} Action {action} completed on {player_alias}. IP Route: {ip_route}")


def get_obj_method(cli_obj, method_name):
    if hasattr(cli_obj, method_name):
        method = getattr(cli_obj, method_name)
        if callable(method):
            return method
    raise TestIssue(f"Failed to find a callable function with name \"{method_name}\" "
                    f"in {cli_obj.__class__.__name__}")


def skip_test_on_unsupported_os(cli_obj, unsupported_os):
    with allure.step(f"Skip test on unsupported OS: {unsupported_os}"):
        if unsupported_os == CliType.NVUE and isinstance(cli_obj, NvueCli):
            pytest.skip(f"This test is not supported in {CliType.NVUE}")
        elif unsupported_os == CliType.DVS and isinstance(cli_obj, DvsCli):
            pytest.skip(f"This test is not supported in {CliType.DVS}")
        elif unsupported_os == CliType.SONIC and isinstance(cli_obj, SonicCli):
            pytest.skip(f"This test is not supported in {CliType.SONIC}")


def skip_test_on_unsupported_chip_type(current_chip_type, unsupported_chip_type):
    if current_chip_type == unsupported_chip_type:
        pytest.skip(f"This test is not supported in {unsupported_chip_type}")


def skip_performance_test_conditionally(condition, skip_message):
    if condition:
        pytest.skip(skip_message)


def get_topology_obj(players):
    cli_obj = players['dut']['cli']
    if isinstance(cli_obj, DvsCli):
        return get_dvs_topology_obj(players)
    else:
        return get_nvue_sonic_topology_obj(players)


def create_acl_dump(players):
    return players[PerfConsts.DUT_ALIAS]['cli'].performance.create_acl_dump()


def create_occ_watermark_dump(players, sonic_mgmt_path, tar_file_name="occ_headroom_per_port.tar.gz",
                              tar_file_system='/tmp'):
    """
    Copy occupancy and watermark data dump from DUT and attach to Allure report.

    Args:
        players: Test players configuration
        sonic_mgmt_path (str): The local path where the tar file will be copied.
        tar_file_name (str, optional): The name of the tar file on the DUT.
                                       Defaults to "occ_headroom_per_port.tar.gz".
        tar_file_system (str, optional): The remote filesystem path where the tar file is located.
                                         Defaults to '/tmp'.

    Returns:
        Path to the copied tar archive file.
    """
    tar_file = players[PerfConsts.DUT_ALIAS]['cli'].performance.get_occ_watermark_per_port_dump(
        sonic_mgmt_path=sonic_mgmt_path,
        tar_file_name=tar_file_name,
        tar_file_system=tar_file_system
    )

    if os.path.exists(tar_file):
        try:
            allure.attach.file(
                source=tar_file,
                name='Occupancy and Watermark Data',
                extension='.tar.gz'
            )
            logger.info(f"Attached occupancy/watermark tar file to Allure report: {tar_file}")
        except Exception as e:
            logger.warning(f"Failed to attach tar file to Allure report: {e}")
    else:
        logger.warning(f"Tar file not found: {tar_file}")

    return tar_file


def create_sdk_dump(players, full_path):
    return players[PerfConsts.DUT_ALIAS]['cli'].performance.create_sdk_dump(full_path)


def configure_incremental_dips_on_tg(players, step="basic_test_configuration - configure_incremental_dips_on_tg"):
    call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                           action="create incremental dips",
                                           performance_clis_function_name="configure_incremental_dips_on_tg",
                                           performance_clis_function_args=(), step=step)


def modify_pg_buffer_for_connected_ports(players, step="Test Body - modify_pg_buffer_for_connected_ports", parallel_run=True):
    """
    Modify PG buffer configuration for connected ports on traffic generators.

    This function expects pg_buffer_configs to already be in conf_args and loaded into conf.json
    on each TG from apply_test_configuration. It simply runs the sys_sdk test that reads
    the configuration and applies it.

    The test modifies only:
    - pipeline_latency_size (from user config)
    - override_default_max_borrowed_delta (always True)
    - max_borrowed_delta (from user config)

    All other values (size, xon, xoff, is_lossy, etc.) are preserved from current configuration.

    Args:
        players: Test players configuration
        step: Description of the current step for allure reporting
        parallel_run: If True, modifies buffers in parallel. If False, modifies sequentially.

    Returns:
        int: Number of TGs where buffer configuration was successfully modified

    Raises:
        TestIssue: If pg_buffer_config is missing or buffer modification fails on any TG
    """
    if parallel_run:
        call_performance_function_with_threads(players, players_aliases=PerfConsts.PERF_SETUP_TG_ALIASES,
                                               action="modify PG buffer for connected ports",
                                               performance_clis_function_name="modify_pg_buffer_for_connected_ports",
                                               performance_clis_function_args=(),
                                               step=step)
        modified_count = len(PerfConsts.PERF_SETUP_TG_ALIASES)
    else:
        modified_count = 0
        for player_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            players[player_alias]['cli'].performance.modify_pg_buffer_for_connected_ports()
            modified_count += 1

    return modified_count


def update_port_group_in_df(port_group_df, port_group_name, port_list):
    """
    Update the port group dataframe with the port list
    :param port_group_df: port group dataframe, i.e [{"port": "1", "port_group_name": "left"}, {"port": "2", "port_group_name": "right"}]
    :param port_group_name: port group name, i.e "left" or "right"
    :param port_list: port list, i.e ["1", "2"]
    :return: port group dataframe, i.e [{"port": "1", "port_group_name": "left"}, {"port": "2", "port_group_name": "left"}, {"port": "3", "port_group_name": "right"}]
    """
    for port in port_list:
        port_group_df.append({ValidationConsts.PORT: port, MongoDbConsts.PORT_GROUP_NAME: port_group_name})
    return port_group_df
