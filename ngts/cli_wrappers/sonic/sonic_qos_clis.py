import json
import logging
import time

from retry.api import retry_call

from ngts.constants.constants import SonicConst
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps, wait_for_system_ready, detect_asic_count, validate_and_get_asic_count
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon

logger = logging.getLogger()


class SonicQosCli:
    """
    This class hosts SONiC Qos cli methods
    """

    def __init__(self, engine):
        self.engine = engine

    def reload_qos(self, ports_list=[], no_dynamic=False, platform_params=None):
        """
        This method is to reload qos
        :param ports_list: if provided a port lists, reload qos configuration only on ports in list
        :param no_dynamic: True if buffer module is traditional
        :param platform_params: Platform parameters dict (optional, for multi-ASIC context)
        :return: command output
        """
        cmd_suffix = ""
        if ports_list:
            cmd_suffix += f"--ports {','.join(ports_list)} "
        if no_dynamic:
            cmd_suffix += "--no-dynamic-buffer"

        # Wait for system to be ready (checks global + all ASIC namespaces if multi-ASIC)
        logger.info("Checking if Redis/system is ready before reloading QoS...")
        wait_for_system_ready(self.engine, platform_params)
        logger.info("✓ System is ready, proceeding with QoS reload")

        cmd = f'sudo config qos reload {cmd_suffix}'
        return self.engine.run_cmd(cmd, validate=True)

    def clear_qos(self):
        """
        This method is to clear qos
        :param engine: ssh engine object
        :return: command output
        """
        return self.engine.run_cmd('sudo config qos clear ', validate=True)

    def _check_container_running_once(self, container_name):
        """
        Check if a container is running (single attempt)
        Uses verify_container_running from GeneralCliCommon
        :param container_name: Name of the docker container
        :raises Exception: If container is not running
        """
        # Use the common verify method from GeneralCliCommon
        # Create a temporary instance to access the method
        common_cli = GeneralCliCommon(self.engine, None, 'temp')
        common_cli.verify_container_running(container_name)
        logger.info(f"Container {container_name} is running")

    def _is_container_running(self, container_name, max_retries=3, retry_delay=2):
        """
        Check if a container is running, with retries
        :param container_name: Name of the docker container
        :param max_retries: Maximum number of retries
        :param retry_delay: Delay between retries in seconds
        :return: True if container is running, False otherwise
        """
        try:
            retry_call(
                self._check_container_running_once,
                fargs=[container_name],
                tries=max_retries,
                delay=retry_delay,
                logger=logger
            )
            return True
        except Exception as e:
            logger.warning(f"Container {container_name} is not running after {max_retries} retries: {e}")
            return False

    def _manage_buffermgrd_on_container(self, action, container, asic_id=None, total_asics=1):
        """
        Manage buffermgrd on a single container
        :param action: Either "start" or "stop"
        :param container: Container name (e.g., 'swss' or 'swss0')
        :param asic_id: ASIC ID for logging (None for single-ASIC)
        :param total_asics: Total number of ASICs for logging
        """
        prefix = f"[ASIC {asic_id}/{total_asics - 1}] " if asic_id is not None else ""

        logger.info(f"{prefix}{action.capitalize()}ing buffermgrd on container: {container}")

        # Check if container is running before attempting to manage buffermgrd
        if not self._is_container_running(container, max_retries=10, retry_delay=2):
            error_msg = f"Container {container} is not running after retries"
            logger.error(f"{prefix}{error_msg}")
            raise Exception(error_msg)

        try:
            output = self.engine.run_cmd(f'docker exec {container} supervisorctl {action} buffermgrd', validate=True)
            logger.info(f"{prefix}✓ Successfully {action}ed buffermgrd on {container}")
            return output
        except Exception as e:
            logger.error(f"{prefix}✗ Failed to {action} buffermgrd on {container}: {e}")
            raise

    def _manage_buffermgrd_multi_asic(self, action, platform_params):
        """
        Manage buffermgrd on multi-ASIC platform
        :param action: Either "start" or "stop"
        :param platform_params: Platform parameters dict with asic_count
        :return: command output
        """
        # Get asic_count and raise error if not specified
        config_asic_count = validate_and_get_asic_count(platform_params)

        # Detect actual ASIC count from the running system
        actual_asic_count = detect_asic_count(self.engine, platform_params, raise_on_error=False) if platform_params else config_asic_count

        logger.info(f"Using actual asic_count={actual_asic_count} for operations")
        logger.info(f"Will {action} buffermgrd on containers: swss0 through swss{actual_asic_count - 1}")

        # Define the operation to be retried
        def _manage_all_asics():
            output = None
            for asic_id in range(actual_asic_count):
                container = f'swss{asic_id}'
                output = self._manage_buffermgrd_on_container(action, container, asic_id, actual_asic_count)

            logger.info(f"✓ Successfully {action}ed buffermgrd on all {actual_asic_count} ASIC containers")
            return output

        # Use retry_call with configurable parameters
        result = retry_call(_manage_all_asics, tries=SonicConst.MultiAsic.RETRY_COUNT,
                            delay=SonicConst.MultiAsic.RETRY_DELAY, logger=logger)
        return result

    def _manage_buffermgrd_single_asic(self, action):
        """
        Manage buffermgrd on single-ASIC platform
        :param action: Either "start" or "stop"
        :return: command output
        """
        output = self._manage_buffermgrd_on_container(action, 'swss')
        logger.info(f"Successfully {action}ed buffermgrd on swss container")
        logger.info("=" * 80)
        return output

    def _manage_buffermgrd(self, action, platform_params=None):
        """
        Generic method to start or stop buffermgrd
        For multi-ASIC platforms, manages buffermgrd on all ASIC containers
        :param action: Either "start" or "stop"
        :param platform_params: Platform parameters dict with asic_count (optional, only for multi-ASIC)
        :return: command output
        """
        logger.info("=" * 80)
        logger.info(f"Starting {action}_buffermgrd operation")

        if SonicInstallationSteps.is_multi_asic_platform(platform_params=platform_params):
            result = self._manage_buffermgrd_multi_asic(action, platform_params)
        else:
            result = self._manage_buffermgrd_single_asic(action)

        return result

    def stop_buffermgrd(self, platform_params=None, max_operation_retries=3, operation_retry_delay=15):
        """
        This method is to stop buffermgrd
        For multi-ASIC platforms, stops buffermgrd on all ASIC containers
        :param platform_params: Platform parameters dict with asic_count (optional, only for multi-ASIC)
        :param max_operation_retries: Maximum number of retries for the entire operation (unused, kept for backwards compatibility)
        :param operation_retry_delay: Delay in seconds between operation retries (unused, kept for backwards compatibility)
        :return: command output
        """
        return self._manage_buffermgrd("stop", platform_params)

    def start_buffermgrd(self, platform_params=None, max_operation_retries=3, operation_retry_delay=15):
        """
        This method is to start buffermgrd
        For multi-ASIC platforms, starts buffermgrd on all ASIC containers
        :param platform_params: Platform parameters dict with asic_count (optional, only for multi-ASIC)
        :param max_operation_retries: Maximum number of retries for the entire operation (unused, kept for backwards compatibility)
        :param operation_retry_delay: Delay in seconds between operation retries (unused, kept for backwards compatibility)
        :return: command output
        """
        return self._manage_buffermgrd("start", platform_params)

    def get_dwrr_weights(self, tc_list):
        """
        This function is used to get the dwrr weights for the selected tc list
        :param tc_list: list of tc, i.e [1, 2]
        :return: dict of tc and dwrr weight, i.e {1: 100, 2: 200}
        """
        dwrr_weights = {}
        output = self.engine.run_cmd("sonic-cfggen -j /etc/sonic/config_db.json --var-json SCHEDULER")
        weights_json = json.loads(output)
        for tc in tc_list:
            dwrr_weights[tc] = int(weights_json[f"scheduler_q{tc}_downlink"]["weight"])
        return dwrr_weights
