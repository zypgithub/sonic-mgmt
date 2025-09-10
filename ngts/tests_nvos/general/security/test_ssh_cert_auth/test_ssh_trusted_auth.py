from typing import List, Tuple

import pytest

from ngts.nvos_constants.constants_nvos import SystemConsts, UserRole
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.AuthVerifier import PKAAuthVerifier
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.general.security.test_ssh_cert_auth.helpers import (
    SshCertAuthHelper,
    get_random_key_type,
    get_random_principal,
    get_random_principals,
)
from ngts.tests_nvos.helpers.general_helpers import generate_rand_str
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.security
@pytest.mark.ssh
@pytest.mark.parametrize("addressing_type", [AddressingType.IPV4, AddressingType.IPV6])
def test_ssh_cert_basic_func(
    engines,
    local_admin_user: UserInfo,
    local_monitor_user: UserInfo,
    addressing_type: str,
    dut_ipv6_addr: str,
    nv_command: NvCommand,
    ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str],
    random_api,
):
    """
    This test performs basic functionality check of the feature.
    That user can connect without any password by providing private key.
    Should test admin/monitor user and also non-default generated users.

    Test Flow:
    1.		Generates an SSH key pair and user key pair, sign it.
    2.		Set the Principal for the User
    3.		Enable certificate-based authentication for the user
    4.		Set the trusted CA public key file (Test all supported key types)
    5.		Verify show commands
    6.		Log in using the signed certificate

    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    key_type = get_random_key_type()
    random_principal = get_random_principal()
    admin = local_admin_user
    monitor = local_monitor_user
    users = [admin, monitor]
    hostname = engines.dut.ip if addressing_type == AddressingType.IPV4 else dut_ipv6_addr

    ca_val, key_private_path = ssh_cert_auth_helper.generate_keys_and_sign_certificate(
        key_name=key_name, key_type=key_type, principals=[random_principal]
    )

    for user in users:
        _set_cert_auth(system=system, user=user, principal=random_principal, state="enabled")

    _set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)
    _verify_show_commands(system, users, key_name, key_type, random_principal, expected_state="enabled")

    _verify_user_login(admin, key_private_path, hostname, engines, expect_success=True)
    _verify_user_login(monitor, key_private_path, hostname, engines, expect_success=True)

    with allure.step("disable cert auth for user"):
        system.aaa.user.user_id[admin.username].ssh.cert_auth.disable_state(apply=True)

    _verify_show_commands(system, [admin], key_name, key_type, expected_state="disabled")

    _verify_user_login(admin, key_private_path, hostname, engines, expect_success=False)
    _verify_user_login(monitor, key_private_path, hostname, engines, expect_success=True)


@pytest.mark.security
@pytest.mark.ssh
def test_ssh_cert_auth_disabled(
    engines, nv_command: NvCommand, ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str], random_api, dut_hostname: str
):
    """
    This test performs check that user with auth disabled can’t connect to the system via key provided.

    Test Flow:
    1.		Generates an SSH key pair and user key	General generation steps should succeed
    2.		Set the Principal for the User
        nv set system aaa user {user} ssh cert-auth principals {principal}
    3.		Disable certificate-based authentication
        nv set system aaa user {user} ssh cert-auth state disabled
    4.		Set the trusted CA public key file
        nv set system ssh-server trusted-ca-keys <key-id> key <key-val>
        nv set system ssh-server trusted-ca-keys <key-id> type <key-type>
    5.		Verify show commands
        nv show system ssh-server trusted-ca-keys – Should list trusted ca
        nv show system ssh-server – Should have trusted ca key
        nv show system ssh-server trusted-ca-keys {key_id}-
        nv show system aaa user {user} ssh cert-auth

            Should list user cert-auth state as disabled
    6.		Login using the signed certificate
        Verify that user fails to login
    7.		Login using the user password
        Verify that user succeed to login
    8.		Enable certificate-based authentication
        nv set system aaa user {user} ssh cert-auth state enable
    9.		Login using the signed certificate
        Verify that user succeed to login

    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    key_type = get_random_key_type()
    random_principal = get_random_principal()
    admin = UserInfo(SystemConsts.DEFAULT_USER_ADMIN, SystemConsts.DEFAULT_USER_ADMIN, UserRole.ADMIN)
    monitor = UserInfo(SystemConsts.DEFAULT_USER_MONITOR, SystemConsts.DEFAULT_USER_MONITOR, UserRole.MONITOR)
    users = [admin, monitor]
    hostname = dut_hostname

    ca_val, key_private_path = ssh_cert_auth_helper.generate_keys_and_sign_certificate(
        key_name=key_name, key_type=key_type, principals=[random_principal]
    )

    for user in users:
        _set_cert_auth(system=system, user=user, principal=random_principal, state="disabled")

    _set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)
    _verify_show_commands(system, users, key_name, key_type, expected_state="disabled")

    _verify_user_login(admin, key_private_path, hostname, engines, expect_success=False)
    _verify_user_login(monitor, key_private_path, hostname, engines, expect_success=False)

    with allure.step("enable cert auth for user"):
        system.aaa.user.user_id[admin.username].ssh.cert_auth.enable_state(apply=True)

    _verify_show_commands(system, [admin], key_name, key_type, random_principal, expected_state="enabled")
    _verify_show_commands(system, [monitor], key_name, key_type, expected_state="disabled")

    _verify_user_login(admin, key_private_path, hostname, engines, expect_success=True)
    _verify_user_login(monitor, key_private_path, hostname, engines, expect_success=False)


@pytest.mark.security
@pytest.mark.ssh
def test_ssh_cert_auth_multiple_principals(
    engines,
    local_admin_user: UserInfo,
    nv_command: NvCommand,
    ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str],
    random_api,
    dut_hostname: str,
):
    """
    This test performs check that user can connect to the system via key provided if it has multiple principals.
    Test Flow:
    1.		Generates an SSH key pair and user key
    2.		Set the Principal for the User
        nv set system aaa user {user} ssh cert-auth principals {principal}
        nv set system aaa user {local_admin_user} ssh cert-auth principals {another_principal}
    3.		Set the trusted CA public key file
        nv set system ssh-server trusted-ca-keys <key-id> key <key-val>
        nv set system ssh-server trusted-ca-keys <key-id> type <key-type>
    4.		Verify show commands
        nv show system ssh-server trusted-ca-keys – Should list trusted ca
        nv show system ssh-server – Should have trusted ca key
        nv show system ssh-server trusted-ca-keys {key_id}-
        Should show the specified id for the key
        nv show system aaa user {user} ssh cert-auth
        -	Should list user cert-auth state as enabled
    5.		Login using the signed certificate
        Verify that user succeed to login
        Verify that another user succeed to login with another principal
    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    key_type = get_random_key_type()
    random_principals = get_random_principals(number_of_values_to_select=2)
    random_principal = random_principals[0]
    another_random_principal = random_principals[1]
    admin = UserInfo(SystemConsts.DEFAULT_USER_ADMIN, SystemConsts.DEFAULT_USER_ADMIN, UserRole.ADMIN)
    hostname = dut_hostname

    ca_val, key_private_path = ssh_cert_auth_helper.generate_keys_and_sign_certificate(
        key_name=key_name, key_type=key_type, principals=[random_principal, another_random_principal]
    )

    _set_cert_auth(system=system, user=admin, principal=random_principal, state="enabled")
    _set_cert_auth(system=system, user=local_admin_user, principal=another_random_principal, state="enabled")

    _set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)

    _verify_show_commands(system, [admin], key_name, key_type, random_principal, expected_state="enabled")
    _verify_show_commands(system, [local_admin_user], key_name, key_type, another_random_principal, expected_state="enabled")

    _verify_user_login(admin, key_private_path, hostname, engines, expect_success=True)
    _verify_user_login(local_admin_user, key_private_path, hostname, engines, expect_success=True)


@pytest.mark.security
@pytest.mark.ssh
def test_ssh_cert_auth_multiple_keys(
    engines,
    local_admin_user: UserInfo,
    nv_command: NvCommand,
    ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str],
    random_api,
    dut_hostname: str,
):
    """
    This test performs check that user can connect to the system via key provided if it has multiple keys.
    Test Flow:
    1.		Generates an SSH key pair and user key
    2.      Generate another key pair
    3.		Set the Principal for the User
        nv set system aaa user {user} ssh cert-auth principals {principal}
    4.		Set the trusted CA public key file
        nv set system ssh-server trusted-ca-keys <key-id> key <key-val>
        nv set system ssh-server trusted-ca-keys <key-id> type <key-type>
    4.		Verify show commands
        nv show system ssh-server trusted-ca-keys – Should list trusted ca
        nv show system ssh-server – Should have trusted ca key
        nv show system ssh-server trusted-ca-keys {key_id}-
    Should show the specified id for the key
    5.		Login using the signed certificate
        Verify that user succeed to login with the first key
        Verify that user succeed to login with the second key
    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    another_key_name = generate_rand_str(str_len=10)
    key_type = get_random_key_type()
    random_principal = get_random_principal()
    admin = UserInfo(SystemConsts.DEFAULT_USER_ADMIN, SystemConsts.DEFAULT_USER_ADMIN, UserRole.ADMIN)
    hostname = dut_hostname

    _, _, key_path = ssh_cert_auth_helper.generate_user_key_pair(key_name, key_type)
    _, _, another_key_path = ssh_cert_auth_helper.generate_user_key_pair(another_key_name, key_type)
    ca_val, key_type, _ = ssh_cert_auth_helper.generate_ca_key_pair(key_name, key_type)
    ssh_cert_auth_helper.sign_user_certificate(f"{key_name}_ca", f"{key_name}_key", principals=[random_principal])
    ssh_cert_auth_helper.sign_user_certificate(f"{key_name}_ca", f"{another_key_name}_key", principals=[random_principal])

    _set_cert_auth(system=system, user=admin, principal=random_principal, state="enabled")

    _set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)

    _verify_show_commands(system, [admin], key_name, key_type, random_principal, expected_state="enabled")

    _verify_user_login(admin, key_path, hostname, engines, expect_success=True)
    _verify_user_login(admin, another_key_path, hostname, engines, expect_success=True)


@pytest.mark.security
@pytest.mark.ssh
def test_bad_principal(
    engines,
    local_admin_user: UserInfo,
    nv_command: NvCommand,
    ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str],
    random_api,
    dut_hostname: str,
):
    """
    This test performs check that user can't connect to the system via key provided if the principal is not matching.
    Test Flow:
        1. Generates an SSH key pair and user key
        2. Set bad principal for the user
        3. Set the trusted CA public key file
        4. Verify show commands
        5. Login using the signed certificate
        6. Verify that user fails to login
    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    key_type = get_random_key_type()
    random_principal = get_random_principal()
    bad_principal = "bad_principal"
    admin = local_admin_user
    hostname = dut_hostname

    _, _, key_path = ssh_cert_auth_helper.generate_user_key_pair(key_name, key_type)
    ca_val, key_type, _ = ssh_cert_auth_helper.generate_ca_key_pair(key_name, key_type)
    ssh_cert_auth_helper.sign_user_certificate(f"{key_name}_ca", f"{key_name}_key", principals=[random_principal])

    _set_cert_auth(system=system, user=admin, principal=bad_principal, state="enabled")
    _set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)
    _verify_show_commands(system, [admin], key_name, key_type, bad_principal, expected_state="enabled")
    _verify_user_login(admin, key_path, hostname, engines, expect_success=False)


@pytest.mark.security
@pytest.mark.ssh
def test_bad_key_type(
    engines,
    local_admin_user: UserInfo,
    nv_command: NvCommand,
    ssh_cert_auth_helper_with_cleanup: Tuple[SshCertAuthHelper, str],
    random_api,
    dut_hostname: str,
):
    """
    This test performs check that user can't connect to the system via key provided if the key type is not matching.
    Test Flow:
        1. Generates an SSH key pair and user key
        2. Set bad key type for the user
        3. Set the trusted CA public key file
        4. Verify show commands
        5. Login using the signed certificate
        6. Verify that user fails to login
    """
    system = nv_command.system
    ssh_cert_auth_helper, key_name = ssh_cert_auth_helper_with_cleanup
    key_type = get_random_key_type()
    random_principal = get_random_principal()
    bad_key_type = get_random_key_type(exclude=[key_type])
    admin = local_admin_user
    hostname = dut_hostname

    _, _, key_path = ssh_cert_auth_helper.generate_user_key_pair(key_name, key_type)
    ca_val, key_type, _ = ssh_cert_auth_helper.generate_ca_key_pair(key_name, key_type)
    ssh_cert_auth_helper.sign_user_certificate(f"{key_name}_ca", f"{key_name}_key", principals=[random_principal])

    _set_cert_auth(system=system, user=admin, principal=random_principal, state="enabled")
    _set_trusted_ca_key(system, key_name, bad_key_type, ca_val, apply=True)
    _verify_show_commands(system, [admin], key_name, bad_key_type, random_principal, expected_state="enabled")
    _verify_user_login(admin, key_path, hostname, engines, expect_success=False)


def _verify_show_commands(
    system: System,
    users: List[UserInfo],
    key_name: str,
    key_type: str,
    random_principal: str = "",
    expected_state: str = "",
):
    with allure.step("verify show commands"):
        _verify_trusted_ca_key(system, key_name, key_type)
        _verify_users_principals_and_state(system, users, random_principal, expected_state)


def _verify_trusted_ca_key(system: System, key_name: str, key_type: str):
    """
    Verify the trusted CA key is set as expected.
    """
    with allure.independent_step(f"verify trusted ca key for {key_name}"):
        out = system.ssh_server.trusted_ca_keys.key_id[key_name].parse_show()
        assert out.get("key", "") == "*", f"trusted ca key val is not set as expected. actual: {out}"
        assert out.get("type", "") == key_type, f"trusted ca key type is not set as expected. actual: {out}"


def _verify_users_principals_and_state(system: System, users: List[UserInfo], random_principal: str, expected_state: str):
    """
    Verify the users principals and state are set as expected.
    """
    for user in users:
        with allure.independent_step(f"verify user {user.username} role {user.role} principals and state {expected_state}"):
            out = system.aaa.user.user_id[user.username].ssh.cert_auth.parse_show()
            out_principals = out.get("principals", "")
            out_state = out.get("state", "")
            if random_principal:
                assert random_principal in out_principals, f"principals for user {user.username} are not set as expected. actual: {out}"
            else:
                assert not out_principals, f"principals for user {user.username} are not set as expected. actual: {out}"
            assert out_state == expected_state, f"user {user.username} state is not set as expected. actual: {out}"


def _set_trusted_ca_key(system: System, key_name: str, key_type: str, ca_val: str, apply: bool = False):
    with allure.step("set trusted ca"):
        system.ssh_server.trusted_ca_keys.key_id[key_name].set_key_val(ca_val)
        system.ssh_server.trusted_ca_keys.key_id[key_name].set_key_type(key_type, apply=apply)


def _set_cert_auth(system: System, user: UserInfo, principal: str, state: str, apply: bool = False):
    with allure.step(f"set cert auth state {state} and principal {principal} for user {user.username}"):
        system.aaa.user.user_id[user.username].ssh.cert_auth.principals[principal].set().verify_result()
        if state == "enabled":
            system.aaa.user.user_id[user.username].ssh.cert_auth.enable_state(apply=apply)
        elif state == "disabled":
            system.aaa.user.user_id[user.username].ssh.cert_auth.disable_state(apply=apply)
        else:
            raise ValueError(f"invalid state: {state}")


def _verify_user_login(user: UserInfo, key_private_path: str, hostname: str, engines, expect_success: bool = True):
    with allure.step(f"log in with certificate for user {user.username} with role {user.role}, expect success: {expect_success}"):
        session_obj = PKAAuthVerifier(username=user.username, private_key_path=key_private_path, hostname=hostname, engines=engines)
        session_obj.verify_authentication(expect_success=expect_success)
        if expect_success:
            session_obj.verify_authorization(user_is_admin=user.role == UserRole.ADMIN)
