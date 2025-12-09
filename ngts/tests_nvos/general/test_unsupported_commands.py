import logging

from ngts.nvos_tools.infra.Tools import Tools
from ngts.tools.test_utils import allure_utils as allure
from ngts.ngts_types import EnginesT, DevicesT

logger = logging.getLogger()


def test_unsupported_commands(engines: EnginesT, devices: DevicesT):
    """
    Make sure there are no unsupported commands available on system
    (run unsupported commands and expect an error)
    """

    with allure.step("Start running unsupported commands on system"):
        engine = engines.dut
        for cmd in devices.dut.unsupported_commands_list:
            if '{port}' in cmd:
                tested_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
                tested_port_name = tested_port.name
                cmd = cmd.replace('{port}', tested_port_name)
            with allure.independent_step(f"Current command: '{cmd}'"):
                output = engine.run_cmd(cmd)
                assert "Error" in output, (f"Didn't receive an error after running command. "
                                           f"'{cmd}' command should not be supported on system.")
