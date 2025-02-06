import random

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import TestFlowType
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.conftest import local_adminuser
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.system.gnmi.constants import GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import verify_gnmi_client


@pytest.mark.security_ci
@pytest.mark.system
@pytest.mark.gnmi
@pytest.mark.parametrize('addressing_type', random.sample([AddressingType.IPV4, AddressingType.IPV6], 1))
def test_gnmi_basic(addressing_type, local_adminuser, gnmi_certs, engines):
    cert: CertInfo = gnmi_certs[0]
    local_adminuser = random.choice([local_adminuser, UserInfo(engines.dut.username, engines.dut.password, 'admin')])

    # with allure.step('set gnmi certificate'):
    #     System().gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
    # with allure.step(f'run client without skip-verify flag, using right CA crt - expect success'):
    #     verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.ip, GnmiConsts.GNMI_DEFAULT_PORT, local_adminuser.username,
    #                        local_adminuser.password, False, GnmicErr.CERT_VERIFY_FAIL,
    #                        cacert=cert.cacert, debug_mode=False)

    with allure.step('run client with skip-verify flag - expect success'):
        verify_gnmi_client(TestFlowType.GOOD_FLOW, cert.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                           local_adminuser.username, local_adminuser.password, True,
                           GnmicErr.CERT_VERIFY_FAIL, debug_mode=False)
