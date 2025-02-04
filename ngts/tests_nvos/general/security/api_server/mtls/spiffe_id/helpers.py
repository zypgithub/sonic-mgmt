import random

from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiRequest
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import MAX_SPIFFE_LEN, SecurityMode
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.helpers.general_helpers import generate_rand_str


def generate_rand_spiffe_id(domain_len=None, path_len=None) -> str:
    domain_len = domain_len or random.randint(1, MAX_SPIFFE_LEN)
    path_len = path_len or random.randint(1, MAX_SPIFFE_LEN)
    rand_domain = generate_rand_str(domain_len)
    rand_path = generate_rand_str(path_len)
    rand_spiffe = f'spiffe://{rand_domain}/{rand_path}'
    return rand_spiffe


def setup_api_security_mode(mode: str, server_cert: CertInfo, server_ca: CertInfo):
    system = System()
    system.api.unset().verify_result()
    if mode != SecurityMode.UNSECURED:
        system.api.set('certificate', server_cert.name).verify_result()
    if mode == SecurityMode.MTLS:
        system.api.mtls.set('ca-certificate', server_ca.cacert_name).verify_result()
    system._general_cli_wrapper.apply_config(TestToolkit.engines.dut, verify_execution=True)


def get_tmp_revision_number_for_test_only(client_certs: CertInfo = None):
    if client_certs:
        OpenApiRequest.update_client_certs_info(client_certs)
    System(force_api=ApiType.OPENAPI).gnmi_server.unset().verify_result()
    revision_num = OpenApiRequest.changeset
    OpenApiRequest.clear_changeset_and_payload()
    OpenApiRequest.update_client_certs_info(None)
    return revision_num
