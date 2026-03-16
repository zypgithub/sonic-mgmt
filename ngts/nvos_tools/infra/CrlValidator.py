import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ngts.nvos_tools.infra.CertificateGenerator import CertificateGenerator
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import BAD_RESPONSE_KEYWORDS
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import (
    delete_certificates,
    delete_crl,
)
from ngts.tests_nvos.general.security.helpers import (
    import_cas_safely,
    import_certs_safely,
    import_crl_safely,
    setup_certs_for_tests,
)
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import (
    UserInfo,
)
from ngts.tests_nvos.helpers.general_helpers import run_cmd
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@dataclass
class RevokeConfig:
    """Configuration for certificate revocation."""

    dest: str = ""
    ca_dest: str = ""
    create_empty: bool = False
    ca_name: str = "ca"
    revoke_cert_name: str = "cert.crt"


@dataclass
class ClientConfig:
    """Configuration for running client requests."""

    user: "UserInfo | None" = None
    expect_success: bool = True
    run_insecure: bool = True
    client_cacert: "CertInfo | None" = None
    client_cert: "CertInfo | None" = None
    port: int | None = None


class CrlValidator(ABC):
    """Base CRL validator with template methods for common operations."""

    def __init__(self, host: str, ip: str):
        self.host = host
        self.ip = ip
        self.system = System()
        self.dest: str = ""
        self.configured_client_ca: CertInfo | None = None
        self.configured_server_cert: CertInfo | None = None

    # ==================== TEMPLATE METHODS ====================

    def setup_certs(self, engines, dest: str, cert_names: list[str], create_chain: bool = False) -> list[CertInfo]:
        """
        Setup certificates in a given destination directory.

        Args:
            engines: engines object
            dest: destination directory
            cert_names: list of cert names
            create_chain: whether to create a certificate chain

        Returns:
            list of CertInfo objects
        """
        scp_player = get_scp_player(engines)
        self.dest, certs = setup_certs_for_tests(
            certs_dirname_prefix=dest,
            certs_names=cert_names,
            engines=engines,
            dut_hostname=self.host,
            scp_player=scp_player,
            dut_ip=self.ip,
            create_chain=create_chain,
        )
        return certs

    def prepare_mtls(self, server_certs: list[CertInfo], client_cas: list[CertInfo]) -> tuple[CertInfo, CertInfo]:
        """
        Template method - prepare mTLS by importing certificates and binding to application.

        Args:
            server_certs: list of server certificates
            client_cas: list of client CAs

        Returns:
            tuple of (server certificate, client CA certificate)
        """
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)

        server_cert = server_certs[0]
        client_ca_cert = client_cas[0]

        with allure.step("import test certs"):
            import_certs_safely(server_certs, scp_player)
            import_cas_safely(client_cas, scp_player)

        with allure.step("setup mtls by binding test certs"):
            self._bind_mtls_certs(server_cert, client_ca_cert)

        self.configured_server_cert = server_cert
        self.configured_client_ca = client_ca_cert
        return server_cert, client_ca_cert

    def bind_crl(
        self,
        dest: str,
        crl_name: str,
        should_succeed: bool = True,
        should_import: bool = True,
        ask_for_confirmation: bool = False,
    ):
        """
        Template method for CRL binding.

        Args:
            dest: destination path for CRL file
            crl_name: name of the CRL
            should_succeed: whether the binding should succeed
            should_import: whether to import the CRL first
            ask_for_confirmation: whether to ask for confirmation when binding
        """
        scp_player = get_scp_player(TestToolkit.engines)

        if should_import:
            with allure.step("import test crl"):
                import_crl_safely(crl_name, dest, scp_player)
            with allure.step("verifies the CRL is imported"):
                output = self.system.security.crl.parse_show()
                assert crl_name in output, f"Expected CRL '{crl_name}' not found in show output"

        with allure.step("bind crl"):
            self._do_bind_crl(crl_name, ask_for_confirmation, should_succeed)

        self._post_bind_crl()

        if should_succeed:
            with allure.step("verify crl shown in mtls"):
                self._verify_crl_bound(crl_name)

    def revoke_cert(
        self,
        crl_name: str,
        cert: CertInfo,
        config: RevokeConfig | None = None,
    ) -> str:
        """
        Revoke certificate in a given destination directory.

        Args:
            crl_name: name for the CRL file
            cert: certificate to revoke
            config: revocation configuration options

        Returns:
            path to CRL file
        """
        if config is None:
            config = RevokeConfig()
        dest = config.dest or self.dest
        with allure.step(f"revoke cert: {cert.name}"):
            return CertificateGenerator().revoke_cert(
                dest,
                crl_name,
                cert.name,
                ca_dest=config.ca_dest,
                create_empty=config.create_empty,
                ca_name=config.ca_name,
                revoke_cert_name=config.revoke_cert_name,
            )

    def unbind_crl(self):
        """Unbind CRL from the application."""
        with allure.step("unbind crl"):
            self._do_unbind_crl()

    def cleanup(self):
        """Cleanup certificates and CRL."""
        self._do_cleanup()
        delete_certificates()
        delete_certificates(ca=True)
        delete_crl()

    # ==================== HOOK METHODS (override in subclasses) ====================

    @abstractmethod
    def _bind_mtls_certs(self, server_cert: CertInfo, client_ca: CertInfo) -> None:
        """Hook: bind mTLS certificates to the feature."""
        ...

    @abstractmethod
    def _do_bind_crl(self, crl_name: str, ask_confirm: bool, should_succeed: bool) -> None:
        """Hook: perform the actual CRL binding."""
        ...

    @abstractmethod
    def _verify_crl_bound(self, crl_name: str) -> None:
        """Hook: verify CRL is shown in feature output."""
        ...

    @abstractmethod
    def _post_bind_crl(self) -> None:
        """Hook: optional post-bind action (e.g., sleep for gNMI)."""
        ...

    @abstractmethod
    def _do_unbind_crl(self) -> None:
        """Hook: unbind CRL from the feature."""
        ...

    @abstractmethod
    def _do_cleanup(self) -> None:
        """Hook: feature-specific cleanup."""
        ...

    # ==================== ABSTRACT METHODS ====================

    @abstractmethod
    def run_client(self, config: ClientConfig | None = None):
        """Execute client request - fully protocol-specific."""
        ...

    # ==================== UTILITY METHODS ====================

    def verify_result(self, client_cmd: str, expect_success: bool):
        """Verify the result of a client command."""
        time.sleep(0.1)
        logger.info("running request:\n%s\nexpect: %s", client_cmd, expect_success)
        try:
            out = run_cmd(client_cmd)
            assert all(msg not in out for msg in BAD_RESPONSE_KEYWORDS), out
            logger.info("show succeeded")
            actual_success = True
        except Exception as e:
            logger.info("show failed")
            actual_success = False
            out = e
        assert actual_success == expect_success, (
            f"show result not as expected. expected: {expect_success}. actual: {actual_success}\ncmd: {client_cmd}\nerr:\n{out}"
        )
