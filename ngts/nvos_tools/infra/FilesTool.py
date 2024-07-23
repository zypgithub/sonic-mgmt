import logging
import re

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

    def get_content(self) -> str:
        return self.engine.run_cmd("sudo cat " + self.file_path)

    def revert_to_original(self):
        self.replace_whole_content(self.original_content)

    def replace_whole_content(self, content: str):
        """Writes `content` to file, overwriting any existing content."""
        self.engine.run_cmd(f"sudo cat > {self.file_path} << EOF\n{content}\nEOF")

    def sed(self, pattern: str, new_text: str):
        self.engine.run_cmd(f"sudo sed -i 's/{pattern}/{new_text}/' {self.file_path}")
        self.get_content()  # print new content to log
