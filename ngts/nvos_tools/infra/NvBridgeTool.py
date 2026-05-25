from __future__ import annotations

import itertools
import json
import logging
import time
from dataclasses import dataclass

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
    NV_BRIDGE_PROTO_PATH = (
        "/auto/sw_system_project/NVOS_INFRA/verification_files/nmx/nvbridge.proto"
    )
    NV_BRIDGE_ENDPOINT = "umad_grpc.NvBridge/Hello"
    # HelloResponse.return_code: 0 = OK; 1 = accepted non-active; negative = error.
    HELLO_VALID_RETURN_CODES = frozenset({0, 1})
    HELLO_DEFAULT_RETURN_CODE = 0
    # Cluster Stop/Start App on Rosalind takes ~50-60s; bridge bootstrap a few more.
    HELLO_READY_TIMEOUT_SEC = 120
    HELLO_READY_POLL_INTERVAL_SEC = 5


@dataclass
class HelloRequest:
    """Hello request payload (sent to umad_grpc.NvBridge/Hello)."""

    client_id: str
    connection_id: int
    server_address: str = "localhost:9381"
    version: str = "sonic-mgmt"

    def to_payload(self) -> dict:
        """Build the proto3-JSON payload (camelCase) for grpcurl."""
        return {
            "header": {
                "sessionId": {
                    "clientId": self.client_id,
                    "connectionId": self.connection_id,
                }
            },
            "serverAddress": self.server_address,
            "version": self.version,
        }


@dataclass
class HelloResponse:
    """Parsed Hello response (umad_grpc.NvBridge/Hello)."""

    return_code: int
    error_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.return_code in NvBridgeConsts.HELLO_VALID_RETURN_CODES

    @classmethod
    def from_grpcurl_stdout(cls, out: str) -> "HelloResponse":
        """Classify grpcurl stdout into a HelloResponse."""
        text = out.strip()
        if not text or any(msg in text for msg in BAD_RESPONSE_KEYWORDS):
            return cls(return_code=-1, error_reason=text or "empty grpcurl output")
        try:
            resp = json.loads(text)
        except json.JSONDecodeError as exc:
            logging.info("Failed to parse Hello response JSON: %s", exc)
            return cls(return_code=-1, error_reason=str(exc))
        # grpcurl normally emits a JSON object, but guard against valid non-object
        # JSON (null / list / scalar) so ``resp.get`` below cannot raise.
        if not isinstance(resp, dict):
            logging.info("Unexpected non-object Hello response JSON: %r", resp)
            return cls(return_code=-1, error_reason=f"non-object JSON response: {resp!r}")
        # Missing returnCode == proto3 default 0 (valid success).
        return cls(
            return_code=resp.get("returnCode", NvBridgeConsts.HELLO_DEFAULT_RETURN_CODE),
            error_reason=(resp.get("errorReason") or "").strip(),
        )


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
        # Bridge rejects connection_id=0 (proto3 default). Use a non-zero counter
        # seeded from wall-clock so successive runs get disjoint id ranges.
        self._connection_ids = itertools.count(start=int(time.time()))

    def run_bridge_hello(
        self,
        client_cert: CertInfo | None = None,
        client_cacert: CertInfo | None = None,
        plaintext: bool = False,
        expect_success: bool = True,
    ):
        """
        Run NV Bridge Hello grpc request and assert the result matches expectation.

        Args:
            client_cert: Client certificate for mTLS (optional)
            client_cacert: Client CA certificate for mTLS (optional)
            plaintext: If True, run insecure plaintext request
            expect_success: Expected result of the request

        Raises:
            AssertionError: When the Hello result does not match ``expect_success``.
        """
        with allure.step(f"Run NV Bridge Hello request to {self.host}:{self.port}"):
            grpc_cmd = self._build_grpc_cmd(
                client_cert=client_cert,
                client_cacert=client_cacert,
                plaintext=plaintext,
            )
            actual_success, out = self._execute_hello(grpc_cmd)
            assert actual_success == expect_success, (
                f"NV Bridge request result not as expected. "
                f"expected: {expect_success}, actual: {actual_success}\n"
                f"cmd: {grpc_cmd}\nerr:\n{out}"
            )

    def wait_for_hello_ready(
        self,
        client_cert: CertInfo | None = None,
        client_cacert: CertInfo | None = None,
        plaintext: bool = False,
        timeout: int = NvBridgeConsts.HELLO_READY_TIMEOUT_SEC,
        poll_interval: int = NvBridgeConsts.HELLO_READY_POLL_INTERVAL_SEC,
    ) -> bool:
        """
        Poll Hello until the bridge accepts it or ``timeout`` seconds elapse.

        cluster=enabled / nmx-c=up can be reached before the bridge has finished
        bootstrapping its identity, so the very first Hello can still be refused
        for a few seconds. Polling closes that race; each retry uses a fresh
        connection_id automatically.

        Returns:
            True when Hello is accepted within ``timeout``, False otherwise.
        """
        with allure.step(
            f"Wait up to {timeout}s for NV Bridge Hello to be accepted "
            f"({self.host}:{self.port})"
        ):
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                grpc_cmd = self._build_grpc_cmd(
                    client_cert=client_cert,
                    client_cacert=client_cacert,
                    plaintext=plaintext,
                )
                actual_success, _ = self._execute_hello(grpc_cmd)
                if actual_success:
                    logging.info(
                        "NV Bridge Hello ready after %.1fs",
                        time.monotonic() - start,
                    )
                    return True
                time.sleep(poll_interval)
            logging.warning("NV Bridge Hello not ready after %ds", timeout)
            return False

    def _build_grpc_cmd(
        self,
        client_cert: CertInfo | None = None,
        client_cacert: CertInfo | None = None,
        plaintext: bool = False,
    ) -> str:
        """Build grpcurl command for an NV Bridge Hello request."""
        request = HelloRequest(
            client_id=self.host,
            connection_id=next(self._connection_ids),
        )

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
        grpc.payload(request.to_payload())

        return grpc.build()

    def _execute_hello(self, client_cmd: str) -> tuple[bool, str]:
        """
        Run a built grpcurl Hello command and classify the response.

        Returns:
            ``(actual_success, raw_output)`` — ``actual_success`` is True when
            ``returnCode`` is 0 or 1 (negative codes and other values are failures).
        """
        time.sleep(0.1)
        logging.info(f"Running NV Bridge request:\n{client_cmd}")
        try:
            out = run_cmd(client_cmd)
        except Exception as e:
            logging.info(f"Request failed with exception: {e}")
            return False, str(e)

        response = HelloResponse.from_grpcurl_stdout(out)
        if response.ok:
            logging.info(
                "Request succeeded (Hello returnCode=%s)", response.return_code
            )
        else:
            logging.info(
                f"Request failed: returnCode={response.return_code} "
                f"errorReason={response.error_reason!r} out={out}"
            )
        return response.ok, out


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
    connections: dict = {}

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
