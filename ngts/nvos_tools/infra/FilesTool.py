import json
import logging
import re
import os
from datetime import datetime

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class FilesTool:

    @staticmethod
    def get_subfiles_list(engine, folder_path, subfiles_pattern=""):
        """
        :param subfiles_pattern:
        :param engine:
        :param folder_path: a full path for a specific folder
        :return: list of all subfiles in the folder
        """
        output = engine.run_cmd('ls {}/*'.format(folder_path))
        reg = r'\b(?:{})-\d+\+[^\s]+\b|\b(?:{})\+\d*[^\s]+\b'.format(subfiles_pattern, subfiles_pattern)
        return re.findall(reg, output)

    @staticmethod
    def file_exists(engine, file_path):
        output = engine.run_cmd(f'ls {file_path}')
        return "No such file or directory" not in output

    @staticmethod
    def validate_expected_files(engine, folder_path, expected_files, should_succeed=True):
        """
        :param engine:
        :param folder_path: folder full path
        :param expected_files: list of expected files or folders
        :param should_succeed:
        :return:
        """
        err_msg = ""
        with allure.step(f"validate all {expected_files} in {folder_path}"):
            output = engine.run_cmd(f'ls -l {folder_path}')
            output.splitlines()
            for file in expected_files:
                if file not in output:
                    err_msg += f"{file} file does not exist in the path {folder_path}"

        assert bool(err_msg) != should_succeed, err_msg if err_msg else ""
        return True

    @staticmethod
    def get_file_size_in_bytes(engine, file_path):
        output = engine.run_cmd(f'stat --format="%s" {file_path}')
        return int(output) if output.isdigit() else -1

    @staticmethod
    def create_file_with_content(engine, file_name, file_type, content):
        """
        Create a file with content and upload to the DUT machine.

        Args:
            engine: The test engine
            file_name: Name of the file without extension
            file_type: File extension (e.g., 'json', 'yaml')
            content: Content to write to the file
        """

        # Create a temporary file locally
        local_file = f'/tmp/{file_name}.{file_type}'
        with open(local_file, 'w') as f:
            f.write(content)

        # Copy the file to the DUT machine
        dest_file = f'/tmp/{file_name}.{file_type}'
        engine.copy_file(source_file=local_file, dest_file=dest_file, file_system='/tmp', overwrite_file=True)

        # Clean up local file
        os.remove(local_file)

        return dest_file


class EngineFile:
    """
    Represents a file on the switch and provides methods to edit it. The file has to be already existing.
    The revert_to_original() method is useful for cleanup code.
    """

    def __init__(self, engine: ProxySshEngine, file_path: str):
        self.engine = engine
        self.file_path = file_path
        ls_output = engine.run_cmd("ls " + file_path)
        if ls_output.strip() != file_path.strip():
            raise ValueError(ls_output)

        with allure.step(f"Storing original content of file for later recovery: {file_path}"):
            self.original_content = self.get_content()
            logger.info(self.original_content)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.revert_to_original()

    def get_content(self) -> str:
        return self.engine.run_cmd("sudo cat " + self.file_path, print_output=False)

    def revert_to_original(self):
        self.replace_whole_content(self.original_content)
        new_content = self.get_content()
        if new_content != self.original_content:
            raise Exception(f"Failed to restore original content of {self.file_path}")

    def replace_whole_content(self, content: str):
        """Writes `content` to file, overwriting any existing content."""
        self.engine.run_cmd_set(["sudo su", f"cat > {self.file_path} << EOF\n{content}\nEOF", "exit"])

    def sed(self, pattern: str, new_text: str):
        self.engine.run_cmd(f"sudo sed -i 's/{pattern}/{new_text}/' {self.file_path}")
        logger.info(f"new content of {self.file_path}:\n" + self.get_content())

    def json_read(self):
        return json.loads(self.get_content())

    def json_overwrite(self, data):
        self.replace_whole_content(json.dumps(data, indent=4))


class TempFileOnEngine:
    """
    File is created on engine and automatically assigned a name. File is deleted at the end of usage. Usage example:
    with TempFileOnEngine(engines.dut) as f:
        logger.info(f.path)
        f.write('xyz')
    """

    def __init__(self, engine: ProxySshEngine, extension='test'):
        self.engine = engine
        self.path = datetime.now().strftime("/tmp/%Y%m%d%H%M%S.") + extension

    def __enter__(self):
        with allure.step(f"Creating temp file: {self.path}"):
            self.engine.run_cmd(f"touch {self.path}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.engine.run_cmd(f"rm -f {self.path}")

    def write(self, text: str, newline=True, backslash_escapes=False):
        echo_args = '' if newline else ' -n'
        echo_args += ' -e' if backslash_escapes else ''
        self.engine.run_cmd(f"echo{echo_args} '{text}' >> {self.path}")
