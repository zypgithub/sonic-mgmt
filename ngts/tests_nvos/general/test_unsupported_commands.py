import logging

from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def test_unsupported_commands(engines, devices):
    """
    Make sure there are no unsupported commands available on system
    (run unsupported commands and expect an error)
    """

    with allure.step("Start running unsupported commands on system"):
        engine = engines.dut
        for cmd in devices.dut.unsupported_commands_list:
            with allure.independent_step(f"Current command: '{cmd}'"):
                output = engine.run_cmd(cmd)
                assert "Error" in output, (f"Didn't receive an error after running command. "
                                           f"'{cmd}' command should not be supported on system.")
