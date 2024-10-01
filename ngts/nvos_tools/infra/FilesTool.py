import json
import logging
import re
from datetime import datetime

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.tools.test_utils import allure_utils as allure

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
