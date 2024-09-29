import logging

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.TpmTool import TpmTool

logger = logging.getLogger()


class BmcTool():
    BASE_URL = "https://10.0.1.1/redfish/v1/"
    USER_NAME = "admin"

    @staticmethod
    def _get_bmc_password(engine: LinuxSshEngine):
        return TpmTool(engine).get_bmc_admin_password_from_tpm()

    @staticmethod
    def reset(engine: LinuxSshEngine):
        password = BmcTool._get_bmc_password(engine)
        cmd = (f"""curl -k -u {BmcTool.USER_NAME}:{password} -H "Content-Type: application/json" -X POST """ +
               """-d '{"ResetType": "GracefulRestart"}' """ +
               f"""{BmcTool.BASE_URL}Managers/BMC_0/Actions/Manager.Reset""")
        response = engine.run_cmd(cmd)
        if "The request completed successfully" not in response:
            raise Exception("Shutdown command failed with the following response:\n" + response)
