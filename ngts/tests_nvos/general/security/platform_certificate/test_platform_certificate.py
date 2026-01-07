import logging

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.platform_certificate.constants import (
    PLATFORM_CERT_FILENAME,
    REMOTE_PATH,
    REQUIRED_CERT_FIELDS,
    UploadProtocol,
)
from ngts.tests_nvos.general.security.platform_certificate.helpers import (
    extract_serial_number,
    get_sftp_url,
    get_system_serial_number,
    get_url_for_protocol,
    parse_certificate_dates,
    sanity_check_uploaded_file,
    validate_certificate_dates,
    verify_certificate_fields,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.mark.security
@pytest.mark.platform_certificate
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_show_platform_certificate(test_api, engines, devices):
    """
    Verify nv show system security platform-certificate
    displays certificate content.

    Test Objective:
        Verify that the show command displays the platform certificate
        content from TPM.

    Precondition:
        - Platform certificate is provisioned in TPM
        - TPM is accessible

    Test Flow:
        1. Execute nv show system security platform-certificate
        2. Verify command succeeds
        3. Verify certificate fields are present in output
    """
    TestToolkit.tested_api = test_api

    with allure.step("Execute show platform-certificate command"):
        system = System()
        show_output = system.security.platform_certificate.show()

    with allure.step("Verify command returned certificate content"):
        assert show_output, "Show command returned empty output"
        logger.info(f"Platform certificate output:\n{show_output}")

    with allure.step("Verify required certificate fields are present"):
        assert verify_certificate_fields(show_output), f"Missing required certificate fields. Required: {REQUIRED_CERT_FIELDS}"


@pytest.mark.security
@pytest.mark.platform_certificate
@pytest.mark.parametrize("test_api", ApiType.ALL_TYPES)
def test_upload_platform_certificate(test_api, engines, devices, remote_engine, cleanup_uploaded_cert, nv_command: NvCommand):
    """
    Verify nv action upload system security platform-certificate
    copies certificate to remote server.

    Test Objective:
        Verify that the upload action successfully copies the platform
        certificate to a remote server and validate the certificate.

    Precondition:
        - Platform certificate is provisioned in TPM
        - TPM is accessible

    Test Flow:
        1. Execute nv action upload system security platform-certificate
        2. Verify command succeeds
        3. Verify certificate file exists on remote server
        4. Validate certificate has valid before and after dates
        5. Validate certificate serial number matches system serial number
    """
    TestToolkit.tested_api = test_api

    with allure.step("Get remote SCP URL for upload"):
        remote_url = get_sftp_url(remote_engine, PLATFORM_CERT_FILENAME)
        logger.info(f"Upload target URL: {remote_url}")

    with allure.step("Execute upload platform-certificate action"):
        system = nv_command.system
        result = system.security.platform_certificate.action_upload(remote_url=remote_url)
        result.verify_result()

    with allure.step("Verify certificate was uploaded to remote server"):
        remote_file_path = f"{REMOTE_PATH}/{PLATFORM_CERT_FILENAME}"
        upload_ok = sanity_check_uploaded_file(engines, remote_engine.ip, remote_engine.username, remote_engine.password, remote_file_path)
        assert upload_ok, "Certificate upload verification failed"

    with allure.step("Read certificate content from remote"):
        cert_content = remote_engine.run_cmd(f"openssl x509 -in {remote_file_path} -noout -text")
        logger.info(f"Uploaded certificate content:\n{cert_content}")

    with allure.step("Validate certificate dates"):
        not_before, not_after = parse_certificate_dates(cert_content)
        assert validate_certificate_dates(not_before, not_after), "Certificate dates validation failed"

    with allure.step("Validate certificate serial number"):
        device_serial_in_cert = extract_serial_number(cert_content)
        assert device_serial_in_cert is not None, "Could not extract device serial number from certificate"

        system_serial = get_system_serial_number(engines.dut)
        logger.info(f"Certificate serial: {device_serial_in_cert}, System serial: {system_serial}")
        assert device_serial_in_cert.strip() == system_serial.strip(), "Certificate serial number does not match system serial number"


@pytest.mark.security
@pytest.mark.platform_certificate
def test_show_platform_certificate_fields(engines, devices):
    """
    Additional test: Verify all expected fields in platform certificate.

    Test Objective:
        Verify that the platform certificate contains all required
        fields including Certificate, Serial Number, Issuer, Validity,
        Subject, and Signature Algorithm.
    """
    with allure.step("Show platform certificate"):
        system = System()
        show_output = system.security.platform_certificate.show()

    with allure.step("Parse certificate output"):
        parsed_output = OutputParsingTool.parse_json_str_to_dictionary(show_output)
        if parsed_output.result:
            cert_dict = parsed_output.get_returned_value()
            logger.info(f"Parsed certificate: {cert_dict}")
            allure.orig_allure.attach(str(cert_dict), "parsed_certificate", allure.orig_allure.attachment_type.JSON)

    with allure.step("Verify certificate validity dates"):
        not_before, not_after = parse_certificate_dates(show_output)
        assert not_before is not None, "Failed to parse Not Before date from certificate"
        assert not_after is not None, "Failed to parse Not After date from certificate"
        assert validate_certificate_dates(not_before, not_after), "Platform certificate dates are not valid"


@pytest.mark.security
@pytest.mark.platform_certificate
def test_upload_platform_certificate_bad_url(engines, devices):
    """
    Negative test: Verify upload fails with invalid remote URL.

    Test Objective:
        Verify that the upload action fails gracefully when given
        an invalid remote URL.
    """
    with allure.step("Attempt upload with invalid URL"):
        system = System()
        bad_url = "scp://invalid:url@bad_host/path"
        result = system.security.platform_certificate.action_upload(remote_url=bad_url)

    with allure.step("Verify upload failed"):
        result.verify_result(should_succeed=False, expected_value="Action failed")


@pytest.mark.security
@pytest.mark.platform_certificate
@pytest.mark.parametrize("protocol", list(UploadProtocol), ids=lambda p: p.value)
def test_upload_platform_certificate_protocols(protocol, engines, devices, remote_engine, cleanup_uploaded_cert, nv_command: NvCommand):
    """
    Test upload with different protocols.

    Test Objective:
        Verify that the upload action works with supported protocols
        (scp, sftp, https).

    """
    TestToolkit.tested_api = ApiType.NVUE

    with allure.step(f"Build {protocol.value} URL"):
        remote_url = get_url_for_protocol(protocol, remote_engine, PLATFORM_CERT_FILENAME)
        logger.info(f"Testing upload with {protocol.value}: {remote_url}")

    with allure.step(f"Execute upload with {protocol.value}"):
        system = nv_command.system
        result = system.security.platform_certificate.action_upload(remote_url=remote_url)
        result.verify_result()

    with allure.step("Verify certificate was uploaded"):
        if protocol == UploadProtocol.HTTPS:
            # HTTPS uploads to a web server, skip local verification
            logger.info("HTTPS upload completed, skipping local file check")
        else:
            remote_file_path = f"{REMOTE_PATH}/{PLATFORM_CERT_FILENAME}"
            upload_ok = sanity_check_uploaded_file(
                engines, remote_engine.ip, remote_engine.username, remote_engine.password, remote_file_path
            )
            assert upload_ok, f"Certificate upload with {protocol.value} failed"
