import logging

import allure

from ngts.scripts.generate_tpm_attestation import (
    TPM_JOB_NAME,
    generate_tpm_attestation,
)

logger = logging.getLogger(__name__)


def test_generate_tpm_attestation_corim(setup_name):
    with allure.step(f"Generate TPM attestation Corim for setup {setup_name}"):
        result = generate_tpm_attestation(setup_name=setup_name)

    build_summary = f"Job: {TPM_JOB_NAME}\nBuild: #{result.build_number}\nURL: {result.build_url}\nResult: {result.result}"
    allure.attach(build_summary, "TPM attestation Jenkins build", allure.attachment_type.TEXT)
    logger.info("TPM attestation job passed: build #%s %s", result.build_number, result.build_url)
