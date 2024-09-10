import logging

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.tpm_attestation.constants import *
from ngts.tools.test_utils import allure_utils as allure


def verify_only_aik_at_tpm_dir(engines):
    """
    Verify that tpm directory contains AIK file only
    """
    with allure.step('verify dir contain only AIK file'):
        files = set(TpmTool(engines.dut).get_files_in_tpm_dir())
        assert files == TPM_DIR_CONTENT_AFTER_INIT, \
            f'''tpm dir content is not as expected.
            expected: {TPM_DIR_CONTENT_AFTER_INIT}
            actual: {files}'''


def get_scp_url(remote_engine, dst_filename):
    return REMOTE_SCP_URL.format(remote_engine.username, remote_engine.password, remote_engine.ip, dst_filename)


def get_file_creation_time(engine: LinuxSshEngine, file_path: str) -> str:
    ls_output = engine.run_cmd(f'ls -l {file_path}')
    return ' '.join(ls_output.split()[5:8])


def sanity_check_uploaded_file(engines, dut_file_path, remote_ip, remote_user, remote_password, remote_file_path):
    """
    Sanity check for an uploaded file
    1. compare size of uploaded file and original file at dut
    2. compare tail of uploaded file and original file at dut

    @param engines: test engines
    @param dut_file_path: path of original file at dut
    @param remote_ip: ip to remote destination where file was uploaded to
    @param remote_user: username to remote destination where file was uploaded to
    @param remote_password: password to remote destination where file was uploaded to
    @param remote_file_path: path of uploaded file at remote destination
    """
    with allure.step('connect remote host where file uploaded to'):
        remote_engine = LinuxSshEngine(remote_ip, remote_user, remote_password)
        remote_engine.run_cmd('')
    with allure.step('compare file size at remote and switch'):
        size_at_dut = engines.dut.run_cmd(f'ls -l {dut_file_path}').split()[4]
        size_at_remote = remote_engine.run_cmd(f'ls -l {remote_file_path}').split()[4]
        assert size_at_dut == size_at_remote, \
            f'''AIK file size is not equal at remote and dut
            size at dut: {size_at_dut}
            size at remote: {size_at_remote}'''
    with allure.step('compare file tail at remote and switch'):
        tail_at_dut = engines.dut.run_cmd(f'tail {dut_file_path}')
        tail_at_remote = remote_engine.run_cmd(f'tail {remote_file_path}')
        assert tail_at_dut == tail_at_remote, \
            f'''AIK file tail is not equal at remote and dut
            tail at dut: {tail_at_dut}
            tail at remote: {tail_at_remote}'''


def sanity_check_generated_quote(engines, nonce: str):
    """
    Sanity check for generated quote file
    1. run check quote on the switch
    2. verify it is not throwing error
    @param engines: engines object
    @param nonce: nonce used for the checked quote generation (str)
    """
    assert TpmTool(engines.dut).is_check_quote_ok(nonce), 'check quote returned error'


def tpm_attestation_factory_reset_no_params_check(engines=None):
    engines = engines or TestToolkit.engines
    dut_device: BaseDevice = TestToolkit.devices.dut

    if dut_device.supports_tpm_testing:
        with allure.step('generate tpm quote'):
            System().security.tpm.action_generate_quote(VALID_PCRS_PARAM, VALID_NONCE_PARAM).verify_result()
    else:
        logging.info('dut device does not support TPM testing')

    yield   # do factory reset

    if dut_device.supports_tpm_testing:
        with allure.step('verify no tpm quote file'):
            verify_only_aik_at_tpm_dir(engines)
    else:
        logging.info('dut device does not support TPM testing')

    yield    # to prevent StopIteration on the 2nd next() call


factory_reset_tpm_checker = tpm_attestation_factory_reset_no_params_check()    # generator
