import logging
import re
import crypt
import pexpect

from io import StringIO
from infra.tools.connection_tools.utils import generate_strong_password
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.User import User
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tests_nvos.general.security.ssh_ciphers.constants import SshCiphersConsts
from ngts.tests_nvos.general.security.ssh_ciphers.SshKeyManager import SshKeyManager


def setup_api_type(dut: ProxySshEngine, api_type: ApiType):
    """
    @summary: setup api type
    @param dut: dut
    @param api_type: api type
    @return: original api type
    @raises: Exception if failed to setup api type
    """
    with allure.step(f'Setup api type: {api_type}'):
        original_api = TestToolkit.tested_api
        TestToolkit.tested_api = api_type
        if api_type == ApiType.NVUE:
            with allure.step(f'Detach config'):
                NvueGeneralCli.detach_config(dut)
        return original_api


def clean_ssh_server_configuration(dut: ProxySshEngine, property_name: str = None):
    """
    @summary: clean ssh server configuration for a given property name, if property name is not provided, clean all properties
    @param dut: dut
    @param property_name: property name
    @raises: Exception if failed to clean ssh server configuration
    """
    with allure.step(f'Clean ssh server configuration'):
        if property_name:
            System().ssh_server.unset(op_param=property_name, apply=True, ask_for_confirmation='-y').verify_result()
            verify_values_for_property(dut, property_name=property_name, expected_value=SshCiphersConsts.DEFAULT_VALUES[property_name])
        else:
            keys_to_unset = list(SshCiphersConsts.DEFAULT_VALUES.keys())
            for i, key in enumerate(keys_to_unset):
                System().ssh_server.unset(op_param=key, apply=i == len(keys_to_unset) - 1, ask_for_confirmation='-y').verify_result()
            verify_default_values(dut)


def cleanup_after_test(dut: ProxySshEngine, original_api: ApiType = None, property_name: str = None):
    """
    @summary: cleanup after test
        1. clean ssh server configuration for a given property name, if property name is not provided, clean all properties.
        2. restore api type if original api type is provided
    @param dut: dut
    @param original_api: original api type
    @param property_name: property name
    @raises: Exception if failed to cleanup after test
    """
    try:
        clean_ssh_server_configuration(dut, property_name=property_name)
    finally:
        if original_api:
            with allure.step(f'restore api to original: {original_api}'):
                TestToolkit.tested_api = original_api


def extract_key_info_single_regex(pubkey: str):
    """
    @summary: Single regex to extract key type, bits, and certificate status from SSH public key type string
    @param pubkey: SSH public key type
    @return: tuple of (key_type, num_bits, is_certificate) or (None, None, None) if no match
    @raises: Exception if failed to extract key type, bits, and certificate status from SSH public key type string
    """
    # Single comprehensive regex pattern that captures certificate status
    pattern = r'(?:(ecdsa)-sha2-nistp(\d+)(-cert)?|(rsa)-sha2-(\d+)(-cert)?|(ssh-ed25519)(-cert)?|(ssh-rsa)(-cert)?)'

    match = re.search(pattern, pubkey)
    if match:
        if match.group(1) and match.group(2):  # ECDSA: ecdsa-sha2-nistp256/384/521
            return match.group(1), int(match.group(2)), match.group(3)
        elif match.group(4):  # RSA: rsa-sha2-512, rsa-sha2-256
            return match.group(4), 4096, match.group(6)  # int(match.group(5))*8
        elif match.group(7):  # Ed25519: ssh-ed25519
            return match.group(7), 256, match.group(8)
        elif match.group(9):  # RSA: ssh-rsa (legacy format)
            return match.group(9), 4096, match.group(10)
    return (None, None, None)


def verify_username_password_and_ip_are_valid(server_engine: ProxySshEngine, username: str = None, password: str = None, check_password: bool = True):
    """
    @summary: Verify username, password and ip are valid
        if username and/or password are not provided, use server_engine username and/or password
    @param server_engine: proxy ssh engine
    @param username: username
    @param password: password
    @return: Tuple of (username, password)
    @raises: Exception if invalid parameters
    """
    with allure.step('Verify username, password and ip are valid'):
        if not username:
            assert server_engine.username, f"Invalid server_engine parameters: username is not provided"
            username = str(server_engine.username)
        if check_password and not password:
            assert hasattr(server_engine, 'password') and server_engine.password, f"Invalid server_engine parameters: password is not provided"
            password = str(server_engine.password)
        assert server_engine.ip, f"Invalid server_engine parameters: username='{username}', ip='{server_engine.ip}'"
        return username, password


def check_expected_and_actual(expected_value, actual_value):
    """
    @summary: Get expected and actual message
    @param expected_value: expected value
    @param actual_value: actual value
    @raises: Exception if failed to get expected and actual message
    """
    # Handle the case where expected_value is a string but actual_value is a list
    if isinstance(expected_value, str):
        if isinstance(actual_value, list):
            assert expected_value == actual_value[0], f"Expected: {expected_value}\nGot: {actual_value[0]}"
        else:
            assert expected_value == actual_value, f"Expected: {expected_value}\nGot: {actual_value}"
    else:
        assert set(expected_value) == set(actual_value), (
            f"Expected: {expected_value}\n"
            f"Got: {actual_value}\n"
            f"Missing: {set(expected_value) - set(actual_value)}\n"
            f"Shouldn't contain: {set(actual_value) - set(expected_value)}"
        )


def create_ssh_command_and_spawn_process(username: str, ip: str, timeout: int, ssh_options: str = ''):
    """
    Create SSH command and spawn pexpect process with output buffer.

    @param username: SSH username
    @param ip: SSH server IP address
    @param timeout: SSH timeout in seconds
    @param ssh_options: Additional SSH options
    @return: Tuple of (pexpect child process, output buffer)
    @raises: Exception if command creation or process spawning fails
    """
    with allure.step(f'Create SSH command and spawn pexpect process: {username}@{ip}'):
        try:
            # Add default SSH options to avoid host key checking (like other SSH functions in this file)
            if SshCiphersConsts.STRICT_HOST_KEY_CHECKING not in ssh_options:
                ssh_options = f'{SshCiphersConsts.STRICT_HOST_KEY_CHECKING} {ssh_options}'
            cmd = f'timeout {timeout} ssh -v {ssh_options} ' \
                f'{username}@{ip} "echo SSH_LOGIN_SUCCESS"'

            logging.info(f"SSH command: {cmd}")

            child = pexpect.spawn(cmd, encoding='utf-8')
            # Create a buffer to capture all output
            output_buffer = StringIO()
            child.logfile_read = output_buffer

            return child, output_buffer
        except pexpect.ExceptionPexpect as e:
            raise Exception(f"Failed to spawn process: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to create SSH command: {str(e)}")


def get_ssh_verbose_output(server_engine: ProxySshEngine, timeout: int = 10, ssh_options: str = '', send_password: bool = True, username: str = None, password: str = None):
    """
    @summary: Get SSH verbose output with proxy ssh engine
    @param server_engine: proxy ssh engine
    @param timeout: timeout
    @param ssh_options: ssh options
    @return: Tuple of (SSH verbose output, success boolean)
    @raises: Exception if SSH connection fails
    """
    username, password = verify_username_password_and_ip_are_valid(server_engine, username, password, check_password=send_password)
    child, output_buffer = create_ssh_command_and_spawn_process(username, str(server_engine.ip), timeout, ssh_options)

    try:
        with allure.step('Wait for password prompt or connection to complete'):
            conn_result = False
            # Wait for password prompt or connection to complete
            patterns = [r"[Pp]assword:\s*", 'SSH_LOGIN_SUCCESS', r"[Pp]ermission denied\s*", pexpect.EOF, pexpect.TIMEOUT]
            index = child.expect(patterns, timeout=timeout)
            logging.info(f"SSH output pattern: {patterns[index]}, index: {index}")
            if index == 0:
                if send_password and password:
                    child.sendline(password)
                    index = child.expect(patterns, timeout=timeout)
                    logging.info(f"SSH output pattern: {patterns[index]}, index: {index}")
            if index == 1:
                conn_result = True

    finally:
        with allure.step('Collect SSH output and close process'):
            output = output_buffer.getvalue()
            try:
                child.close()
            except Exception as e:
                logging.warning(f"failed to close child process: {str(e)}")
            return str(output) if output else '', conn_result


def set_ssh_server_param(op_param_name: str, value, apply: bool = True, should_succeed: bool = True):
    """
    @summary: Helper method to set SSH server parameter and verify result based on API type.

    @param ssh_server: SSH server object from System().ssh_server
    @param property_name: SSH parameter name (e.g., 'ciphers', 'macs')
    @param value: Value to set (string or list)
    @param apply: Whether to apply the operation
    @param should_succeed: Whether the operation should succeed
    """
    with allure.step('Set SSH server parameter and verify result based on API type'):
        if isinstance(value, str):
            op_param_value = [value] if TestToolkit.tested_api == ApiType.OPENAPI else value
        elif isinstance(value, list):
            op_param_value = " ".join(value) if TestToolkit.tested_api == ApiType.NVUE else value
        else:
            raise Exception(f"Invalid value type: {type(value)} for op_param_name: {op_param_name}, must be str or list")

        System().ssh_server.set(op_param_name=op_param_name,
                                op_param_value=op_param_value,
                                apply=apply,
                                ask_for_confirmation='-y'
                                ).verify_result(should_succeed=should_succeed)


def boundary_check(dut: ProxySshEngine, api_type: ApiType, property_name: str):
    """
    @summary: Verify boundaries for a given property
    @param dut: dut
    @param api_type: API type
    @param property_name: property name
    @raises: Exception if failed to verify boundaries for a given property
    """
    original_api = setup_api_type(dut, api_type)
    ssh_server = System().ssh_server
    invalid_value = None
    try:
        for value in SshCiphersConsts.DEFAULT_VALUES[property_name]:
            invalid_value = [value, value]
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)
            invalid_value = value.replace("-", "--")
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)
            invalid_value = value.replace("-", "")
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)
            invalid_value = value + 't'
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)
            invalid_value = value[:3] + 't' + value[3:]
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)

            if 'sha2-' in value:
                invalid_value = value.replace('sha2-', 'sha1-')
                set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)

            if '@' in value:
                invalid_value = value.replace('@', '')
                set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)

        for invalid_value in list(set(SshCiphersConsts.POSSIBLE_VALUES[property_name]) - set(SshCiphersConsts.DEFAULT_VALUES[property_name])):
            set_ssh_server_param(op_param_name=property_name, value=invalid_value, apply=False, should_succeed=False)

    except Exception as e:
        ssh_server.unset(op_param=property_name, apply=True, ask_for_confirmation='-y')
        raise Exception(f"for invalid value {invalid_value}: {str(e)}")
    finally:
        TestToolkit.tested_api = original_api


def verify_values_for_property(dut: ProxySshEngine, property_name: str, expected_value: list = None):
    """
    @summary: Verify default values for a given property
    @param dut: dut
    @param property_name: property name
    @param expected_value: expected value
    @raises: Exception if failed to verify default values for a given property
    """
    if not expected_value:
        expected_value = SshCiphersConsts.DEFAULT_VALUES[property_name]
    with allure.step(f'Verify {property_name} in nv show system ssh-server command'):
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(System().ssh_server.show()).get_returned_value()
        check_expected_and_actual(expected_value=expected_value, actual_value=ssh_output[property_name])

    grep_cmd = f'grep -i -E "^{property_name.replace("-", "")}"'
    for cmd in ['cat /etc/ssh/sshd_config', 'sshd -T']:
        with allure.step(f'Verify {property_name} in {cmd}'):
            actual = dut.run_cmd(f'sudo {cmd} | {grep_cmd}').strip().split(' ', 1)
            assert len(actual) == 2, f'Expected: {property_name} <{property_name}> to be present in {cmd} output, got: {actual}'
            assert actual[0].lower() == property_name.replace("-", ""), f'Expected: {property_name}, got: {actual[0]}'
            check_expected_and_actual(expected_value=expected_value, actual_value=actual[1].replace('\n', '').split(','))


def verify_default_values(dut: ProxySshEngine):
    """
    @summary: Verify default values for ssh
    @param dut: dut object
    """
    try:
        verify_default_values_in_nv_show_system_ssh_server()
    finally:
        verify_default_values_in_configuration_file(dut)


def verify_default_values_in_nv_show_system_ssh_server():
    """
    @summary: Verify default values for ssh in nv show system ssh-server command
    """
    with allure.step('verify default values in nv show system ssh-server command'):
        ssh_server = System().ssh_server
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(ssh_server.show()).get_returned_value()
        with allure.step(f'Verify {SshCiphersConsts.STRICT} field is not present'):
            assert SshCiphersConsts.STRICT not in ssh_output.keys(), f'Expected: strict field should not be present'
        keys_to_check = [SshCiphersConsts.CIPHERS,
                         SshCiphersConsts.MACS,
                         SshCiphersConsts.KEX_ALGOS,
                         SshCiphersConsts.HOST_KEY_ALGOS,
                         SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS]
        for key in keys_to_check:
            with allure.step(f'Verify {key} are the default values'):
                check_expected_and_actual(expected_value=SshCiphersConsts.DEFAULT_VALUES[key], actual_value=ssh_output[key])


def verify_default_values_in_configuration_file(dut: ProxySshEngine):
    """
    @summary: Verify default values in configuration file
    @param dut: dut object
    """
    # Build grep pattern for SSH configuration verification
    expected_values_map = dict()
    expected_values_map[SshCiphersConsts.X11FORWARDING] = 'no'
    expected_values_map[SshCiphersConsts.ALLOWTCPFORWARDING] = 'no'
    expected_values_map[SshCiphersConsts.COMPRESSION] = 'no'
    expected_values_map[SshCiphersConsts.CIPHERS] = SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.CIPHERS]
    expected_values_map[SshCiphersConsts.MACS] = SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.MACS]
    expected_values_map[SshCiphersConsts.KEX_ALGOS.replace("-", "")] = SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.KEX_ALGOS]
    expected_values_map[SshCiphersConsts.HOST_KEY_ALGOS.replace("-", "")] = SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.HOST_KEY_ALGOS]
    expected_values_map[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS.replace("-", "")] = SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS]

    grep_pattern = f"^({'|'.join(expected_values_map.keys())})"
    grep_cmd = f'grep -i -E "{grep_pattern}"'
    for cmd in ['cat /etc/ssh/sshd_config', 'sshd -T']:
        keys_to_check = list(expected_values_map.keys())
        with allure.step(f'Verify values in {cmd}'):
            lines = dut.run_cmd(f'sudo {cmd} | {grep_cmd}').splitlines()
            while lines:
                line = lines.pop().strip().split()
                key = line[0].lower()
                if key in keys_to_check:
                    check_expected_and_actual(expected_value=expected_values_map.get(key), actual_value=line[1].split(','))
                    keys_to_check.remove(key)
                else:
                    lines[-1] = lines[-1] + line[0]
            assert not keys_to_check, f'{keys_to_check} are missing'


def extract_negotiated_algorithms(ssh_output: str, property_name: str = None):
    """
    @summary: Extract negotiated algorithms from SSH verbose output using constants patterns
    @param ssh_output: SSH verbose output (combined stdout + stderr)
    @param property_name: property name

    @return: Dict with negotiated values
    """
    if not property_name:
        negotiated = {}
        for property_name, pattern in SshCiphersConsts.PATTERNS.items():
            match = re.search(pattern, ssh_output)
            if match:
                negotiated[property_name] = match.group(1).strip()
        return negotiated
    elif property_name == SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS:
        match = re.search(SshCiphersConsts.PUBLIC_KEY_AUTHENTICATION_PATTERN, ssh_output)
        assert match, f'Pattern "{SshCiphersConsts.PUBLIC_KEY_AUTHENTICATION_PATTERN}" not found in "{ssh_output}"'
        match = re.search(SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS_PATTERN, ssh_output)
        assert match, f'Pattern {SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS_PATTERN} not found in "{ssh_output}"'
        return match.group(1).strip(), match.group(2).strip()
    else:
        match = re.search(SshCiphersConsts.PATTERNS[property_name], ssh_output)
        assert match, f'Pattern {SshCiphersConsts.PATTERNS[property_name]} not found in "{ssh_output}"'
        return match.group(1).strip()


def build_ssh_options(property_name: str, options: list = None) -> str:
    """
    @summary: Build SSH command-line options for testing a specific property
    @param property_name: The SSH property to build options for (e.g., 'ciphers', 'macs')
    @return: SSH options string with appropriate flags
    """
    option = SshCiphersConsts.STRICT_HOST_KEY_CHECKING
    if options:
        option += ' ' + (SshCiphersConsts.FLAGS[property_name] + ','.join(options))
    if property_name == SshCiphersConsts.MACS:  # For MACs testing, we need to specify non-GCM ciphers first
        option += ' ' + SshCiphersConsts.FLAGS[SshCiphersConsts.CIPHERS] + ','.join(cipher for cipher in SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.CIPHERS] if 'gcm' not in cipher)
    return option


def good_flow(dut: ProxySshEngine, property_name: str, options_to_check: list) -> str:
    """
    @summary: Verify SSH connection succeeds and negotiates expected algorithms
    @param dut: dut object
    @param property_name: SSH property being tested
    @param options_to_check: List of options to check (should cause failure)
    @return: SSH output for further processing if needed
    """
    with allure.step(f'Good flow: Verify ssh with valid {property_name}'):
        ssh_options = build_ssh_options(property_name, options_to_check)
        (ssh_output, success) = get_ssh_verbose_output(server_engine=dut, ssh_options=ssh_options)
        assert success, f'SSH connection failed. SSH output: {ssh_output}'

        with allure.step(f'Verify ssh result'):
            negotiated = extract_negotiated_algorithms(ssh_output, property_name)
            assert negotiated in options_to_check, f'Negotiated value "{negotiated}" not in expected options {options_to_check}. SSH output: {ssh_output}'

        assert not re.search(SshCiphersConsts.ERROR_PATTERNS[property_name], ssh_output), f'Pattern "{SshCiphersConsts.ERROR_PATTERNS[property_name]}" found in "{ssh_output}"'
        return ssh_output


def bad_flow(dut: ProxySshEngine, property_name: str, options_to_check: list) -> str:
    """
    @summary: Verify SSH connection fails with invalid options and shows expected error patterns
    @param dut: dut object
    @param property_name: SSH property being tested
    @param options_to_check: List of options to check (should cause failure)
    @return: SSH output for further processing if needed
    """
    with allure.step(f'Bad flow: Verify ssh with invalid {property_name}'):
        ssh_options = build_ssh_options(property_name, options_to_check)
        (ssh_output, success) = get_ssh_verbose_output(server_engine=dut, ssh_options=ssh_options)

        with allure.step(f'Verify ssh result'):
            assert not success, f'SSH connection should not succeed. SSH output: {ssh_output}'
            assert re.search(SshCiphersConsts.ERROR_PATTERNS[property_name], ssh_output), f'Pattern "{SshCiphersConsts.ERROR_PATTERNS[property_name]}" found in "{ssh_output}"'

        return ssh_output


def general_test_flow(dut: ProxySshEngine, api_type, property_name, values_to_check: list = None):
    """
    @summary: verify the change of Ciphers in sshd_config

        Steps:
        for each value in possible values:
            1. configure system ssh-server <property> with the value
            2. verify the property is set in sshd_config
            2. good flow: verify login via ssh with the value is successful
            3. bad flow: verify login via ssh with invalid value is failed
        cleanup:
        1. unset system ssh-server <property>
        2. verify default values of <property> are set
    """
    while values_to_check:
        value = values_to_check.pop()
        try:
            with allure.step(f'{property_name} = {value}'):
                with allure.step(f'configuring {property_name}: {value}'):
                    set_ssh_server_param(op_param_name=property_name, value=value, apply=True, should_succeed=True)
                with allure.step(f'Verify {value} configuration'):
                    verify_values_for_property(dut, property_name=property_name, expected_value=[value])
                try:
                    good_flow(dut, property_name, [value])
                finally:
                    bad_flow(dut, property_name, list(set(SshCiphersConsts.POSSIBLE_VALUES[property_name]) - {value}))

        except Exception as e:
            general_test_flow(dut, api_type, property_name, values_to_check)
            raise Exception(f'Failed to test {property_name}: {e}')


def pubkey_test_flow(dut: ProxySshEngine, keys_manager: SshKeyManager, username: str, values_to_check: list = None):
    while values_to_check:
        pubkey = values_to_check.pop()
        key_path = keys_manager.get_key_path(pubkey)
        try:
            with allure.step(f'{SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS} = {pubkey}'):
                with allure.step(f'Configure {SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS} to {pubkey}'):
                    excepted_value = [pubkey]
                    if pubkey not in SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.HOST_KEY_ALGOS]:
                        excepted_value += [key for key in SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.HOST_KEY_ALGOS] if not pubkey.startswith(key)]
                    set_ssh_server_param(op_param_name=SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS, value=excepted_value, apply=True, should_succeed=True)
                with allure.step(f'Verify {pubkey} configuration'):
                    verify_values_for_property(dut, property_name=SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS, expected_value=excepted_value)
                try:
                    with allure.step(f'Good flow: Verify ssh with valid public key: {pubkey}'):
                        op_options = SshCiphersConsts.ADDITIONAL_FLAGS[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS] + key_path
                        if '-cert' in pubkey:
                            op_options += " " + build_ssh_options(property_name=SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS, options=excepted_value)
                        elif pubkey in SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.HOST_KEY_ALGOS]:
                            op_options += " " + build_ssh_options(property_name=SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS, options=[pubkey])

                        (ssh_output, success) = get_ssh_verbose_output(dut, ssh_options=op_options, send_password=False, username=username if 'cert' in pubkey else None)
                        assert success, f'SSH connection failed. SSH output: {ssh_output}'
                        accepted_key_path, accepted_key_type = extract_negotiated_algorithms(ssh_output, SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS)
                        assert accepted_key_path == key_path, f'Expected key path {key_path} but got {accepted_key_path}\n {ssh_output}'
                        assert ('cert' in pubkey) == ('CERT' in accepted_key_type), f'Expected key type {accepted_key_type} but got {accepted_key_path}\n {ssh_output}'
                        match = re.search(r'Authenticated to .+ using "publickey"', ssh_output)
                        assert match, f'Pattern "Authenticated to .+ using "publickey"" not found in "{ssh_output}"'
                        assert not re.search(SshCiphersConsts.ERROR_PATTERNS[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS], ssh_output), f'Pattern "{SshCiphersConsts.ERROR_PATTERNS[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS]}" found in "{ssh_output}"'
                finally:
                    with allure.step(f'Bad flow: Verify can not ssh with different public keys != {pubkey}'):
                        for invalid_pubkey in keys_manager.keys.keys():
                            invalid_key_path = keys_manager.get_key_path(invalid_pubkey)
                            if invalid_pubkey in excepted_value or (invalid_key_path == key_path and invalid_pubkey.endswith('cert-v01@openssh.com') == pubkey.endswith('cert-v01@openssh.com')):
                                continue
                            op_options = SshCiphersConsts.ADDITIONAL_FLAGS[SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS] + invalid_key_path
                            if invalid_pubkey in SshCiphersConsts.DEFAULT_VALUES[SshCiphersConsts.HOST_KEY_ALGOS]:
                                op_options += " " + build_ssh_options(property_name=SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS, options=[invalid_pubkey])

                            with allure.step(f'Verify ssh with {invalid_pubkey} failed'):
                                (ssh_output, success) = get_ssh_verbose_output(dut, ssh_options=op_options, send_password=False, username=username if 'cert' in invalid_pubkey else None)
                                assert not success, f'SSH connection should not succeed. \n {ssh_output}'

        except Exception as e:
            pubkey_test_flow(dut, keys_manager, username, values_to_check)
            raise Exception(f'Failed to test {SshCiphersConsts.PUBKEY_ACCEPTED_ALGOS}: {e}')


def generate_user(username: str = None, password: str = None, apply: bool = False):
    """
    @summary: generate user with password, if username and/or password are not provided, generate username and/or password
    @param username: username
    @param password: password
    @param apply: apply
    @return: username, password
    """
    with allure.step(f'Generate user'):
        username = username if username else User.generate_username()
        password = password if password else generate_strong_password()
        user_obj = System().aaa.user.user_id[username]
        if TestToolkit.tested_api == ApiType.OPENAPI:
            logging.info(f"generating hashed password for {username} : {password}")
            salt = crypt.mksalt(crypt.METHOD_SHA512)
            hashed_password = crypt.crypt(password, salt)
            user_obj.set(op_param_name='hashed-password', op_param_value=hashed_password, apply=apply, ask_for_confirmation='-y').verify_result()
        else:
            user_obj.set(op_param_name='password', op_param_value=password, apply=apply, ask_for_confirmation='-y').verify_result()
        return username, password
