import logging
import re
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


class TempFileOnEngine:
    """
    File is created on engine and automatically assigned a name. File is deleted at the end of usage. Usage example:
    with TempFileOnEngine(engines.dut) as f:
        logger.info(f.path)
        f.write('xyz')
    """

    def __init__(self, engine: ProxySshEngine):
        self.engine = engine
        self.path = datetime.now().strftime("/tmp/%Y%m%d%H%M%S.test")

    def __enter__(self):
        with allure.step(f"Creating temp file: {self.path}"):
            self.engine.run_cmd(f"touch {self.path}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.engine.run_cmd(f"rm -f {self.path}")

    def write(self, text: str, newline=True):
        self.engine.run_cmd(f"echo {'' if newline else '-n '}'{text}' >> {self.path}")
