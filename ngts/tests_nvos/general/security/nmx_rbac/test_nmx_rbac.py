import logging
import os
import pytest
import time

from ngts.nvos_constants.constants_nvos import ApiType, RbacConsts
from ngts.nvos_tools.infra.NmxRbacTool import NmxRbacTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.helpers import generate_certs, get_test_certs_dir_location, setup_certs_for_tests
from ngts.tests_nvos.general.security.nmx_cert.constants import EncryptionMode
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Apps import ClusterApp
from ngts.nvos_constants.constants_nvos import ClusterConsts

logger = logging.getLogger()


@pytest.mark.cluster
@pytest.mark.security_ci
def test_import_rbac_file(random_api, cluster_rbac_tools):
    """
    Verify RBAC import works as expected
    Test flow:
        1. Import rbac file
        2. Verify rbac file is imported successfully
        3. Verify rbac file is deleted successfully
    """
    TestToolkit.tested_api = random_api
    rbac_file_name = "test_rbac_file"
    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    rbac_tool: NmxRbacTool = cluster_rbac_tools
    rbac_tool.import_rbac_file(rbac_file_name, rbac_file_path)
    rbac_tool.delete_rbac_file(rbac_file_name)


@pytest.mark.cluster
@pytest.mark.security_ci
def test_rbac_user_auth(random_api, dut_hostname, engines, cluster_rbac_tools):
    """
    Verify RBAC user authentication works as expected
    Test flow:
        1. Prepare mtls mode for nmx
        2. Update rbac mode to user-password
        3. Run app client with good user - Should succeed
        4. Run app client with bad user - Should fail
        5. Restore rbac mode
        6. Run app client with bad user - Should succeed
        7. Restore rbac file
        8. Run app client with bad user - Should succeed
    """
    TestToolkit.tested_api = random_api
    rbac_tool: NmxRbacTool = cluster_rbac_tools
    rbac_file_name = "rbac_user_auth"
    certs_location = get_test_certs_dir_location("rbac_user_auth", dut_hostname)
    scp_player = get_scp_player(engines)
    certs_location, certs = setup_certs_for_tests(
        certs_dirname_prefix=certs_location,
        certs_names=["client", "server"],
        engines=engines,
        dut_hostname=dut_hostname,
        scp_player=scp_player,
        dut_ip=engines.dut.ip,
        create_chain=False,
    )
    client_cert = certs[0]
    server_cert = certs[-1]
    rbac_tool.prepare_nmx_certs([server_cert], [client_cert], encryption_mode=EncryptionMode.MTLS)

    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    rbac_tool.import_rbac_file(rbac_file_name, rbac_file_path)
    rbac_tool.update_rbac_file(rbac_file_name)
    rbac_tool.update_rbac_mode(RbacConsts.RBAC_MODE_USERNAME_PASSWORD)
    rbac_user = UserInfo("sasha", "sasha_rbac", "admin")
    bad_rbac_user = UserInfo("bad_user", "bad_password", "admin")
    rbac_tool.run_app_client(dut_hostname, rbac_user, client_cert, server_cert, expect_success=True)
    rbac_tool.run_app_client(dut_hostname, bad_rbac_user, client_cert, server_cert, expect_success=False)

    rbac_tool.restore_rbac_mode()
    rbac_tool.run_app_client(dut_hostname, bad_rbac_user, client_cert, server_cert, expect_success=True)
    rbac_tool.restore_rbac_file()
    rbac_tool.run_app_client(dut_hostname, bad_rbac_user, client_cert, server_cert, expect_success=True)


@pytest.mark.cluster
@pytest.mark.security_ci
def test_rbac_spiffe_auth(dut_hostname, engines, cluster_rbac_tools):
    """
    Verify RBAC spiffe authentication works as expected
    Test flow:
        1. Prepare mtls mode for nmx
        2. Update rbac mode to spiffe
        3. Bind spiffe to user
        4. Run app client with good spiffe - Should succeed
        5. Run app client with bad spiffe - Should fail
        6. Restore rbac mode
        7. Run app client with bad spiffe - Should succeed
        8. Restore rbac file
        9. Run app client with bad spiffe - Should succeed
    """
    dn = dut_hostname
    ip = engines.dut.ip

    certs_location = get_test_certs_dir_location("spiffe", dut_hostname)
    bad_rbac_user = UserInfo("bad_user", "bad_password", "admin")

    with allure.step("generate random spiffe"):
        spiffe = "spiffe://example.org/spiffe1"

    with allure.step("prepare client certs"):
        cn = "nvos-client"
        cert_with_spiffe = CertInfo(
            "cert_good", "spiffe of nmx user", "", "", "", "", dn, ip, "", f"{cn}-1", [spiffe]
        )
        cert_with_bad_spiffe = CertInfo(
            "cert_bad", "bad spiffe", "", "", "", "", dn, ip, "", f"{cn}-1", [spiffe + "bad"]
        )
        client_certs_dir = os.path.join(certs_location, "client_certs")
        clients_certs = [cert_with_spiffe, cert_with_bad_spiffe]
        generate_certs(client_certs_dir, clients_certs)

    with allure.step("prepare server cert"):
        server_certs_dir = os.path.join(certs_location, "server_certs")
        server_cert = CertInfo(
            "server-cert", "server cert", "", "", "", "", dn, ip, "", f"{dn}"
        )
        server_certs = [server_cert]
        generate_certs(server_certs_dir, server_certs)

    cluster_tools: NmxRbacTool = cluster_rbac_tools
    rbac_file_name = "rbac_spiffe_auth"
    rbac_file_path = RbacConsts.NMX_RBAC_FILE_SPIFFE_PATH
    cluster_tools.prepare_nmx_certs(server_certs, clients_certs)
    cluster_tools.import_rbac_file(rbac_file_name, rbac_file_path)
    cluster_tools.update_rbac_file(rbac_file_name)
    cluster_tools.update_rbac_mode(RbacConsts.RBAC_MODE_SPIFFE)

    cluster_tools.run_app_client(dut_hostname, bad_rbac_user, cert_with_spiffe, server_cert, expect_success=True)
    cluster_tools.run_app_client(dut_hostname, bad_rbac_user, cert_with_bad_spiffe, server_cert, expect_success=False)

    cluster_tools.restore_rbac_mode()

    cluster_tools.run_app_client(dut_hostname, bad_rbac_user, cert_with_bad_spiffe, server_cert, expect_success=True)

    cluster_tools.restore_rbac_file()

    cluster_tools.run_app_client(dut_hostname, bad_rbac_user, cert_with_bad_spiffe, server_cert, expect_success=True)

######################################################## BAD FLOW ########################################################


@pytest.mark.cluster
@pytest.mark.security_ci
def test_bad_rbac_file(random_api, dut_hostname, engines, cluster_rbac_tools):
    """
    Verify RBAC user authentication works as expected
    Test flow:
        1. Prepare mtls mode for nmx
        2. Import bad rbac file
        3. Update rbac file
        3. Run app client with good user - Should succeed
        4. Restore rbac file
        5. Run app client with good user - Should succeed
    """
    TestToolkit.tested_api = random_api
    rbac_tool: NmxRbacTool = cluster_rbac_tools
    rbac_file_name = "bad_rbac_file"
    certs_location = get_test_certs_dir_location("bad_rbac_file", dut_hostname)
    scp_player = get_scp_player(engines)
    certs_location, certs = setup_certs_for_tests(
        certs_dirname_prefix=certs_location,
        certs_names=["client", "server"],
        engines=engines,
        dut_hostname=dut_hostname,
        scp_player=scp_player,
        dut_ip=engines.dut.ip,
        create_chain=False,
    )
    client_cert = certs[0]
    server_cert = certs[-1]
    rbac_tool.prepare_nmx_certs([server_cert], [client_cert])

    rbac_file_path = RbacConsts.NMX_RBAC_FILE_BAD_PATH
    rbac_tool.import_rbac_file(rbac_file_name, rbac_file_path)
    rbac_tool.update_rbac_file(rbac_file_name)
    admin = UserInfo("admin", "admin", "admin")
    rbac_tool.run_app_client(dut_hostname, admin, client_cert, server_cert, expect_success=True)

    rbac_tool.restore_rbac_file()
    rbac_tool.run_app_client(dut_hostname, admin, client_cert, server_cert, expect_success=True)


@pytest.mark.cluster
@pytest.mark.security_ci
def test_update_rbac_file_without_encryption(random_api, cluster_rbac_tools):
    """
    Verify RBAC file update does not work without encryption first
    Test flow:
        1. Import rbac file
        2. Update rbac file without encryption first - Should fail
        3. Delete rbac file
    """
    TestToolkit.tested_api = random_api
    rbac_file_name = "bad_flow_rbac_file"
    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    rbac_tool: NmxRbacTool = cluster_rbac_tools
    rbac_tool.import_rbac_file(rbac_file_name, rbac_file_path)
    rbac_tool.update_rbac_file(rbac_file_name, should_succeed=False)
    rbac_tool.delete_rbac_file(rbac_file_name)


@pytest.mark.cluster
@pytest.mark.security_ci
def nmx_rbac_upgrade_check():
    """
    Verify RBAC upgrade works as expected
    Test flow:
        1. Prepare mtls mode for nmx
        2. Update rbac mode to user-password
        3. Run app client with good user - Should succeed
        4. Run app client with bad user - Should fail
        5. Restore rbac mode
        6. Run app client with bad user - Should succeed
        7. Restore rbac file
        8. Run app client with bad user - Should succeed
    """
    cluster = Cluster()
    engines = TestToolkit.engines
    dut_hostname = engines.dut.ip

    cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
    time.sleep(10)
    cluster_app_nmx_c: ClusterApp = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER]
    cluster_app_nmx_t: ClusterApp = cluster.apps.app_name[ClusterConsts.NMX_TELEMETRY]
    rbac_tool_nmx_c = NmxRbacTool(cluster, engines.dut, cluster_app_nmx_c)
    rbac_tool_nmx_t = NmxRbacTool(cluster, engines.dut, cluster_app_nmx_t)
    rbac_file_name = "rbac_upgrade"
    certs_location = get_test_certs_dir_location("rbac_upgrade", dut_hostname)
    scp_player = get_scp_player(engines)
    certs_location, certs = setup_certs_for_tests(
        certs_dirname_prefix=certs_location,
        certs_names=["client_nmx_c", "server_nmx_c", "client_nmx_t", "server_nmx_t"],
        engines=engines,
        dut_hostname=dut_hostname,
        scp_player=scp_player,
        dut_ip=engines.dut.ip,
        create_chain=False,
    )
    client_cert_nmx_c = certs[0]
    server_cert_nmx_c = certs[1]
    client_cert_nmx_t = certs[2]
    server_cert_nmx_t = certs[3]
    rbac_tool_nmx_c.prepare_nmx_certs([server_cert_nmx_c], [client_cert_nmx_c])
    rbac_tool_nmx_t.prepare_nmx_certs([server_cert_nmx_t], [client_cert_nmx_t])

    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    rbac_tool_nmx_c.import_rbac_file(rbac_file_name, rbac_file_path)
    rbac_tool_nmx_c.update_rbac_file(rbac_file_name)
    rbac_tool_nmx_c.update_rbac_mode(RbacConsts.RBAC_MODE_USERNAME_PASSWORD)
    rbac_tool_nmx_t.update_rbac_file(rbac_file_name)
    rbac_tool_nmx_t.update_rbac_mode(RbacConsts.RBAC_MODE_USERNAME_PASSWORD)
    rbac_user = UserInfo("sasha", "sasha_rbac", "admin")
    bad_rbac_user = UserInfo("bad_user", "bad_password", "admin")

    rbac_tool_nmx_c.run_app_client(dut_hostname, rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)
    rbac_tool_nmx_c.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=False)
    rbac_tool_nmx_t.run_app_client(dut_hostname, rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)
    rbac_tool_nmx_t.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=False)

    yield  # Do upgrade

    rbac_tool_nmx_c.run_app_client(dut_hostname, rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)
    rbac_tool_nmx_c.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=False)
    rbac_tool_nmx_t.run_app_client(dut_hostname, rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)
    rbac_tool_nmx_t.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=False)

    rbac_tool_nmx_c.restore_rbac_mode()
    rbac_tool_nmx_c.restore_rbac_file()
    rbac_tool_nmx_t.restore_rbac_mode()
    rbac_tool_nmx_t.restore_rbac_file()

    yield  # to prevent StopIteration on the 2nd next() call
