import logging
import time
from typing import Dict, List, Optional, Tuple

from ngts.nvos_constants.constants_nvos import ClusterApps, ClusterConsts
from ngts.nvos_tools.infra.CrlValidator import CrlClient
from ngts.nvos_tools.infra.CurlCmdBuilder import CurlCmdBuilder
from ngts.nvos_tools.infra.GrpcCmdBuilder import GrpcCmdBuilder
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.helpers import import_cas_safely, import_certs_safely, import_crl_safely
from ngts.tests_nvos.general.security.nmx_cert.constants import CA_CERTIFICATE, CERTIFICATE, EncryptionMode
from ngts.tests_nvos.general.security.nmx_cert.helpers import disable_cluster_app_manager_state, enable_cluster, disable_cluster, enable_cluster_app_manager_state
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import (
    UserInfo,
)
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmicCmdBuilder
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player, verify_gnmi_client_tools_installed

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class ApiCrlClient(CrlClient):
    def prepare_mtls(self, server_certs: List[CertInfo], client_cas: List[CertInfo]) -> Tuple[CertInfo, CertInfo]:
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)
        dut = engines.dut

        server_cert: CertInfo = server_certs[0]
        client_ca_cert: CertInfo = client_cas[0]

        with allure.step("import test certs"):
            import_certs_safely(server_certs, scp_player)
            import_cas_safely(client_cas, scp_player)

        feature_resource = self.system.api

        with allure.step("setup mtls by binding test certs"):
            feature_resource.set(CERTIFICATE, server_cert.name).verify_result()
            feature_resource.mtls.set(CA_CERTIFICATE, client_ca_cert.cacert_name).verify_result()
            feature_resource._general_cli_wrapper.apply_config(dut)
            return server_cert, client_ca_cert

    def bind_crl(self, dest: str, crl_name: str, should_succeed: bool = True):
        system = self.system
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)
        crl_file_path = dest

        with allure.step("import test crl"):
            import_crl_safely(crl_name, crl_file_path, scp_player)

        with allure.step("verifies the CRL is imported"):
            output = system.security.crl.parse_show()
            assert crl_name in output, f"Expected CRL '{crl_name}' not found in show output"

        with allure.step("bind crl"):
            system.api.mtls.set("crl", crl_name, apply=True).verify_result(should_succeed=should_succeed)

        with allure.step("verify crl shown in mtls"):
            output = system.api.mtls.parse_show()
            assert 'crl' in output, "No crl found in output"
            assert crl_name in output['crl'], f"Expected CRL '{crl_name}' not found in show output"

    def run_client(
        self,
        user: Optional[UserInfo] = None,
        expect_success: bool = True,
        run_insecure: bool = True,
        client_cacert: Optional[CertInfo] = None,
        client_cert: Optional[CertInfo] = None,
        port: Optional[int] = None,
    ):
        method = 'GET'
        resource = self.system.version.get_resource_path()

        cmd_builder = CurlCmdBuilder(method, self.host, resource)
        if user:
            cmd_builder.user_creds(user.username, user.password)
        if run_insecure or not client_cert:
            cmd_builder.insecure()
        if client_cert:
            cmd_builder.client_cert(client_cert.private, client_cert.public)
        if client_cacert:
            cmd_builder.cacert(client_cacert.cacert)
        curl_cmd = cmd_builder.build()
        self.verify_result(curl_cmd, expect_success)

    def unbind_crl(self):
        self.system.api.mtls.unset('crl', apply=True).verify_result()

    def cleanup(self):
        self.system.api.unset(apply=True).verify_result()


class GnmiCrlClient(CrlClient):
    def prepare_mtls(self, server_certs: List[CertInfo], client_cas: List[CertInfo]) -> Tuple[CertInfo, CertInfo]:
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)
        dut = engines.dut

        server_cert: CertInfo = server_certs[0]
        client_ca_cert: CertInfo = client_cas[0]

        with allure.step("import test certs"):
            import_certs_safely(server_certs, scp_player)
            import_cas_safely(client_cas, scp_player)

        feature_resource = self.system.gnmi_server

        with allure.step("setup mtls by binding test certs"):
            feature_resource.set(CERTIFICATE, server_cert.name).verify_result()
            feature_resource.mtls.set(CA_CERTIFICATE, client_ca_cert.cacert_name).verify_result()
            feature_resource._general_cli_wrapper.apply_config(dut)
            return server_cert, client_ca_cert

    def bind_crl(self, dest: str, crl_name: str, should_succeed: bool = True):
        system = self.system
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)
        crl_file_path = dest

        with allure.step("import test crl"):
            import_crl_safely(crl_name, crl_file_path, scp_player)

        with allure.step("verifies the CRL is imported"):
            output = system.security.crl.parse_show()
            assert crl_name in output, f"Expected CRL '{crl_name}' not found in show output"

        with allure.step("bind crl and wait 5 sec"):
            system.gnmi_server.mtls.set("crl", crl_name, apply=True).verify_result()
            time.sleep(5)

        with allure.step("verify crl shown in mtls"):
            output = system.gnmi_server.mtls.parse_show()
            assert 'crl' in output, "No crl found in output"
            assert crl_name in output['crl'], f"Expected CRL '{crl_name}' not found in show output"

    def run_client(
        self,
        user: Optional[UserInfo] = None,
        expect_success: bool = True,
        run_insecure: bool = True,
        client_cacert: Optional[CertInfo] = None,
        client_cert: Optional[CertInfo] = None,
        port: Optional[int] = None,
    ):
        verify_gnmi_client_tools_installed()  # Makes sure gnmic and grpcurl are installed on the test player
        gnmic = GnmicCmdBuilder(self.ip).capabilities()
        if run_insecure or not client_cert:
            gnmic.skip_verify()
        if user:
            gnmic.user_creds(user.username, user.password)
        if client_cert:
            gnmic.cert(client_cert.private, client_cert.public)
        if client_cacert:
            gnmic.ca(client_cacert.cacert)

        self.verify_result(gnmic.build(), expect_success)

    def unbind_crl(self):
        with allure.step("unbind crl and wait 5 sec"):
            self.system.gnmi_server.mtls.unset('crl', apply=True).verify_result()
            time.sleep(5)

    def cleanup(self):
        self.system.gnmi_server.unset(apply=True).verify_result()


class NmxCrlClient(CrlClient):
    def __init__(self, host: str, ip: str, app_name: str, port: int, proto_path: str = ''):
        super().__init__(host, ip)
        self.app_name: str = app_name
        self.port: int = port
        self.cluster = Cluster()
        self.proto_path: str = proto_path
        # Makes sure gnmic and grpcurl are installed on the test player
        verify_gnmi_client_tools_installed()

    def prepare_mtls(self, server_certs: List[CertInfo], client_cas: List[CertInfo]) -> Tuple[CertInfo, CertInfo]:
        engines = TestToolkit.engines
        scp_player = get_scp_player(engines)

        server_cert: CertInfo = server_certs[0]
        client_ca_cert: CertInfo = client_cas[0]

        with allure.step("import test certs"):
            import_certs_safely(server_certs, scp_player)
            import_cas_safely(client_cas, scp_player)

        nmx_app = self.cluster.apps.app_name[self.app_name]

        with allure.step("Enable cluster and setup mtls by binding test certs"):
            enable_cluster()
            enable_cluster_app_manager_state(nmx_app.manager)
            nmx_app.manager.certificate.action_update(server_cert.name).verify_result()
            nmx_app.manager.ca_certificate.action_update(client_ca_cert.cacert_name).verify_result()
            nmx_app.manager.encryption.action_update(EncryptionMode.MTLS).verify_result()
        return server_cert, client_ca_cert

    def bind_crl(self, dest: str, crl_name: str, should_succeed: bool = True):
        system = self.system
        scp_player = get_scp_player(TestToolkit.engines)
        nmx_app = self.cluster.apps.app_name[self.app_name]
        crl_file_path = dest

        with allure.step("import test crl"):
            import_crl_safely(crl_name, crl_file_path, scp_player)

        with allure.step("verifies the CRL is imported"):
            output = system.security.crl.parse_show()
            assert crl_name in output, f"Expected CRL '{crl_name}' not found in show output"

        with allure.step("bind crl"):
            nmx_app.manager.crl.action_update(crl_name).verify_result(should_succeed=should_succeed)

        with allure.step("verify crl shown in mtls"):
            with allure.independent_step("verify crl shown in nmx app manager output"):
                output = nmx_app.manager.parse_show()
                assert 'crl' in output, "No crl found in output"
            with allure.independent_step("verify crl shown in nmx app manager crl output"):
                output = nmx_app.manager.crl.parse_show()
                assert 'crl' in output, "No crl found in output"
                assert crl_name in output['crl'], f"Expected CRL '{crl_name}' not found in show output"

    def run_client(
        self,
        user: Optional[UserInfo] = None,
        expect_success: bool = True,
        run_insecure: bool = False,
        client_cacert: Optional[CertInfo] = None,
        client_cert: Optional[CertInfo] = None,
        port: Optional[int] = None,
    ):
        if self.app_name == ClusterApps.NMX_CONTROLLER:
            endpoint: str = 'nmx_c.NMX_Controller.Hello'
        elif self.app_name == ClusterApps.NMX_TELEMETRY:
            endpoint: str = 'TelemetryService.Hello'
        else:
            raise ValueError(f"Invalid app name: {self.app_name}")

        if not port:
            port = self.port

        payload: Dict[str, str] = {"gatewayId": "sasha",
                                   "major_version": "PROTO_MSG_MAJOR_VERSION", "minor_version": "PROTO_MSG_MINOR_VERSION"}
        grpc = GrpcCmdBuilder(self.host, port)
        if user:
            grpc.user_creds(user.username, user.password)
        if client_cert:
            grpc.cert(client_cert.private, client_cert.public)
        if client_cacert:
            grpc.ca(client_cacert.cacert)
        if endpoint:
            grpc.endpoint(endpoint)
        if payload:
            grpc.payload(payload)
        if self.proto_path:
            grpc.proto(self.proto_path)
        grpc_cmd = grpc.build()
        self.verify_result(grpc_cmd, expect_success)

    def unbind_crl(self):
        app_manager = self.cluster.apps.app_name[self.app_name].manager
        app_manager.crl.action_restore().verify_result()

    def cleanup(self):
        app_manager = self.cluster.apps.app_name[self.app_name].manager
        app_manager.encryption.action_restore().verify_result()
        app_manager.crl.action_restore().verify_result()
        app_manager.certificate.action_restore().verify_result()
        app_manager.ca_certificate.action_restore().verify_result()
        disable_cluster_app_manager_state(app_manager)
        disable_cluster()


class NmxControllerCrlClient(NmxCrlClient):
    def __init__(self, host: str, ip: str):
        super().__init__(host, ip, ClusterApps.NMX_CONTROLLER, ClusterConsts.NMX_CONTROLLER_ENVOY_PORT)


class NmxTelemetryCrlClient(NmxCrlClient):
    def __init__(self, host: str, ip: str):
        super().__init__(host, ip, ClusterApps.NMX_TELEMETRY,
                         ClusterConsts.NMX_TELEMETRY_ENVOY_PORT, ClusterConsts.NMX_TELEMETRY_PROTO_PATH)
