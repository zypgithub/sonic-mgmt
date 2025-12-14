import logging

import pytest

from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.tests_nvos.general.security.platform_certificate.constants import (
    PLATFORM_CERT_FILENAME,
    REMOTE_PATH,
)
from ngts.tests_nvos.general.security.platform_certificate.helpers import (
    cleanup_remote_file,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def check_platform_certificate_ready(engines, devices):
    """
    Verify that the setup supports platform certificate testing.

    Platform certificate feature requires:
    - TPM module is present and functional
    - Platform certificate is provisioned in TPM NV storage
    - Rosalind systems only (per test plan)
    """
    with allure.step("Check if setup supports platform certificate testing"):
        tpm_tool = TpmTool(engines.dut)

        with allure.step("Verify TPM is accessible"):
            if not tpm_tool.is_tpm_attestation_ready():
                pytest.skip("TPM is not ready for testing on current setup")

        with allure.step("Verify host TPM directory exists"):
            if not tpm_tool.is_host_tpm_dir_exists():
                pytest.skip("TPM host directory /host/tpm does not exist")

        logger.info("Setup is ready for platform certificate testing")


@pytest.fixture(scope="session")
def remote_engine(engines, check_platform_certificate_ready):
    """
    Provide a remote engine for file uploads.

    Uses sonic-mgmt as the remote destination.
    """
    with allure.step("Get remote engine for file upload"):
        sonic_mgmt_engine = engines[NvosConst.SONIC_MGMT]
        sonic_mgmt_engine.run_cmd("")
        logger.info(f"Using remote engine: {sonic_mgmt_engine.ip}")
        return sonic_mgmt_engine


@pytest.fixture(scope="function")
def cleanup_uploaded_cert(remote_engine):
    """
    Clean up uploaded certificate file after test.
    """
    yield

    with allure.step("Cleanup uploaded certificate"):
        remote_file_path = f"{REMOTE_PATH}/{PLATFORM_CERT_FILENAME}"
        cleanup_remote_file(remote_engine.ip, remote_engine.username, remote_engine.password, remote_file_path)


@pytest.fixture(scope="session", autouse=True)
def platform_cert_debug_info(engines, check_platform_certificate_ready):
    """
    Log debug information before and after test module.
    """
    debug_cmds = [
        "sudo tpm2 getcap properties-variable | head -20",
        "ls -la /host/tpm/",
    ]

    with allure.step("Debug prints before test module"):
        output_lines = []
        for cmd in debug_cmds:
            result = engines.dut.run_cmd(cmd)
            output_lines.append(f"$ {cmd}\n{result}\n")
        attachment = "\n".join(output_lines)
        allure.orig_allure.attach(attachment, "platform_cert_debug_before", allure.orig_allure.attachment_type.TEXT)

    yield

    with allure.step("Debug prints after test module"):
        output_lines = []
        for cmd in debug_cmds:
            result = engines.dut.run_cmd(cmd)
            output_lines.append(f"$ {cmd}\n{result}\n")
        attachment = "\n".join(output_lines)
        allure.orig_allure.attach(attachment, "platform_cert_debug_after", allure.orig_allure.attachment_type.TEXT)
