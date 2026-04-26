import argparse
import logging
from collections.abc import Sequence

from ngts.nvos_tools.infra.JenkinsTool import JenkinsBuildResult, JenkinsTool

logger = logging.getLogger(__name__)

TPM_PROJECT_JOB_PATH = "/nbu-sws-nos/job"
TPM_JOB_NAME = "TPM_Build"
SUCCESS_RESULT = "SUCCESS"
DEFAULT_POLL_INTERVAL = 30
DEFAULT_TIMEOUT = 600
DEFAULT_MAIL_RECIPIENT = "ncaro@nvidia.com,nadeemn@nvidia.com,hmechlovich@nvidia.com,aromashin@nvidia.com"


def generate_tpm_attestation(
    switch_address: str,
    mail_recipient: str = DEFAULT_MAIL_RECIPIENT,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
    client: JenkinsTool | None = None,
) -> JenkinsBuildResult:
    """
    Trigger TPM attestation generation and wait for the Jenkins pipeline result.

    Args:
        switch_address: Switch IP address or hostname.
        mail_recipient: Comma-separated mail recipient list.
        poll_interval: Seconds between Jenkins status polls.
        timeout: Max seconds to wait for queue start and build completion.
        client: Optional Jenkins client, mainly for tests.

    Returns:
        JenkinsBuildResult: Final Jenkins build result.

    Raises:
        RuntimeError: If Jenkins rejects the trigger or the build does not finish successfully.
        TimeoutError: If the queue item or build does not complete within timeout.
    """
    if not switch_address:
        raise ValueError("switch_address must not be empty")
    if not mail_recipient:
        mail_recipient = DEFAULT_MAIL_RECIPIENT

    jenkins_client = client or JenkinsTool(project_job_path=TPM_PROJECT_JOB_PATH)
    params = {
        "SWITCH_ADDRESS": switch_address,
        "MAIL_RECIPIENT": mail_recipient,
    }

    logger.info("Triggering Jenkins job '%s' for switch '%s'", TPM_JOB_NAME, switch_address)
    result = jenkins_client.trigger_and_wait(TPM_JOB_NAME, params, poll_interval=poll_interval, timeout=timeout)
    if result.result != SUCCESS_RESULT:
        raise RuntimeError(f"Jenkins job '{TPM_JOB_NAME}' finished with result '{result.result}'. Build URL: {result.build_url}")

    logger.info("Jenkins job '%s' finished successfully. Build URL: %s", TPM_JOB_NAME, result.build_url)
    return result


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger TPM attestation generation through Jenkins")
    parser.add_argument("--switch-address", required=True, help="IP address or hostname of the switch")
    parser.add_argument(
        "--mail-recipient",
        default=DEFAULT_MAIL_RECIPIENT,
        help="Comma-separated mail recipient list",
    )
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL, help="Seconds between Jenkins status polls")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Max seconds to wait for Jenkins queue/build completion")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    try:
        result = generate_tpm_attestation(
            switch_address=args.switch_address,
            mail_recipient=args.mail_recipient,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    except Exception as err:
        logger.error("Failed to generate TPM attestation: %s", err)
        return 1

    logger.info("TPM attestation job passed: build #%s %s", result.build_number, result.build_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
