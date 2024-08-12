from time import sleep

import pytest

from ngts.tests_nvos.general.security.test_aaa_ldap.constants import LdapConsts
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def prepare_scp_test(prepare_scp):
    return


@pytest.fixture(scope='function', autouse=True)
def recover_after_aaa(cleanup_after_aaa):
    return


@pytest.fixture(scope='function', autouse=False, params=[LdapConsts.IPV4, LdapConsts.IPV6])
def alias_ldap_server_dn(engines, request):
    """
    @summary: To allow the switch work with the docker ldap server with certificate,
        we need to add an alias of the server's ip to a specific domain name.
        Also, as cleanup step, remove the line of the added alias after the tests.
    """
    connection_method = request.param
    if connection_method == LdapConsts.IPV4:
        alias_line = LdapConsts.DOCKER_LDAP_SERVER_HOST_ALIAS_IPV4
        remove_alias_cmd = "sudo sed -i '/10\\.237\\.0\\.86 ldap\\.itzgeek\\.local/d' /etc/hosts"
    else:
        alias_line = LdapConsts.DOCKER_LDAP_SERVER_HOST_ALIAS_IPV6
        remove_alias_cmd = "sudo sed -i '/fdfd:fdfd:10:237:250:56ff:fe1b:56 ldap\\.itzgeek\\.local/d' /etc/hosts"

    with allure.step(f'Before tests: Verify that docker ldap server dn has {connection_method} alias in the switch'):
        output = engines.dut.run_cmd('cat /etc/hosts')
        if alias_line not in output:
            with allure.step('Switch does not have existing alias for the docker ldap server. Add the alias'):
                engines.dut.run_cmd(f'echo "{alias_line} " | sudo tee -a /etc/hosts')

            with allure.step('Verify alias wad added'):
                output = engines.dut.run_cmd('cat /etc/hosts')
                assert alias_line in output, \
                    f'Error: docker server alias was not found in /etc/hosts .\n' \
                    f'/etc/hosts content: {output}\n' \
                    f'Expected: {alias_line}'

    yield

    with allure.step('After tests: Remove docker ldap server alias from the switch'):
        # engines.dut.run_cmd("sudo sed -i '$ d' /etc/hosts")
        engines.dut.run_cmd(remove_alias_cmd)


@pytest.fixture(scope='function', autouse=False)
def backup_and_restore_certificates(engines):
    """
    @summary: To allow the switch work with the docker ldap server with cert-verify enabled,
        we need to get the right certificate, which is kept in specific shared location.
    """
    with allure.step('Before tests: Add ldap server certificate'):
        with allure.step('Backup original certificates file'):
            engines.dut.run_cmd(f'sudo cp -f {LdapConsts.SWITCH_CA_FILE} {LdapConsts.SWITCH_CA_BACKUP_FILE}')

    yield

    with allure.step('After tests: Restore certificates file'):
        engines.dut.run_cmd(f"sudo mv -f {LdapConsts.SWITCH_CA_BACKUP_FILE} {LdapConsts.SWITCH_CA_FILE}")

    with allure.step('Restart nslcd service'):
        engines.dut.run_cmd('sudo service nslcd restart')
        sleep(3)
