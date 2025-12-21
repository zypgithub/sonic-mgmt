"""
Traffic Validator Tool

This tool provides utilities to verify that traffic tests do not cause
link errors on the switch ports. It includes methods to:
- Get traffic ports from the RegressionConfigurations
- Clear counters before running traffic
- Verify no link errors occurred after traffic
- Capture baseline for PHY detail counters (non-clearable)
- Compare PHY detail counters after traffic to detect changes

Design follows SOLID principles:
- Counter definitions are in device classes (IbSwitch and subclasses)
- This tool queries the device for which counters to check
- New platforms can override _init_link_error_counters() to add counters
"""
import logging
from typing import List, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure

if TYPE_CHECKING:
    from ngts.nvos_tools.Devices.IbDevice import IbSwitch

logger = logging.getLogger()


# PHY detail error counters that cannot be cleared - must use baseline comparison
# These are from 'nv show interface <port> link phy detail'
PHY_DETAIL_ERROR_COUNTERS = [
    'sync-header-error-counter',
    'port-local-physical-errors',
    'port-malformed-packet-errors',
    'plr-rcv-codes-err',
    'plr-rcv-uncorrectable-code',
    'plr-xmit-retry-codes',
    'plr-xmit-retry-events',
    'plr-sync-events',
    'rq-general-error',
    'port-buffer-overrun-errors',
    'port-dlid-mapping-errors',
    'port-vl-mapping-errors',
    'port-looping-errors',
    'port-inactive-discards',
    'port-neighbor-mtu-discards',
    'unintentional-link-down-events',
]


@dataclass
class CounterBaseline:
    """
    Stores baseline counter values for comparison after traffic.

    This is used for counters that cannot be cleared (like PHY detail counters).
    We capture values before traffic and compare after to detect changes.
    """
    port_name: str
    phy_detail_counters: Dict[str, int] = field(default_factory=dict)

    def get_changed_counters(self, current_values: Dict[str, int]) -> Dict[str, tuple]:
        """
        Compare current values with baseline and return changed counters.

        :param current_values: Current counter values
        :return: Dict of counter_name -> (before, after) for counters that changed
        """
        changes = {}
        for counter_name, baseline_value in self.phy_detail_counters.items():
            current_value = current_values.get(counter_name, 0)
            if current_value != baseline_value:
                changes[counter_name] = (baseline_value, current_value)
        return changes


class TrafficErrorCounters:
    """
    Helper class to define default traffic error counter configurations.

    Used by IbSwitch._init_link_error_counters() to set up the default counters.
    Subclasses can extend the dict to add platform-specific counters.
    """

    @staticmethod
    def get_default() -> Dict[str, List[str]]:
        """
        Get the default traffic error counters configuration.

        :return: Dict with 'link' and 'top_level' counter lists
        """
        return {
            # Counters under 'nv show interface <port> counters link'
            'link': list(IbInterfaceConsts.LINK_STATS_QNT3_UNDER_LINK),
            # Counters under 'nv show interface <port> counters'
            'top_level': [
                IbInterfaceConsts.LINK_STATS_IN_ERRORS,
                IbInterfaceConsts.LINK_STATS_OUT_ERRORS,
            ],
        }


class TrafficValidatorTool:
    """
    Tool for validating traffic tests by checking link error counters.

    This tool helps ensure that IB/IPoIB traffic tests do not cause link errors
    on the switch ports. It provides methods to clear counters before traffic
    and verify no errors occurred after traffic.

    Counter definitions come from the device class (IbSwitch.get_traffic_error_counters),
    allowing platform-specific counters to be added by overriding the method.
    """

    @staticmethod
    def get_traffic_ports(engine=None) -> List[Port]:
        """
        Get list of Port objects for traffic ports based on DUT IP.

        Uses RegressionConfigurations.traffic_ports to lookup ports for the DUT.

        :param engine: Optional DUT engine. If not provided, uses TestToolkit.get_engine()
        :return: List of Port objects for traffic ports, or empty list if not configured
        """
        engine = engine or TestToolkit.get_engine()
        port_names = Configurations.traffic_ports.get(engine.ip, [])
        if not port_names:
            logger.warning(f"No traffic ports configured for DUT IP {engine.ip}")
            return []
        logger.info(f"Traffic ports for {engine.ip}: {port_names}")
        return [Port(port_name, "", "") for port_name in port_names]

    @staticmethod
    def clear_traffic_port_counters(engine=None) -> ResultObj:
        """
        Clear counters for all traffic ports on the DUT.

        :param engine: Optional DUT engine. If not provided, uses TestToolkit.get_engine()
        :return: ResultObj indicating success/failure
        """
        engine = engine or TestToolkit.get_engine()
        traffic_ports = TrafficValidatorTool.get_traffic_ports(engine)

        if not traffic_ports:
            return ResultObj(True, info="No traffic ports configured - skipping counter clear")

        with allure.step(f'Clear counters for traffic ports: {[p.name for p in traffic_ports]}'):
            interface = Interface(parent_obj=None)
            port_names = ",".join([p.name for p in traffic_ports])
            result = interface.action_clear_counter_for_interface(
                dut_engine=engine,
                interface_name=port_names
            )
            if result.result:
                logger.info(f"Successfully cleared counters for ports: {port_names}")
            else:
                logger.error(f"Failed to clear counters for ports: {port_names}")
            return result

    @staticmethod
    def get_link_counters(port: Port, engine=None) -> Dict[str, any]:
        """
        Get link counters for a specific port.

        :param port: Port object to get counters for
        :param engine: Optional DUT engine
        :return: Dictionary of counter name to value
        """
        engine = engine or TestToolkit.get_engine()

        # Get counters from 'nv show interface <port> counters link'
        counters_output = port.interface.counters.link.show(dut_engine=engine)
        counters_dict = OutputParsingTool.parse_json_str_to_dictionary(
            counters_output
        ).get_returned_value()

        return counters_dict

    @staticmethod
    def get_top_level_counters(port: Port, engine=None) -> Dict[str, any]:
        """
        Get top-level counters for a specific port.

        :param port: Port object to get counters for
        :param engine: Optional DUT engine
        :return: Dictionary of counter name to value
        """
        engine = engine or TestToolkit.get_engine()

        # Get counters from 'nv show interface <port> counters'
        counters_output = port.interface.counters.show(dut_engine=engine)
        counters_dict = OutputParsingTool.parse_json_str_to_dictionary(
            counters_output
        ).get_returned_value()

        return counters_dict

    @staticmethod
    def _parse_counter_value(counter_value) -> int:
        """
        Parse counter value to integer, handling string representations.

        :param counter_value: Counter value (int, str, or other)
        :return: Integer value, or 0 if parsing fails
        """
        if isinstance(counter_value, int):
            return counter_value
        if isinstance(counter_value, str):
            try:
                return int(counter_value)
            except ValueError:
                return 0
        return 0

    @staticmethod
    def verify_no_link_errors(engine, device: 'IbSwitch') -> ResultObj:
        """
        Verify that traffic ports have no link errors in their counters.

        Uses device.link_error_counters and device.top_level_error_counters to determine
        which counters to check, allowing platform-specific counters to be validated.

        :param engine: DUT engine (engines.dut)
        :param device: Device object (devices.dut) with link_error_counters attribute
        :return: ResultObj with result=True if no errors, result=False with error details otherwise
        """
        traffic_ports = TrafficValidatorTool.get_traffic_ports(engine)

        if not traffic_ports:
            return ResultObj(True, info="No traffic ports configured - skipping error check")

        # Get error counters from device (supports platform-specific counters)
        error_counters = TrafficValidatorTool._get_error_counters_from_device(device)
        link_counters_to_check = error_counters.get('link', [])
        top_level_counters_to_check = error_counters.get('top_level', [])

        errors_found = []

        with allure.step(f'Verify no link errors on traffic ports: {[p.name for p in traffic_ports]}'):
            for port in traffic_ports:
                with allure.step(f'Check counters for {port.name}'):
                    try:
                        # Check link-level counters
                        if link_counters_to_check:
                            link_counters = TrafficValidatorTool.get_link_counters(port, engine)
                            logger.info(f"Link counters for {port.name}: {link_counters}")

                            for counter_name in link_counters_to_check:
                                counter_value = TrafficValidatorTool._parse_counter_value(
                                    link_counters.get(counter_name, 0)
                                )
                                if counter_value != 0:
                                    error_msg = f"{port.name}: {counter_name}={counter_value}"
                                    errors_found.append(error_msg)
                                    logger.error(f"Link error detected - {error_msg}")

                        # Check top-level counters
                        if top_level_counters_to_check:
                            top_counters = TrafficValidatorTool.get_top_level_counters(port, engine)
                            logger.info(f"Top-level counters for {port.name}: {top_counters}")

                            for counter_name in top_level_counters_to_check:
                                counter_value = TrafficValidatorTool._parse_counter_value(
                                    top_counters.get(counter_name, 0)
                                )
                                if counter_value != 0:
                                    error_msg = f"{port.name}: {counter_name}={counter_value}"
                                    errors_found.append(error_msg)
                                    logger.error(f"Top-level error detected - {error_msg}")

                    except Exception as e:
                        error_msg = f"{port.name}: Failed to get counters - {str(e)}"
                        errors_found.append(error_msg)
                        logger.error(error_msg)

        if errors_found:
            error_summary = "Link errors detected after traffic: " + ", ".join(errors_found)
            logger.error(error_summary)
            return ResultObj(False, info=error_summary)

        logger.info("No link errors detected on traffic ports")
        return ResultObj(True, info="No link errors detected")

    @staticmethod
    def _get_error_counters_from_device(device: 'IbSwitch') -> Dict[str, List[str]]:
        """
        Get error counters to check from the device object.

        Reads device.traffic_error_counters dict attribute.

        :param device: Device object (IbSwitch or subclass)
        :return: Dict with 'link' and 'top_level' counter lists
        """
        return device.traffic_error_counters

    @staticmethod
    def get_phy_detail_counters(port: Port, engine=None) -> Dict[str, any]:
        """
        Get PHY detail counters for a specific port.

        These counters are from 'nv show interface <port> link phy detail'.

        :param port: Port object to get counters for
        :param engine: Optional DUT engine
        :return: Dictionary of counter name to value
        """
        engine = engine or TestToolkit.get_engine()

        # Get counters from 'nv show interface <port> link phy detail'
        phy_detail_output = port.interface.link.phy.detail.show(dut_engine=engine)
        phy_detail_dict = OutputParsingTool.parse_json_str_to_dictionary(
            phy_detail_output
        ).get_returned_value()

        return phy_detail_dict if phy_detail_dict else {}

    @staticmethod
    def capture_baseline(engine=None, counters_to_capture: List[str] = None) -> Dict[str, CounterBaseline]:
        """
        Capture baseline values for PHY detail counters on all traffic ports.

        This should be called BEFORE running traffic. The returned baselines
        can then be passed to compare_with_baseline() after traffic.

        :param engine: Optional DUT engine. If not provided, uses TestToolkit.get_engine()
        :param counters_to_capture: Optional list of counter names to capture.
                                    Defaults to PHY_DETAIL_ERROR_COUNTERS.
        :return: Dict of port_name -> CounterBaseline
        """
        engine = engine or TestToolkit.get_engine()
        traffic_ports = TrafficValidatorTool.get_traffic_ports(engine)
        counters_to_capture = counters_to_capture or PHY_DETAIL_ERROR_COUNTERS

        baselines = {}

        if not traffic_ports:
            logger.warning(f"No traffic ports configured for DUT IP {engine.ip} - skipping baseline capture")
            return baselines

        with allure.step(f'Capture PHY detail counter baseline for ports: {[p.name for p in traffic_ports]}'):
            for port in traffic_ports:
                with allure.step(f'Capture baseline for {port.name}'):
                    try:
                        phy_detail = TrafficValidatorTool.get_phy_detail_counters(port, engine)
                        logger.info(f"PHY detail for {port.name}: {phy_detail}")

                        # Extract only the counters we care about
                        baseline = CounterBaseline(port_name=port.name)
                        for counter_name in counters_to_capture:
                            value = TrafficValidatorTool._parse_counter_value(
                                phy_detail.get(counter_name, 0)
                            )
                            baseline.phy_detail_counters[counter_name] = value

                        baselines[port.name] = baseline
                        logger.info(f"Baseline for {port.name}: {baseline.phy_detail_counters}")

                    except Exception as e:
                        logger.error(f"Failed to capture baseline for {port.name}: {str(e)}")
                        # Create empty baseline so we can still compare later
                        baselines[port.name] = CounterBaseline(port_name=port.name)

        return baselines

    @staticmethod
    def compare_with_baseline(baselines: Dict[str, CounterBaseline], engine=None) -> ResultObj:
        """
        Compare current PHY detail counters with baseline and report changes.

        This should be called AFTER running traffic. Any counter that changed
        from its baseline value indicates an error occurred during traffic.

        :param baselines: Dict of port_name -> CounterBaseline from capture_baseline()
        :param engine: Optional DUT engine. If not provided, uses TestToolkit.get_engine()
        :return: ResultObj with result=True if no changes, result=False with details otherwise
        """
        engine = engine or TestToolkit.get_engine()
        traffic_ports = TrafficValidatorTool.get_traffic_ports(engine)

        if not traffic_ports:
            return ResultObj(True, info="No traffic ports configured - skipping baseline comparison")

        if not baselines:
            return ResultObj(True, info="No baselines provided - skipping comparison")

        errors_found = []

        with allure.step(f'Compare PHY detail counters with baseline for ports: {[p.name for p in traffic_ports]}'):
            for port in traffic_ports:
                with allure.step(f'Compare counters for {port.name}'):
                    baseline = baselines.get(port.name)
                    if not baseline:
                        logger.warning(f"No baseline for {port.name} - skipping comparison")
                        continue

                    try:
                        # Get current PHY detail counters
                        phy_detail = TrafficValidatorTool.get_phy_detail_counters(port, engine)
                        logger.info(f"Current PHY detail for {port.name}: {phy_detail}")

                        # Parse current values for the counters we're tracking
                        current_values = {}
                        for counter_name in baseline.phy_detail_counters.keys():
                            current_values[counter_name] = TrafficValidatorTool._parse_counter_value(
                                phy_detail.get(counter_name, 0)
                            )

                        # Compare with baseline
                        changes = baseline.get_changed_counters(current_values)
                        if changes:
                            for counter_name, (before, after) in changes.items():
                                delta = after - before
                                error_msg = f"{port.name}: {counter_name} changed from {before} to {after} (delta: +{delta})"
                                errors_found.append(error_msg)
                                logger.error(f"PHY detail counter changed - {error_msg}")

                    except Exception as e:
                        error_msg = f"{port.name}: Failed to compare counters - {str(e)}"
                        errors_found.append(error_msg)
                        logger.error(error_msg)

        if errors_found:
            error_summary = "PHY detail counters changed during traffic: " + "; ".join(errors_found)
            logger.error(error_summary)
            return ResultObj(False, info=error_summary)

        logger.info("No PHY detail counter changes detected")
        return ResultObj(True, info="No PHY detail counter changes detected")
