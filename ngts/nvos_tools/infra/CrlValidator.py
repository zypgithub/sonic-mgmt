from abc import ABC, abstractmethod
import logging
import time
from typing import List, Optional, Tuple

from ngts.nvos_tools.infra.CertificateGenerator import YEAR, CertificateGenerator
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import BAD_RESPONSE_KEYWORDS
from ngts.tests_nvos.general.security.certificate.helpers import (
    delete_certificates,
    delete_crl,
)
from ngts.tests_nvos.general.security.helpers import setup_certs_for_tests
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import (
    UserInfo,
)
from ngts.tests_nvos.helpers.general_helpers import run_cmd

from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure


class CrlValidator:
    def __init__(self, app: "CrlClient"):
        self.app = app
        self.dest: str = ""
        self.configured_client_ca: Optional[CertInfo] = None
        self.configured_server_cert: Optional[CertInfo] = None

    def setup_certs(self, engines, dest: str, cert_names: List[str], create_chain: bool = False) -> List[CertInfo]:
        dest, certs = self.app.setup_certs(engines=engines, dest=dest, cert_names=cert_names, create_chain=create_chain)
        self.dest = dest
        return certs

    def revoke_cert(self, crl_name: str, cert: CertInfo, dest: str = "", ca_dest: str = "", create_empty: bool = False, ca_name: str = "ca", revoke_cert_name: str = "cert.crt") -> str:
        """
        @param dest: destination directory
        @param cert: cert to revoke
        @param create_empty: if True, generate an empty CRL
        @param ca_name: name of the CA file (without extension)
        @param revoke_cert_name: name of the certificate file to revoke (with extension)

        revoke certificate in a given destination directory.
        @return: path to crl file
        """
        if not dest:
            dest = self.dest
        with allure.step(f"revoke cert: {cert.name}"):
            return CertificateGenerator().revoke_cert(dest, crl_name, cert.name, ca_dest=ca_dest, create_empty=create_empty, ca_name=ca_name, revoke_cert_name=revoke_cert_name)

    def prepare_mtls(self, server_certs: List[CertInfo], client_cas: List[CertInfo]):
        """
        @param server_certs: list of server certificates
        @param client_cas: list of client CAs

        prepare mtls by importing certificates and binding to application.
        @return: tuple of server certificate, client CA certificate
        """
        with allure.step(
            f"Import certificates and bind to {self.app.__class__.__name__} application"
        ):
            server_cert, client_ca_cert = self.app.prepare_mtls(
                server_certs, client_cas
            )
            self.configured_client_ca = client_ca_cert
            self.configured_server_cert = server_cert

    def bind_crl(self, dest: str, crl_name: str, should_succeed: bool = True):
        self.app.bind_crl(dest, crl_name, should_succeed)

    def run_client(
        self,
        user: Optional[UserInfo] = None,
        expect_success: bool = True,
        run_insecure: bool = True,
        client_cacert: Optional[CertInfo] = None,
        client_cert: Optional[CertInfo] = None,
        port: Optional[int] = None,
    ):
        self.app.run_client(
            user, expect_success, run_insecure, client_cacert, client_cert, port
        )

    def unbind_crl(self):
        with allure.step("unbind crl"):
            self.app.unbind_crl()

    def cleanup(self):
        self.app.cleanup()
        delete_certificates()
        delete_certificates(ca=True)
        delete_crl()


class CrlClient(ABC):
    def __init__(self, host: str, ip: str):
        self.host: str = host
        self.ip: str = ip
        self.system = System()

    def setup_certs(
        self, engines, dest: str, cert_names: List[str], create_chain: bool = False
    ) -> Tuple[str, List[CertInfo]]:
        """
        @param engines: engines object
        @param dest: destination directory
        @param cert_names: list of cert names

        setup certificates in a given destination directory.
        @return: tuple of cert location, list of CertInfo
        """
        scp_player = get_scp_player(engines)
        return setup_certs_for_tests(
            certs_dirname_prefix=dest,
            certs_names=cert_names,
            engines=engines,
            dut_hostname=self.host,
            scp_player=scp_player,
            dut_ip=self.ip,
            create_chain=create_chain,
        )

    @abstractmethod
    def prepare_mtls(
        self, server_certs: List[CertInfo], client_cas: List[CertInfo]
    ) -> Tuple[CertInfo, CertInfo]: ...

    @abstractmethod
    def bind_crl(self, dest: str, crl_name: str, should_succeed: bool = True): ...

    @abstractmethod
    def run_client(
        self,
        user: Optional[UserInfo] = None,
        expect_success: bool = True,
        run_insecure: bool = True,
        client_cacert: Optional[CertInfo] = None,
        client_cert: Optional[CertInfo] = None,
        port: Optional[int] = None,
    ): ...

    @abstractmethod
    def unbind_crl(self): ...

    @abstractmethod
    def cleanup(self): ...

    def verify_result(self, client_cmd: str, expect_success: bool):
        time.sleep(0.1)
        logging.info(f'running request:\n{client_cmd}\nexpect: {expect_success}')
        try:
            out = run_cmd(client_cmd)
            assert all(msg not in out for msg in BAD_RESPONSE_KEYWORDS), out
            logging.info('show succeeded')
            actual_success = True
        except Exception as e:
            logging.info('show failed')
            actual_success = False
            out = e
        assert actual_success == expect_success, f'show result not as expected. expected: {expect_success}. actual: {actual_success}\ncmd: {client_cmd}\nerr:\n{out}'
