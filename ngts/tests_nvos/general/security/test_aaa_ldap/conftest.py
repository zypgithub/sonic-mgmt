from time import sleep

import pytest

from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AaaConsts
from ngts.tests_nvos.general.security.test_aaa_ldap.constants import LdapConsts
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def prepare_scp_test(prepare_scp):
    return


@pytest.fixture(scope='function', autouse=True)
def recover_after_aaa(cleanup_after_aaa):
    return


@pytest.fixture(scope='function', autouse=False)
def alias_ldap_server_dn(engines, request):
    """
    @summary: To allow the switch work with the docker ldap server with certificate,
        we need to add an alias of the server's ip to a specific domain name.
        Also, as cleanup step, remove the line of the added alias after the tests.
    """
    server_cert_dn = 'ldap.itzgeek.local'
    connection_method = get_cur_test_param_value(request, 'addressing_type')
    remove_etc_host_mapping_to_dn(server_cert_dn, engines.dut)
    if connection_method == AddressingType.IPV4:
        add_etc_host_mapping_to_dn(server_cert_dn, AaaConsts.VM_AAA_SERVER_IPV4_ADDR, engines.dut)
    else:
        add_etc_host_mapping_to_dn(server_cert_dn, AaaConsts.VM_AAA_SERVER_IPV6_ADDR, engines.dut)

    yield

    with allure.step('After tests: Remove docker ldap server alias from the switch'):
        remove_etc_host_mapping_to_dn(server_cert_dn, engines.dut)


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
