from ngts.tests_nvos.general.security.crl.helpers import ApiCrlClient, GnmiCrlClient, NmxControllerCrlClient, NmxCrlClient, NmxTelemetryCrlClient
import pytest

from ngts.nvos_tools.infra.CrlValidator import CrlValidator
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates, delete_crl
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value

api_client = pytest.param(ApiCrlClient, id="rest")
gnmi_client = pytest.param(GnmiCrlClient, id="gnmi")
nmx_controller_client = pytest.param(NmxControllerCrlClient, id="nmx_c")
nmx_telemetry_client = pytest.param(NmxTelemetryCrlClient, id="nmx_t")
# TODO: add nmx telemetry client after it is merged
clients = [api_client, gnmi_client, nmx_controller_client]


@pytest.fixture(scope="function")
def system_with_cleanup():
    system = System()
    yield system
    system.api.unset().verify_result()
    system.gnmi_server.unset(apply=True).verify_result()
    delete_certificates()
    delete_certificates(ca=True)
    delete_crl()


@pytest.fixture(scope="function", params=clients)
def validator_with_cleanup(request, dut_hostname, engines, devices, dut_ipv6_addr):
    ip = dut_ipv6_addr if get_cur_test_param_value(
        request, "addressing_type") == AddressingType.IPV6 else engines.dut.ip
    Client = request.param
    if issubclass(Client, NmxCrlClient) and not devices.dut.has_nmx:
        pytest.skip("NMX is not supported on this device")
    crl_validator = CrlValidator(app=Client(host=dut_hostname, ip=ip))
    yield crl_validator
    crl_validator.cleanup()
