import logging
import os
import time

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import GnmiConsts
from ngts.nvos_tools.infra import CmdRunner
from ngts.tests_nvos.conftest import dut_hostname, get_dut_hostname
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.helpers import generate_certs, get_test_certs_dir_location, prepare_tmp_test_certs, set_new_random_users
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
import pytest
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine

from ngts.nvos_constants.constants_nvos import (
    ApiType,
    UserRole,
)
from ngts.nvos_tools.infra.CrlValidator import CrlValidator
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.crl.helpers import ApiCrlClient, GnmiCrlClient
from ngts.tests_nvos.general.security.test_api_server_security.constants import CA_CERTIFICATE
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmicCmdBuilder
from ngts.tests_nvos.system.gnmi.constants import CERTIFICATE, GnmiMode
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tests_nvos.system.gnmi.test_gnmi_cert import read_process_for_specified_time, validate_gnmi_streaming_output
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_import_crl_cert(dut_hostname, engines, test_api, system_with_cleanup):
    """
    Basic feature functionality to validate import, show, set, unset, delete commands.
    Test flow:
    1.	Import the CRL to switch
    2.	Verify imported successfully via nv show.
    3.	Verify imported crl is stored in '/var/local/share/crl/'
    4.	Delete the imported CRL through CLI
    5.	Verify CRL is deleted in show.
    6.	Verify CRL is removed from '/var/local/share/crl/'

    """
    TestToolkit.tested_api = test_api
    system = system_with_cleanup
    engine: LinuxSshEngine = engines.dut
    scp_player = get_scp_player(engines)
    crl_resource = system.security.crl
    crl_validator = CrlValidator(app=ApiCrlClient(host=dut_hostname, ip=engine.ip))
    certs = crl_validator.setup_certs(
        engines=engines, dest="sasha", cert_names=["client", "server"]
    )
    cert_to_revoke = certs[0]
    crl_name = "test_crl"
    crl_file_path = crl_validator.revoke_cert(crl_name=crl_name, cert=cert_to_revoke)

    with allure.step("Import the CRL to switch"):
        crl_resource.crl_id[crl_name].action_import(uri=generate_scp_uri_using_player(scp_player, crl_file_path)).verify_result()

    with allure.step("Verify imported successfully via nv show"):
        output = crl_resource.parse_show()
        assert crl_name in output, f"Expected CRL '{crl_name}' not found in show output"

    with allure.step("Verify imported crl is stored in '/var/local/share/crl/'"):
        _verify_cmd_success(engine, f"ls /var/local/share/crl/{crl_name}.pem")

    with allure.step("Delete the imported CRL through CLI"):
        crl_resource.crl_id[crl_name].action_delete().verify_result()

    with allure.step("Verify CRL is deleted in show"):
        output = crl_resource.parse_show()
        assert crl_name not in output, f"CRL '{crl_name}' found in show output after delete action"

    with allure.step("Verify CRL is removed from '/var/local/share/crl/'"):
        _verify_cmd_success(engine, f"ls /var/local/share/crl/{crl_name}.pem", should_succeed=False)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_crl_core_functionality(engines, validator_with_cleanup):
    """
    Core feature functionality to validate crl is blocking the request.
    Test flow:
    1.	Generate certs
    2.	Generate CRL file
    3.	Import the CRL to switch
    4.	Bind Crl for application
    5.	Verify show under application bound
    6.	Verify show under sec crl
    7.	Make request via client application with client cert which is in CRL
    8.	Verify request doesn't pass with certificate revoked error in logs.
    9.	Delete CRL file
    10.	Verify delete fails as it is bind to api
    11.	Unbound crl from application
    12.	Verify crl location is empty.
    13.	Verify the request now passes.

    """
    crl_validator: CrlValidator = validator_with_cleanup
    certs = crl_validator.setup_certs(
        engines=engines, dest="crl-sasha", cert_names=["client", "server"]
    )
    revoked_cert = certs[0]
    server_cert = certs[-1]

    crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[revoked_cert])
    crl_name = "my_crl"
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=revoked_cert)
    crl_validator.bind_crl(crl_path, crl_name)
    system = System()

    admin = _generate_random_admin_with_apply(engines.dut, system)
    with allure.step("Core test flow"):
        with allure.independent_step("Make request via client application and see it fails"):
            crl_validator.run_client(admin, expect_success=False, client_cert=revoked_cert, client_cacert=server_cert)

        with allure.independent_step("Try to delete CRL file"):
            system.security.crl.crl_id[crl_name].action_delete().verify_result(should_succeed=False)

        crl_validator.unbind_crl()
        with allure.independent_step("Make request via client application and see it is successful"):
            crl_validator.run_client(admin, expect_success=True, client_cert=revoked_cert, client_cacert=server_cert)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_cert_not_in_crl(dut_hostname, engines, validator_with_cleanup):
    """
    Validate crl is not blocking the request for certificate which is not part of crl.
    Test flow:
    1.	Generate CA cert and 2 client certificates cert_pos and cert_neg
    2.	Using CA, generate CRL with cert_neg serial part of it
    3.	Import CRL
    4.	Bind CRL for application
    5.	Verify client request with cert_pos works
    6.	Verify client request with cert_neg does not go through with crl error
    7.	Unset and delete CRL
    8.	Verify client request with cert_pos works
    9.	Verify client request with cert_neg works

    """
    crl_validator: CrlValidator = validator_with_cleanup
    certs_location = get_test_certs_dir_location('crl_2_certs', dut_hostname)
    cn = 'nvos-client'
    dn = dut_hostname
    ip = engines.dut.ip
    with allure.step("Generate CA cert and 2 client certificates cert_pos and cert_neg"):
        cert_pos = CertInfo('client1', 'first client', '', '', '', '', dn, ip, '', f'{cn}')
        cert_neg = CertInfo('client2', 'second client', '', '', '', '', dn, ip, '', f'{cn}')
        clients_certs = [cert_pos, cert_neg]
        client_certs_dir = os.path.join(certs_location, 'client_certs')
        generate_certs(client_certs_dir, clients_certs)
    with allure.step("Generate server cert"):
        server_certs_dir = os.path.join(certs_location, 'server_certs')
        server_certs = [
            CertInfo('server-cert', 'server cert', '', '', '', '', dn, ip, '', f'{dn}'),
        ]
        server_cert: CertInfo = server_certs[0]
        generate_certs(server_certs_dir, server_certs)

    crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[cert_pos])
    crl_name = "test_crl"
    ca_dest = os.path.join(client_certs_dir, 'ca')
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=cert_neg, dest=client_certs_dir, ca_dest=ca_dest)
    crl_validator.bind_crl(crl_path, crl_name)

    admin = UserInfo("admin", "admin", "admin")
    with allure.step("Make request via client with good cert"):
        crl_validator.run_client(admin, expect_success=True, client_cert=cert_pos, client_cacert=server_cert)

    with allure.step("Make request via client with revoked cert"):
        crl_validator.run_client(admin, expect_success=False, client_cert=cert_neg, client_cacert=server_cert)

    crl_validator.unbind_crl()

    with allure.step("Make request via client with good cert"):
        crl_validator.run_client(admin, expect_success=True, client_cert=cert_pos, client_cacert=server_cert)

    with allure.step("Make request via client with revoked cert"):
        crl_validator.run_client(admin, expect_success=True, client_cert=cert_pos, client_cacert=server_cert)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
@pytest.mark.parametrize('addressing_type', [AddressingType.IPV4, AddressingType.IPV6])
def test_empty_crl(engines, addressing_type, validator_with_cleanup):
    """
    Validate importing empty CRL works and does not affect mtls flow

    1.	Generate CA and certs both for client and server
    2.	Import empty crl file
    3.	Bind crl for each application
    4.	Verify each application request still works in mtls mode

    """
    crl_validator: CrlValidator = validator_with_cleanup
    certs = crl_validator.setup_certs(
        engines=engines, dest="crl-sasha", cert_names=["client", "server"]
    )
    revoked_cert = certs[0]
    server_cert = certs[-1]

    crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[revoked_cert])
    crl_name = "test_crl"
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=revoked_cert, create_empty=True)
    crl_validator.bind_crl(crl_path, crl_name)
    system = System()

    admin = _generate_random_admin_with_apply(engines.dut, system)
    with allure.step("Make request via client application and see it works as crl is empty"):
        crl_validator.run_client(admin, expect_success=True, client_cert=revoked_cert, client_cacert=server_cert)

    crl_validator.unbind_crl()
    with allure.step("Make request via client application and see it works after unbinding crl"):
        crl_validator.run_client(admin, expect_success=True, client_cert=revoked_cert, client_cacert=server_cert)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_cert_intermidiate_ca(engines, validator_with_cleanup):
    """
    Validate CRL works with chain and revoking iCA

    1.	Generate root CA and sign with it iCA. With iCa generate client cert
    2.	Revoke with iCa the generated cert -> iCRL
    3.	Revoke with rCa the iCA -> rCRL
    4.	Import both iCA and rCA
    5.	Bind application ca to use iCA
    6.	Import iCRL and bind it to application
    7.	Verify client application gets certificate revoked error on request
    8.	Bind rCA instead of iCA as ca-certificate for application
    9.	Verify ssl error, as rCA didn't sign the iCRL
    10.	Bind rCRL as crl for application
    11.	Verify ssl error, as cert chain should be revoked

    """
    with allure.step('prepare temp test certs in shared location'):
        crl_validator: CrlValidator = validator_with_cleanup
        certs = crl_validator.setup_certs(
            engines=engines, dest="crl-chain", cert_names=["client-chain", "server"], create_chain=True
        )
        chain_cert = certs[0]
        chain_cert.public = os.path.join(os.path.dirname(chain_cert.public), 'chain.pem')
        server_cert = certs[-1]

    crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[chain_cert])
    crl_name = "test_crl_chain"
    crl2_name = "test_revoked_iCA"
    system = System()
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=chain_cert, ca_name='interCA')
    crl2_path = crl_validator.revoke_cert(crl_name=crl2_name, cert=chain_cert, ca_name='rCA', revoke_cert_name='interCA.crt')

    admin = _generate_random_admin_with_apply(engines.dut, system)
    with allure.step("Make request via client application and see it works before applying crl"):
        crl_validator.run_client(admin, expect_success=True, client_cert=chain_cert, client_cacert=server_cert)

    crl_validator.bind_crl(crl_path, crl_name)
    with allure.step("Make request via client application and see doesn't work after applying crl"):
        crl_validator.run_client(admin, expect_success=False, client_cert=chain_cert, client_cacert=server_cert)

    crl_validator.bind_crl(crl2_path, crl2_name)
    with allure.step("Make request via client application and see doesn't work as iCA is revoked"):
        crl_validator.run_client(admin, expect_success=False, client_cert=chain_cert, client_cacert=server_cert)

    crl_validator.unbind_crl()
    with allure.step("Make request via client application and see it works after unbinding crl"):
        crl_validator.run_client(admin, expect_success=True, client_cert=chain_cert, client_cacert=server_cert)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_exprired_crl_after_import():
    """
    Validate importing crl with soon to be expired works and does not affect mtls flow
    After it expires the flow should not work

    1. Generate CA and certs both for client and server
    2. Generate CRL with soon to be expired date
    3. Import CRL
    4. Bind CRL for each application
    5. Wait for CRL to expire (by changing system time)
    6. Verify each application request does not work in mtls mode


    """
    pytest.skip("Not implemented")


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_multiple_crl(engines, dut_hostname, system_with_cleanup):
    """
    Validate that is it possible to import multiple crl and bind each to each application
    Also validates that combined crl works

    1.	Generate couple of crl files for each application
    2.	Bind to each application its own crl
    3.	Validate each request has ssl error on cert revoked
    4.	Create combined crl file and bind it to both applications
    5.  Validate each request has ssl error on cert revoked

    """
    ip = engines.dut.ip
    rest_validator = CrlValidator(app=ApiCrlClient(host=dut_hostname, ip=ip))
    gnmi_validator = CrlValidator(app=GnmiCrlClient(host=dut_hostname, ip=ip))
    with allure.step('prepare client and server certs'):
        rest_certs = rest_validator.setup_certs(engines=engines, dest="crl-rest", cert_names=["client_rest", "server_rest"])
        rest_cert = rest_certs[0]
        rest_server_cert = rest_certs[-1]
        gnmi_certs = gnmi_validator.setup_certs(engines=engines, dest="crl-gnmi", cert_names=["client_gnmi", "server_gnmi"])
        gnmi_cert = gnmi_certs[0]
        gnmi_server_cert = gnmi_certs[-1]

    rest_validator.prepare_mtls(server_certs=[rest_server_cert], client_cas=[rest_cert])
    gnmi_validator.prepare_mtls(server_certs=[gnmi_server_cert], client_cas=[gnmi_cert])
    crl_rest_name = "test_crl_rest"
    crl_gnmi_name = "test_crl_gnmi"
    system = system_with_cleanup
    rest_crl_path = rest_validator.revoke_cert(crl_name=crl_rest_name, cert=rest_cert)
    gnmi_crl_path = gnmi_validator.revoke_cert(crl_name=crl_gnmi_name, cert=gnmi_cert)

    admin = _generate_random_admin_with_apply(engines.dut, system)
    with allure.step("Make request both client request work before binding the crl"):
        rest_validator.run_client(admin, expect_success=True, client_cert=rest_cert, client_cacert=rest_server_cert)
        gnmi_validator.run_client(admin, expect_success=True, client_cert=gnmi_cert, client_cacert=gnmi_server_cert)

    rest_validator.bind_crl(rest_crl_path, crl_rest_name)
    gnmi_validator.bind_crl(gnmi_crl_path, crl_gnmi_name)
    with allure.step("Make sure both client request do not work as crl is applied"):
        rest_validator.run_client(admin, expect_success=False, client_cert=rest_cert, client_cacert=rest_server_cert)
        gnmi_validator.run_client(admin, expect_success=False, client_cert=gnmi_cert, client_cacert=gnmi_server_cert)

    with allure.step("Combine both crls into one and verify both request are not working"):
        combined_crl_path = _combine_crls(rest_crl_path, gnmi_crl_path)
        combined_crl_name = "combined_crl"
        rest_validator.bind_crl(combined_crl_path, f'{combined_crl_name}_rest')
        gnmi_validator.bind_crl(combined_crl_path, f'{combined_crl_name}_gnmi')

    with allure.step("Make sure both client request do not work as crl is applied"):
        rest_validator.run_client(admin, expect_success=False, client_cert=rest_cert, client_cacert=rest_server_cert)
        gnmi_validator.run_client(admin, expect_success=False, client_cert=gnmi_cert, client_cacert=gnmi_server_cert)

    rest_validator.unbind_crl()
    gnmi_validator.unbind_crl()
    with allure.step("Make request both client request work before binding the crl"):
        rest_validator.run_client(admin, expect_success=True, client_cert=rest_cert, client_cacert=rest_server_cert)
        gnmi_validator.run_client(admin, expect_success=True, client_cert=gnmi_cert, client_cacert=gnmi_server_cert)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_large_crl_file():
    """
    Validate we don't have time degradation with large crl

    1.	Import crl file of around 10 mb.
    2.	Verify request are working and are responding fast by running high number of requests


    """
    pytest.skip("Not implemented, as need to find large crl file")


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_continious_application(engines, validator_with_cleanup):
    """
    Validate that adding crl during open connection should not drop it, but new connection should not be allowed

    1.	Setup mTLS for gNMI
    2.  Import CRL revoking the client cert (don't bind yet)
    3.	Open long client connection (gNMI Subscribe) in background
    4.	Bind crl to application (gNMI)
    5.	Verify background subscription is still working after a delay
    6.	Verify new connection attempt with revoked cert fails
    7.  Cleanup background process and unbind CRL

    """
    crl_validator: CrlValidator = validator_with_cleanup
    with allure.step("Check if supported"):
        if not isinstance(crl_validator.app, GnmiCrlClient):
            pytest.skip("This test is only supported for gNMI")

    with allure.step("Setup certs and gNMI mTLS"):
        certs = crl_validator.setup_certs(
            engines=engines, dest="crl-continuous", cert_names=["client_cont", "server_cont"]
        )
        client_cert = certs[0]
        server_cert = certs[-1]
        crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[client_cert])

    crl_name = "test_crl_continuous"
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=client_cert)

    admin = _generate_random_admin_with_apply(engines.dut, crl_validator.system)
    gnmic_cmd = (
        GnmicCmdBuilder(crl_validator.host)
        .user_creds(admin.username, admin.password)
        .ca(server_cert.cacert)
        .cert(client_cert.private, client_cert.public)
        .subscribe(prefix="platform-general", path="", mode=GnmiMode.STREAM)
        .build()
    )
    cmd_runner = CmdRunner("GnmiClient")
    _, _, gnmi_process = cmd_runner.run_cmd_in_process(cmd=gnmic_cmd, keep_process_alive=True)

    with allure.step("Validate process is running"):
        output, err = read_process_for_specified_time(gnmi_process, GnmiConsts.SLEEP_TIME_FOR_UPDATE)
        validate_gnmi_streaming_output(output, err)

    with allure.step(f"Bind CRL '{crl_name}' to gNMI"):
        crl_validator.bind_crl(crl_path, crl_name)

    with allure.step("Attempt new connection with revoked cert and verify failure"):
        crl_validator.run_client(admin, expect_success=False, client_cert=client_cert, client_cacert=server_cert)

    with allure.step("Validate process is still running"):
        output, err = read_process_for_specified_time(gnmi_process, GnmiConsts.SLEEP_TIME_FOR_UPDATE)
        validate_gnmi_streaming_output(output, err)


def crl_factory_reset_keep_all_config_check():
    engines = TestToolkit.engines
    system = System()
    hostname = get_dut_hostname(engines)
    crl_validator = CrlValidator(app=ApiCrlClient(host=hostname, ip=engines.dut.ip))
    gnmi_validator = CrlValidator(app=GnmiCrlClient(host=hostname, ip=engines.dut.ip))
    try:
        with allure.step('prepare client and server certs'):
            certs = crl_validator.setup_certs(engines=engines, dest="crl-reset-factory", cert_names=["client_rest", "server_rest"])
            client_cert = certs[0]
            server_cert = certs[-1]

        crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[client_cert])
        crl_name = "test_crl_reset_factory"
        crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=client_cert)
        crl_validator.bind_crl(crl_path, crl_name)
        admin = UserInfo("admin", "admin", "admin")

        with allure.independent_step("Make request via client application and see it fails"):
            crl_validator.run_client(admin, expect_success=False, client_cert=client_cert, client_cacert=server_cert)

        with allure.step('save config'):
            NvueGeneralCli.save_config(engines.dut)

        yield  # do factory reset

        with allure.independent_step("Make request via client application and see it fails"):
            crl_validator.run_client(admin, expect_success=False, client_cert=client_cert, client_cacert=server_cert)

        with allure.independent_step("setup mtls by binding test certs"):
            system.gnmi_server.set(CERTIFICATE, server_cert.name).verify_result()
            system.gnmi_server.mtls.set(CA_CERTIFICATE, client_cert.cacert_name).verify_result()
            system.gnmi_server._general_cli_wrapper.apply_config(engines.dut)
            gnmi_validator.bind_crl(crl_path, crl_name)

        with allure.independent_step("Make gnmi request with same certs and get revoked error"):
            crl_validator.run_client(admin, expect_success=False, client_cert=client_cert, client_cacert=server_cert)
    finally:
        crl_validator.cleanup()
        gnmi_validator.cleanup()

        yield  # to prevent StopIteration on the 2nd next() call


############################### NEGATIVE FLOW ########################################

@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_crl_with_no_ca(engines, dut_hostname, system_with_cleanup):
    """
    Validate crl apply does not work without CA certificate

    1.	Import CRL without importing CA
    2.	Try to bind CRL and see error or should it fail on request?
    3.	Test with CA that didn't sign the CRL
    4.	Bind CA
    5.	Bind of CRL should fail

    """
    ip = engines.dut.ip
    crl_validator = CrlValidator(app=ApiCrlClient(host=dut_hostname, ip=ip))
    certs = crl_validator.setup_certs(
        engines=engines, dest="crl-no-ca", cert_names=["client1", "client2", "server"]
    )
    revoked_cert = certs[0]
    another_ca_cert = certs[1]
    server_cert = certs[-1]

    crl_name = "test_crl"
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=revoked_cert)
    with allure.step("Bind CRL without importing CA and expect failure"):
        crl_validator.bind_crl(crl_path, crl_name, should_succeed=False)

    with allure.step("Bind CRL with CA that didn't sign the CRL and expect failure"):
        crl_validator.prepare_mtls(server_certs=[server_cert], client_cas=[another_ca_cert])
        crl_validator.bind_crl(crl_path, crl_name, should_succeed=False)


@pytest.mark.system
@pytest.mark.crl
@pytest.mark.security_ci
def test_import_expired_crl(engines, dut_hostname, system_with_cleanup):
    """
    Validate that importing expired crl does not work

    1. Generate CA and certs both for client and server
    2. Generate CRL with expired date
    3. Import CRL and verify it fails


    """
    ip = engines.dut.ip
    crl_validator = CrlValidator(app=ApiCrlClient(host=dut_hostname, ip=ip))
    certs = crl_validator.setup_certs(
        engines=engines, dest="crl-expired", cert_names=["client", "server"]
    )
    revoked_cert = certs[0]
    server_cert = certs[-1]

    crl_name = "test_expired_crl"
    crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=revoked_cert)
    system = system_with_cleanup
    crl_resource = system.security.crl
    scp_player = get_scp_player(engines)

    # with allure.step("Generate an already expired CRL"):
    #     crl_path = crl_validator.revoke_cert(crl_name=crl_name, cert=revoked_cert, days_valid=-1)

    # with allure.step("Attempt to import the expired CRL and verify failure"):
    #     import_uri = generate_scp_uri_using_player(scp_player, crl_path)
    #     crl_resource.crl_id[crl_name].action_import(uri=import_uri).verify_result(should_succeed=False)

    # with allure.step("Verify expired CRL is not listed in show output"):
    #     output = crl_resource.parse_show()
    #     assert crl_name not in output, f"Expired CRL '{crl_name}' should not be present in show output after failed import"


def _combine_crls(crl1_path: str, crl2_path: str) -> str:
    """
    Combine two crl files into one
    Creates file at the path of first provided crl

    @param crl1_path: path to first crl file
    @param crl2_path: path to second crl file
    @return: path to combined crl file
    """
    output_dir = os.path.dirname(crl1_path)
    output_file_path = os.path.join(output_dir, 'combined_crl.pem')
    with open(crl1_path, 'r') as crl1_file:
        crl1_cont = crl1_file.read()

    with open(crl2_path, 'r') as crl2_file:
        crl2_cont = crl2_file.read()

    with open(output_file_path, 'w') as output_file:
        output_file.write(crl1_cont)
        output_file.write(crl2_cont)

    return output_file_path


def _verify_cmd_success(switch: LinuxSshEngine, cmd: str, should_succeed: bool = True):
    with allure.step("Verify the command is successful"):
        output = switch.run_cmd(cmd)
        exit_code = int(switch.run_cmd("echo $?").split("\n")[-1])
        if should_succeed:
            assert exit_code == 0, "The command should be successful"
        else:
            assert exit_code != 0, "The command should fail"
        return output


def _generate_random_admin_with_apply(engine: LinuxSshEngine, system: System):
    admin = set_new_random_users(1, UserRole.ADMIN)[0]
    with allure.step('apply config'):
        system._general_cli_wrapper.apply_config(engine, verify_execution=True)
    return admin
