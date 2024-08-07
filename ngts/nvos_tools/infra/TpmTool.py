import logging
from typing import Dict, Any, List, Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.security.tpm_attestation import constants as tpmconst
from ngts.tools.test_utils import allure_utils as allure

PATH_NO_EXIST_ERR = 'No such file or directory'
CMD_NOT_FOUND_ERR = 'command not found'


class TpmTool:
    def __init__(self, engine: LinuxSshEngine):
        self.engine = engine

    """ API methods """

    def get_files_in_tpm_dir(self) -> List[str]:
        with allure.step('get list of files in tpm dir'):
            return self.engine.run_cmd(f'ls {tpmconst.TPM_DIR}').split()

    def is_tpm_attestation_ready(self) -> bool:
        """
        check if setup is prepared for tpm attestation
        """
        return self._is_sys_tpm_dir_exists() and self._is_dev_tpm_dir_exists() and \
            self._is_tpm_tools_installed() and self._is_tpm_capabilities_ok()

    def install_tpm_tools(self) -> bool:
        with allure.step('install tpm tools'):
            self.engine.run_cmd('sudo apt update -y && sudo apt install tpm2-tools -y')
            return self._is_tpm_tools_installed()

    def is_check_quote_ok(self, nonce: str) -> bool:
        with allure.step('convert AIK from crt to pem'):
            tmp_aik_path = f'/tmp/{tpmconst.AIK_PEM_FILENAME}'
            self.engine.run_cmd(f'sudo rm -f {tmp_aik_path}')
            out = self.engine.run_cmd(f'sudo openssl x509 -in {tpmconst.AIK_FILE_PATH} -pubkey -noout > {tmp_aik_path}')
            assert not out, f'unexpected output after converting AIK crt to pem:\n{out}'
        with allure.step('run check-quote'):
            out = self.engine.run_cmd(f'sudo tpm2_checkquote -u {tmp_aik_path} '
                                      f'-m {tpmconst.TPM_DIR}/pcr_quote '
                                      f'-s {tpmconst.TPM_DIR}/pcr_quote.sig '
                                      f'-q "{nonce}"')
        with allure.step('remove tmp pem file'):
            self.engine.run_cmd(f'sudo rm -f {tmp_aik_path}')
        return 'ERROR' not in out

    def remove_quote_files_from_tpm_dir(self):
        with allure.step('remove quote files from tpm dir'):
            self.engine.run_cmd(f'sudo rm -f {tpmconst.TPM_DIR}/pcr_quote')
            self.engine.run_cmd(f'sudo rm -f {tpmconst.TPM_DIR}/pcr_quote.sig')
            self.engine.run_cmd(f'sudo rm -f {tpmconst.QUOTE_FILE_PATH}')

    def get_quote_file_content(self):
        return self.engine.run_cmd(f'sudo cat {tpmconst.QUOTE_FILE_PATH}')

    def is_tpm_lockout_counter_cleared(self) -> Tuple[bool, str]:
        expected_counter_hex = '0x0'
        with allure.step(f'check if tpm lockout counter is cleared: {expected_counter_hex}'):
            actual_counter_hex = \
                self.engine.run_cmd('sudo tpm2 getcap properties-variable | grep TPM2_PT_LOCKOUT_COUNTER:').split(':')[
                    1].strip()
            return actual_counter_hex == expected_counter_hex, actual_counter_hex

    def clear_tpm_lockout_counter(self):
        with allure.step('clear tpm lockout counter'):
            self.engine.run_cmd('sudo tpm2_dictionarylockout --setup-parameters --clear-lockout')

    def get_tpm_cipher(self):
        with allure.step('get tpm cipher'):
            salt = "1300NVOS-BMC-USER-Const"
            file_name = "kdfconst.bin"
            self.engine.run_cmd(f'echo {salt} | xxd -r -p > {file_name}')
            return \
                (self.engine.run_cmd(
                    f'sudo tpm2_createprimary -C o -G aes256cfb -u {file_name} | grep symcipher:')).split(
                    ':')[1].strip()

    def get_bmc_admin_password_from_tpm(self):
        with allure.step('get bmc admin password from tpm'):
            return self.get_tpm_cipher()[:11] + 'A!'

    """ Helper methods """

    def _is_sys_tpm_dir_exists(self) -> bool:
        with allure.step('check if system tpm directory exists'):
            out = self.engine.run_cmd('sudo ls /sys/class/tpm/tpm0')
            return out != '' and PATH_NO_EXIST_ERR not in out

    def _is_dev_tpm_dir_exists(self) -> bool:
        with allure.step('check if tpm is enabled'):
            out = self.engine.run_cmd('ls /dev/ | grep tpm')
            return out != '' and PATH_NO_EXIST_ERR not in out

    def _is_tpm_tools_installed(self) -> bool:
        with allure.step('check if tpm tools package is installed'):
            return self.engine.run_cmd('dpkg -l | grep tpm2-tools') != ''

    def _is_tpm_capabilities_ok(self) -> bool:
        with allure.step('check if tpm capabilities are ok'):
            with allure.step('run tpm getcap'):
                out = self.engine.run_cmd('sudo tpm2_getcap properties-variable')
                logging.info(f'getcap output:\n{out}')
                if CMD_NOT_FOUND_ERR in out:
                    return False
            with allure.step('parse output to dict'):
                parsed_out = parse_tpm_output(out)
            with allure.step('check if "TPM2_PT_STARTUP_CLEAR" in output'):
                if 'TPM2_PT_STARTUP_CLEAR' not in parsed_out:
                    return False
            with allure.step('check target attributes'):
                target_attributes = parsed_out['TPM2_PT_STARTUP_CLEAR']
                return 'phEnable' in target_attributes and target_attributes['phEnable'] == '1' \
                    and 'shEnable' in target_attributes and target_attributes['shEnable'] == '1' \
                    and 'ehEnable' in target_attributes and target_attributes['ehEnable'] == '1'

    def _is_tpm_provisioned(self) -> bool:
        return True  # TODO: complete


def parse_tpm_output(tpm_output: str) -> Dict[str, Any]:
    output_lines = tpm_output.split('\n')

    parsed_dict = {}
    current_section = None

    for raw_line in output_lines:
        line = raw_line.strip()
        if line.strip() == '':
            continue
        if line.endswith(':'):
            current_section = line.strip()[:-1]
            parsed_dict[current_section] = {}
        elif current_section is not None:
            key, value = line.strip().split(':')
            parsed_dict[current_section][key.strip()] = value.strip()

    return parsed_dict
