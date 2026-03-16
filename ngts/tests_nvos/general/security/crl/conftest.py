import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates, delete_crl
from ngts.tests_nvos.general.security.crl.helpers import (
    ApiCrlValidator,
    GnmiCrlValidator,
    NmxControllerCrlValidator,
    NmxCrlValidator,
    NmxTelemetryCrlValidator,
)
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value

api_validator = pytest.param(ApiCrlValidator, id="rest")
gnmi_validator = pytest.param(GnmiCrlValidator, id="gnmi")
nmx_controller_validator = pytest.param(NmxControllerCrlValidator, id="nmx_c")
nmx_telemetry_validator = pytest.param(NmxTelemetryCrlValidator, id="nmx_t")
validators = [api_validator, gnmi_validator, nmx_controller_validator, nmx_telemetry_validator]


@pytest.fixture(scope="function")
def system_with_cleanup():
    system = System()
    yield system
    system.api.unset().verify_result()
    system.gnmi_server.unset(apply=True).verify_result()
    delete_certificates()
    delete_certificates(ca=True)
    delete_crl()


@pytest.fixture(scope="function", params=validators)
def validator_with_cleanup(request, dut_hostname, engines, devices, dut_ipv6_addr):
    ip = dut_ipv6_addr if get_cur_test_param_value(request, "addressing_type") == AddressingType.IPV6 else engines.dut.ip

    ValidatorClass = request.param

    if issubclass(ValidatorClass, NmxCrlValidator) and not devices.dut.has_nmx:
        pytest.skip("NMX is not supported on this device")

    crl_validator = ValidatorClass(host=dut_hostname, ip=ip)
    yield crl_validator
    crl_validator.cleanup()
