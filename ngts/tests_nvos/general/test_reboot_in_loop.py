import logging
import os
import random
import time
from ngts.nvos_tools.infra.SerialConsoleTool import SerialConsoleTool
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()

reboot_types = ["nvue_reboot", "power_cycle"]
server_ip = "10.237.22.60"


def test_reboot_in_loop(engines, topology_obj):
    server_ssh_conn = LinuxSshEngine(ip=server_ip, username=os.getenv("TEST_SERVER_USER"),
                                     password=os.getenv("TEST_SERVER_PASSWORD"))
    issue_reproduced = False
    iteration_num = 0

    while not issue_reproduced:
        logging.info(f" ----------- Iteration #{iteration_num} ----------- ")

        reboot_type = random.choice(reboot_types)
        logging.info(f" ### Reboot: {reboot_type} ###")

        if reboot_type == "power_cycle":
            run_power_cycle(engines, topology_obj, server_ssh_conn)
        else:
            run_reboot(engines)

        time.sleep(60)

        if was_issue_reproduced(engines):
            logging.info("The issue was reproduced")
            break

        logging.info("Issue wasn't reproduced - continue\n\n\n")
        iteration_num += 1


def was_issue_reproduced(engines):
    issue_reproduced = False

    if not valid_fw_output(engines):
        logging.warning("Reproduced - fw output")
        issue_reproduced = True
    if found_error_in_log(engines):
        logging.warning("Reproduced - error in log")
        issue_reproduced = True

    if issue_reproduced:
        System(None).techsupport.action_generate(engines.dut)

    return issue_reproduced


def run_reboot(engines):
    logging.info(f" ### Reboot ###")
    system = System(None)
    system.reboot.action_reboot(engines.dut)


def run_power_cycle(engines, topology_obj, server_ssh_conn):
    cmd = f"/auto/mswg/utils/bin/rreboot {engines.dut.ip}"

    logging.info(f" ### Power cycle - {cmd}")
    server_ssh_conn.run_cmd(cmd)

    engines.dut.disconnect()
    serial_engine = SerialConsoleTool.get_serial_console_session(topology_obj, 'dut')
    logging.info("Wait for nvos")
    wait_nos_to_become_functional(engines.dut, topology_obj, serial_engine)


def wait_nos_to_become_functional(engine, topology_obj, serial_engine):
    ping_till_alive(should_be_alive=False, destination_host=engine.ip)
    logging.info('Ping switch until back alive')
    ping_till_alive(should_be_alive=True, destination_host=engine.ip)
    logging.info('wait for System is ready in serial')
    DutUtilsTool.wait_for_system_ready_in_serial(topology_obj, serial_engine, 300)


def valid_fw_output(engines):
    logging.info("Checking fw output")
    output = OutputParsingTool.parse_show_output_to_dict(engines.dut.run_cmd("nv show platform firmware -o json")).verify_result()
    if output["EROT"]["actual-firmware"] == "N/A" or output["EROT-ASIC1"]["actual-firmware"] == "N/A" or \
       output["EROT-CPU"]["actual-firmware"] == "N/A":
        return False
    return True


def found_error_in_log(engines):
    logging.info("Checking log file")
    output = engines.dut.run_cmd("nv show system log | grep 'Version not found in Redfish response'")
    return output
