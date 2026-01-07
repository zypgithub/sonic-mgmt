import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.security.platform_certificate.constants import (
    REMOTE_URL_TEMPLATE,
    REMOTE_PATH_HTTPS,
    REQUIRED_CERT_FIELDS,
    CERT_FIELD_NOT_BEFORE,
    CERT_FIELD_NOT_AFTER,
    CERT_FIELD_SERIAL_NUMBER,
    UploadProtocol,
)
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


def get_url_for_protocol(
    protocol: UploadProtocol,
    remote_engine: LinuxSshEngine,
    dst_filename: str
) -> str:
    """
    Build a URL for the given upload protocol.

    Args:
        protocol: The upload protocol (SCP, SFTP, HTTPS)
        remote_engine: Remote engine with connection details
        dst_filename: Destination filename

    Returns:
        URL string for the specified protocol
    """
    if protocol == UploadProtocol.HTTPS:
        return f"{REMOTE_PATH_HTTPS}{dst_filename}"

    return REMOTE_URL_TEMPLATE.format(
        protocol=protocol.value,
        username=remote_engine.username,
        password=remote_engine.password,
        host=remote_engine.ip,
        filename=dst_filename
    )


def get_sftp_url(remote_engine: LinuxSshEngine, dst_filename: str) -> str:
    """
    Build an SFTP URL for uploading files.

    Args:
        remote_engine: Remote engine with connection details
        dst_filename: Destination filename

    Returns:
        SFTP URL string
    """
    return get_url_for_protocol(
        UploadProtocol.SFTP, remote_engine, dst_filename
    )


def verify_certificate_fields(cert_output: str) -> bool:
    """
    Verify that required certificate fields are present in output.

    Args:
        cert_output: Certificate show command output

    Returns:
        True if all required fields are present
    """
    with allure.step("Verify required certificate fields are present"):
        missing_fields = []
        for field in REQUIRED_CERT_FIELDS:
            if field not in cert_output:
                missing_fields.append(field)

        if missing_fields:
            logger.error(f"Missing certificate fields: {missing_fields}")
            return False

        logger.info("All required certificate fields are present")
        return True


def parse_certificate_dates(cert_output: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse Not Before and Not After dates from certificate output.

    Args:
        cert_output: Certificate show command output

    Returns:
        Tuple of (not_before, not_after) datetime objects
    """
    not_before = None
    not_after = None

    with allure.step("Parse certificate validity dates"):
        # Handle both escaped newlines (\n as literal) and actual newlines
        normalized_output = cert_output.replace("\\n", "\n")

        # Pattern to match dates like "Dec 14 00:00:00 2025 GMT"
        date_pattern = r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})"

        for line in normalized_output.split("\n"):
            if CERT_FIELD_NOT_BEFORE in line and not_before is None:
                match = re.search(date_pattern, line)
                if match:
                    try:
                        not_before = datetime.strptime(
                            match.group(1), "%b %d %H:%M:%S %Y"
                        )
                    except ValueError as e:
                        logger.warning(f"Failed to parse Not Before date: {e}")

            if CERT_FIELD_NOT_AFTER in line and not_after is None:
                after_idx = line.find(CERT_FIELD_NOT_AFTER)
                if after_idx >= 0:
                    search_text = line[after_idx:]
                    match = re.search(date_pattern, search_text)
                    if match:
                        try:
                            not_after = datetime.strptime(
                                match.group(1), "%b %d %H:%M:%S %Y"
                            )
                        except ValueError as e:
                            logger.warning(f"Failed to parse Not After date: {e}")

        logger.info(f"Parsed dates - Not Before: {not_before}, Not After: {not_after}")
        return not_before, not_after


def validate_certificate_dates(not_before: Optional[datetime], not_after: Optional[datetime]) -> bool:
    """
    Validate that certificate dates are valid (not expired, not future).

    Args:
        not_before: Certificate start date
        not_after: Certificate end date

    Returns:
        True if certificate is currently valid
    """
    with allure.step("Validate certificate is currently valid"):
        if not_before is None or not_after is None:
            logger.error("Could not parse certificate dates")
            return False

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if now < not_before:
            logger.error(f"Certificate not yet valid. Not Before: {not_before}")
            return False

        if now > not_after:
            logger.error(f"Certificate expired. Not After: {not_after}")
            return False

        logger.info("Certificate dates are valid")
        return True


def extract_serial_number(cert_output: str) -> Optional[str]:
    """
    Extract the device serial number from the certificate Subject field.

    Looks for 'serialNumber = <value>' in the Subject line.

    Args:
        cert_output: Certificate show command output

    Returns:
        Device serial number string or None
    """
    with allure.step("Extract device serial number from certificate"):
        normalized_output = cert_output.replace("\\n", "\n")

        # Match serialNumber in Subject field: serialNumber = MT2545XZ05NY
        match = re.search(r'serialNumber\s*=\s*([^\s,]+)', normalized_output)
        if match:
            serial = match.group(1)
            logger.info(f"Extracted device serial number: {serial}")
            return serial

        logger.warning("Could not extract device serial number from certificate")
        return None


def get_system_serial_number(engine: LinuxSshEngine) -> Optional[str]:
    """
    Get the system serial number from the switch.

    Args:
        engine: SSH engine for the DUT

    Returns:
        System serial number or None
    """
    with allure.step("Get system serial number"):
        try:
            output = engine.run_cmd("sudo dmidecode -s system-serial-number")
            serial = output.strip()
            logger.info(f"System serial number: {serial}")
            return serial
        except Exception as e:
            logger.error(f"Failed to get system serial number: {e}")
            return None


def sanity_check_uploaded_file(engines, remote_ip: str, remote_user: str, remote_password: str, remote_file_path: str) -> bool:
    """
    Verify that uploaded certificate file exists and is valid.

    Args:
        engines: Test engines
        remote_ip: Remote server IP
        remote_user: Remote server username
        remote_password: Remote server password
        remote_file_path: Path to uploaded file on remote server

    Returns:
        True if file exists and is valid
    """
    with allure.step("Sanity check uploaded certificate file"):
        with allure.step("Connect to remote host"):
            remote_engine = LinuxSshEngine(remote_ip, remote_user, remote_password)
            remote_engine.run_cmd("")

        with allure.step("Verify file exists"):
            ls_output = remote_engine.run_cmd(f"ls -l {remote_file_path}")
            if "No such file" in ls_output:
                logger.error(f"File not found: {remote_file_path}")
                return False

        with allure.step("Verify file is not empty"):
            size_output = remote_engine.run_cmd(f'stat --printf="%s" {remote_file_path}')
            try:
                size = int(size_output.strip())
                if size == 0:
                    logger.error("Uploaded file is empty")
                    return False
                logger.info(f"Uploaded file size: {size} bytes")
            except ValueError:
                logger.warning("Could not determine file size")

        with allure.step("Verify certificate format with openssl"):
            verify_output = remote_engine.run_cmd(f"openssl x509 -in {remote_file_path} -noout -text 2>&1")
            if "unable to load certificate" in verify_output.lower():
                logger.error("Uploaded file is not a valid certificate")
                return False

            logger.info("Uploaded certificate is valid")
            return True


def cleanup_remote_file(remote_ip: str, remote_user: str, remote_password: str, remote_file_path: str):
    """
    Clean up uploaded file from remote server.

    Args:
        remote_ip: Remote server IP
        remote_user: Remote server username
        remote_password: Remote server password
        remote_file_path: Path to file to remove
    """
    with allure.step(f"Clean up remote file: {remote_file_path}"):
        try:
            remote_engine = LinuxSshEngine(remote_ip, remote_user, remote_password)
            remote_engine.run_cmd(f"rm -f {remote_file_path}")
            logger.info(f"Removed remote file: {remote_file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup remote file: {e}")
