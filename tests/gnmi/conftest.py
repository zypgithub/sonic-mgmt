import pytest
import shutil

from tests.common.helpers.assertions import pytest_require as pyrequire
from tests.common.helpers.dut_utils import check_container_state
from tests.gnmi.helper import gnmi_container, apply_cert_config, recover_cert_config, create_ext_conf,\
    prepare_root_cert, prepare_server_cert, prepare_client_cert, copy_certificate_to_dut,\
    copy_certificate_to_ptf
from tests.generic_config_updater.gu_utils import create_checkpoint, rollback

SETUP_ENV_CP = "test_setup_checkpoint"


@pytest.fixture(scope="function", autouse=True)
def skip_non_x86_platform(duthosts, rand_one_dut_hostname):
    """
    Skip the current test if DUT is not x86_64 platform.
    """
    duthost = duthosts[rand_one_dut_hostname]
    platform = duthost.facts["platform"]
    if 'x86_64' not in platform:
        pytest.skip("Test not supported for current platform. Skipping the test")


@pytest.fixture(scope="module", autouse=True)
def download_gnmi_client(duthosts, rand_one_dut_hostname, localhost):
    duthost = duthosts[rand_one_dut_hostname]
    for file in ["gnmi_cli", "gnmi_set", "gnmi_get", "gnoi_client"]:
        duthost.shell("docker cp %s:/usr/sbin/%s /tmp" % (gnmi_container(duthost), file))
        ret = duthost.fetch(src="/tmp/%s" % file, dest=".")
        gnmi_bin = ret.get("dest", None)
        shutil.copyfile(gnmi_bin, "gnmi/%s" % file)
        localhost.shell("sudo chmod +x gnmi/%s" % file)


@pytest.fixture(scope="module", autouse=True)
def setup_gnmi_server(duthosts, rand_one_dut_hostname, localhost, ptfhost):
    '''
    Create GNMI client certificates
    '''
    duthost = duthosts[rand_one_dut_hostname]

    # Check if GNMI is enabled on the device
    pyrequire(
        check_container_state(duthost, gnmi_container(duthost), should_be_running=True),
        "Test was not supported on devices which do not support GNMI!")

    prepare_root_cert(localhost)
    prepare_server_cert(duthost, localhost)
    prepare_client_cert(localhost)

    copy_certificate_to_dut(duthost)
    copy_certificate_to_ptf(ptfhost)

    create_checkpoint(duthost, SETUP_ENV_CP)
    apply_cert_config(duthost)

    yield
    # Delete all created certs
    local_command = "rm \
                        extfile.cnf \
                        gnmiCA.* \
                        gnmiserver.* \
                        gnmiclient.*"
    localhost.shell(local_command)

    # Rollback configuration
    rollback(duthost, SETUP_ENV_CP)
    recover_cert_config(duthost)
