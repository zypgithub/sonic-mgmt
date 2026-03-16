from __future__ import annotations

import logging
import time

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine

from ngts.nvos_tools.infra.GrpcCmdBuilder import GrpcCmdBuilder
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import (
    BAD_RESPONSE_KEYWORDS,
)
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.helpers.general_helpers import run_cmd
from ngts.tools.test_utils import allure_utils as allure


class NvBridgeConsts:
    """Constants for NV Bridge service."""

    NV_BRIDGE_PORT = 50052
    NV_BRIDGE_PROTO_PATH = "/auto/sw_system_project/NVOS_INFRA/verification_files/nmx/umad.proto"
    NV_BRIDGE_ENDPOINT = "umad_grpc.NvBridge/Hello"


class NvBridgeTool:
    """Tool for running grpc requests to NV Bridge service."""

    def __init__(self, host: str, port: int = NvBridgeConsts.NV_BRIDGE_PORT):
        """
        Initialize NvBridgeTool.

        Args:
            host: The host IP address to connect to
            port: The port to connect to (default: 50052)
        """
        self.host = host
        self.port = port
        self.proto_path = NvBridgeConsts.NV_BRIDGE_PROTO_PATH
        self.endpoint = NvBridgeConsts.NV_BRIDGE_ENDPOINT

    def run_bridge_hello(
        self,
        client_cert: CertInfo | None = None,
        client_cacert: CertInfo | None = None,
        plaintext: bool = False,
        expect_success: bool = True,
    ):
        """
        Run NV Bridge Hello grpc request.

        Args:
            client_cert: Client certificate for mTLS (optional)
            client_cacert: Client CA certificate for mTLS (optional)
            plaintext: If True, run insecure plaintext request
            expect_success: Expected result of the request
        """
        with allure.step(f"Run NV Bridge Hello request to {self.host}:{self.port}"):
            grpc_cmd = self._build_grpc_cmd(
                client_cert=client_cert,
                client_cacert=client_cacert,
                plaintext=plaintext,
            )
            self._verify_result(client_cmd=grpc_cmd, expect_success=expect_success)

    def _build_grpc_cmd(
        self,
        client_cert: CertInfo | None = None,
        client_cacert: CertInfo | None = None,
        plaintext: bool = False,
        client_id: str = "sasha",
    ) -> str:
        """
        Build grpcurl command for NV Bridge Hello request.

        Args:
            client_cert: Client certificate for mTLS (optional)
            client_cacert: Client CA certificate for mTLS (optional)
            plaintext: If True, skip TLS verification

        Returns:
            The constructed grpcurl command string
        """
        payload: dict[str, str] = {
            "call_id": {"app_id": f"{client_id}", "call_id": 1},
            "client_id": f"{client_id}",
            "server_address": "localhost:9381",
        }

        grpc = GrpcCmdBuilder(self.host, self.port)

        if plaintext:
            grpc.skip_verify()
        else:
            if client_cert:
                grpc.cert(client_cert.private, client_cert.public)
            if client_cacert:
                grpc.ca(client_cacert.cacert)

        grpc.proto(self.proto_path)
        grpc.endpoint(self.endpoint)
        grpc.payload(payload)

        return grpc.build()

    def _verify_result(self, client_cmd: str, expect_success: bool):
        """
        Execute and verify the grpc command result.

        Args:
            client_cmd: The grpcurl command to execute
            expect_success: Expected result of the request
        """
        time.sleep(0.1)
        logging.info(f"Running NV Bridge request:\n{client_cmd}\nexpect: {expect_success}")
        try:
            out = run_cmd(client_cmd)
            has_error = any(msg in out for msg in BAD_RESPONSE_KEYWORDS)
            if has_error:
                logging.info(f"Request failed with bad response: {out}")
                actual_success = False
            else:
                logging.info("Request succeeded")
                actual_success = True
        except Exception as e:
            logging.info(f"Request failed with exception: {e}")
            actual_success = False
            out = str(e)

        assert actual_success == expect_success, (
            f"NV Bridge request result not as expected. "
            f"expected: {expect_success}, actual: {actual_success}\n"
            f"cmd: {client_cmd}\nerr:\n{out}"
        )


def verify_nv_bridge_has_connection(
    dut_engine: LinuxSshEngine,
    expect_connection: bool = True,
    timeout: int = 30,
) -> bool:
    """
    Verify NV-Bridge connection status.

    Args:
        dut_engine: SSH engine to execute commands on DUT
        expect_connection: If True, expect at least one connection;
            if False, expect no connections
        timeout: Max seconds to wait for expected connection state

    Returns:
        True if connection state matches expectation within timeout

    Raises:
        AssertionError: If connection state doesn't match expectation
    """
    logger = logging.getLogger(__name__)
    poll_interval = 2
    elapsed = 0
    nv_bridge = System().nv_bridge

    with allure.step(f"Verify NV-Bridge {'has' if expect_connection else 'has no'} connection"):
        while elapsed < timeout:
            output = nv_bridge.show(dut_engine=dut_engine)
            parsed = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
            connections = parsed.get("connections", {})
            has_connection = bool(connections)
            if has_connection == expect_connection:
                logger.info(f"NV-Bridge connection state as expected: has_connection={has_connection}")
                return True
            logger.info(f"Waiting for NV-Bridge connection state (has_connection={has_connection}, expect={expect_connection})")
            time.sleep(poll_interval)
            elapsed += poll_interval

        raise AssertionError(
            f"NV-Bridge connection state mismatch after {timeout}s. Expected connection={expect_connection}, got connections={connections}"
        )
