'''
Secure Boot Suite case:

In this test file we introduce different cases for secure boot feature.
Secure Boot is a feature that validates secure boot and only signed modules are running.

In order to run this test, you need to specify the following argument: kernel_module_path
'''
import logging
import os
import random
import re
import time

import pytest

from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.KernelModulesTool import KernelModulesTool
from ngts.tests_nvos.general.security.test_secure_boot.constants import ChainOfTrustNode, SecureBootConsts, SigningState
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


def get_system_chain_of_trust_node_file_switch_path(chain_of_trust_node: str, serial_engine: PexpectSerialEngine) -> str:
    assert chain_of_trust_node in ChainOfTrustNode.ALL_NODES, f'chain of trust must be in: {ChainOfTrustNode.ALL_NODES}'
    if chain_of_trust_node == ChainOfTrustNode.SHIM:
        return SecureBootConsts.SHIM_FILEPATH
    elif chain_of_trust_node == ChainOfTrustNode.GRUB:
        return SecureBootConsts.GRUB_FILEPATH
    else:
        # vmlinuz
        output = serial_engine.run_cmd_and_get_output(f'ls {SecureBootConsts.VMLINUZ_DIR}')
        path = re.findall(SecureBootConsts.VMLINUZ_REGEX, output)[0]
        return SecureBootConsts.VMLINUZ_DIR + path


def manipulate_nvos_system_file_signature(chain_of_trust_node: str, dut_engine: ProxySshEngine,
                                          serial_engine: PexpectSerialEngine):
    assert chain_of_trust_node in ChainOfTrustNode.ALL_NODES, f'chain of trust must be in: {ChainOfTrustNode.ALL_NODES}'

    with allure.step(f'Download orig {chain_of_trust_node} file from the switch'):
        system_file_switch_path = get_system_chain_of_trust_node_file_switch_path(chain_of_trust_node, serial_engine)
        filename = os.path.split(system_file_switch_path)[1]
        system_file_local_path = f'{SecureBootConsts.LOCAL_SECURE_BOOT_DIR}/{filename}'
        system_file_switch_tmp_path = f'{SecureBootConsts.TMP_FOLDER}/{filename}'
        with allure.step('Copy system file to tmp dir on switch and make it readable for sudoers'):
            logging.info(f'Copy system file to tmp dir on switch:\nSwitch (src) path: {system_file_switch_path}\nSwitch (dst) path: {system_file_switch_tmp_path}')
            dut_engine.run_cmd(f'sudo cp -f {system_file_switch_path} {system_file_switch_tmp_path}', validate=True)
            dut_engine.run_cmd(f'sudo chown admin {system_file_switch_tmp_path}', validate=True)
        with allure.step(f'Download using scp:\nSwitch (src) path: {system_file_switch_path}\nLocal (dst) path: {system_file_local_path}'):
            scp_file(
                player=dut_engine,
                src_path=system_file_switch_tmp_path,
                dst_path=system_file_local_path,
                download_from_remote=True
            )

    with allure.step(f'Manipulate binary content in {chain_of_trust_node} file'):
        with open(system_file_local_path, 'rb') as file_obj:
            original_content = file_obj.read()
        assert original_content, f'Cannot corrupt empty file: {system_file_local_path}'

        with open(system_file_local_path, 'rb+') as file_obj:
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            corruption_offset = max(file_size - 64, 0)
            file_obj.seek(corruption_offset)
            bytes_to_corrupt = file_obj.read(16)
            assert bytes_to_corrupt, f'Cannot read bytes to corrupt at offset {corruption_offset}'
            file_obj.seek(corruption_offset)
            file_obj.write(bytes(current_byte ^ 0xA5 for current_byte in bytes_to_corrupt))
            file_obj.flush()
            os.fsync(file_obj.fileno())

        with open(system_file_local_path, 'rb') as file_obj:
            corrupted_content = file_obj.read()
        assert corrupted_content != original_content, f'Corruption did not change file content: {system_file_local_path}'
        assert len(corrupted_content) == len(original_content), \
            f'Unexpected file size change after corruption. Original: {len(original_content)}, Corrupted: {len(corrupted_content)}'

    with allure.step(f'Update {chain_of_trust_node} file on the switch'):
        with allure.step(f'Upload new {chain_of_trust_node} file to the switch'):
            logging.info(f'Upload using scp:\nLocal (src) path: {system_file_local_path}\nSwitch (dst) path: {system_file_switch_tmp_path}')
            scp_file(
                player=dut_engine,
                src_path=system_file_local_path,
                dst_path=system_file_switch_tmp_path,
                download_from_remote=False
            )
        with allure.step(f'Override orig {chain_of_trust_node} file with the new one'):
            logging.info(f'Copy file on switch:\nSwitch (src) path: {system_file_switch_tmp_path}\nSwitch (dst) path: {system_file_switch_path}')
            dut_engine.run_cmd(f'sudo cp -f {system_file_switch_tmp_path} {system_file_switch_path}', validate=True)
        with allure.step(f'Verify updated {chain_of_trust_node} file on switch matches uploaded corrupted file'):
            dut_engine.run_cmd(f'sudo cmp -s {system_file_switch_tmp_path} {system_file_switch_path}', validate=True)

    with allure.step('Remove file from local fs'):
        os.remove(system_file_local_path)


@pytest.mark.track_serial_console
@pytest.mark.checklist
@pytest.mark.secure_boot
@pytest.mark.timeout(20 * MINUTE, func_only=True)
@pytest.mark.parametrize('tested_chain_of_trust_node', [random.choice(ChainOfTrustNode.ALL_NODES)])
def test_secure_boot_unsigned_system_file(tested_chain_of_trust_node: str, serial_engine: PexpectSerialEngine,
                                          mount_uefi_disk_partition, engines, restore_image_path, is_secure_boot_enabled,
                                          topology_obj, devices):
    assert tested_chain_of_trust_node in ChainOfTrustNode.ALL_NODES, \
        f'chain of trust must be in: {ChainOfTrustNode.ALL_NODES}'
    dut_device: BaseDevice = devices.dut

    with allure.step(f'Manipulate signature of {tested_chain_of_trust_node} file on the switch'):
        manipulate_nvos_system_file_signature(
            chain_of_trust_node=tested_chain_of_trust_node,
            dut_engine=engines.dut,
            serial_engine=serial_engine
        )

    try:
        with allure.step('Reboot the system'):
            expected_messages = SecureBootConsts.INVALID_SIGNATURE
            _, respond_index = serial_engine.run_cmd(
                cmd='sudo reboot',
                expected_value=expected_messages,
                timeout=dut_device.timeout_reboot_to_grub_menu + 1 * MINUTE
            )

        with allure.step(f'Verify got one of expected messages: {expected_messages}'):
            expected_indexes = list(range(len(expected_messages)))
            assert respond_index in expected_indexes, f'Wrong respond index.\nExpected: {expected_indexes}\n' \
                f'Actual: {respond_index}'
    finally:
        with allure.step(f'Recovery after test - reinstall nvos: {restore_image_path}'):
            NvueGeneralCli(engines.dut, devices.dut).install_image_via_onie(topology_obj, restore_image_path)
        with allure.step('disconnect engine'):
            engines.dut.disconnect()


def get_kernel_module_path(signing_state: str, engines, kernel_modules_tool: KernelModulesTool):
    assert signing_state in SigningState.ALL_STATES, f'Given signing state arg {signing_state} is not in {SigningState.ALL_STATES}'

    if signing_state == SigningState.SIGNED:
        with allure.step(f'Get ko file path of existing signed kernel module: {SecureBootConsts.SIGNED_KERNEL_MODULE_KO_FILENAME}'):
            ko_file_path = kernel_modules_tool.get_kernel_module_ko_file_path(
                SecureBootConsts.SIGNED_KERNEL_MODULE_KO_FILENAME).get_returned_value()
        with allure.step(f'Copy signed kernel module {SecureBootConsts.SIGNED_KERNEL_MODULE_KO_FILENAME} to /tmp'):
            engines.dut.run_cmd(f'sudo cp {ko_file_path} {SecureBootConsts.TMP_FOLDER}')
    else:
        with allure.step(f'Upload unsigned kernel module to switch'):
            ko_file_path = SecureBootConsts.UNSIGNED_KERNEL_MODULE_PATH
            scp_file(
                player=engines.dut,
                src_path=ko_file_path,
                dst_path=f'{SecureBootConsts.TMP_FOLDER}',
                download_from_remote=False
            )

    return f'{SecureBootConsts.TMP_FOLDER}/{ko_file_path.split("/")[-1]}', ko_file_path


@pytest.mark.checklist
@pytest.mark.secure_boot
@pytest.mark.parametrize('signing_state', SigningState.ALL_STATES)
def test_kernel_module_loading(signing_state: str, engines):
    '''
    @summary: in this test case we want to validate unsuccessful load
    of unsigned kernel module
    '''
    assert signing_state in SigningState.ALL_STATES, f'signing state {signing_state} must be in {SigningState.ALL_STATES}'

    km = KernelModulesTool(engines.dut)

    new_kernel_module_path, orig_kernel_module_path = get_kernel_module_path(signing_state, engines, km)
    kernel_module_ko_filename = new_kernel_module_path.split('/')[-1]
    kernel_module_name = kernel_module_ko_filename.split('.')[0].replace('-', '_')

    with allure.step(f'Remove kernel module: {kernel_module_name}'):
        km.remove_kernel_module(kernel_module_name)

    try:
        with allure.step(f'Load new {signing_state} kernel module: {kernel_module_name}'):
            expected = signing_state == SigningState.SIGNED
            km.load_kernel_module(f'{SecureBootConsts.TMP_FOLDER}/{kernel_module_ko_filename}').verify_result(should_succeed=expected)

        with allure.step(f'Verify kernel module {kernel_module_name} was {"" if expected else "not "}loaded'):
            time.sleep(3)
            actual = km.is_kernel_module_loaded(kernel_module_name)
            assert actual == expected, f'Kernel module {kernel_module_name} was loaded (actual): {actual}\nExpected: {expected}'
    finally:
        with allure.step(f'Remove kernel module: {kernel_module_name}'):
            km.remove_kernel_module(kernel_module_name)

        if signing_state == SigningState.SIGNED:
            with allure.step(f'Load orig kernel module: {kernel_module_name}'):
                km.load_kernel_module(orig_kernel_module_path)
