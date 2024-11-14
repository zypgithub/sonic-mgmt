import logging
import pytest

from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.HostMethods import HostMethods
from ngts.nvos_constants.constants_nvos import NvosConst

log = logging.getLogger()


def verify_CUMULUS_SENSOR_MIB(engines, port=None):
    with allure.step("Checking: CUMULUS-SENSOR-MIB::entitySensorObjects"):
        output = HostMethods.host_snmp_walk_v2(engines.dut,
                                               ip_address='localhost',
                                               mib='1.3.6.1.4.1.40310.6',
                                               param='', port=port)

    sensor_obj = ["entPhySensorIndex", "entPhySensorType",
                  "entPhySensorScale", "entPhySensorPrecision",
                  "entPhySensorValue", "entPhySensorOperStatus",
                  "entPhySensorUnitsDisplay", "entPhySensorValueTimeStamp",
                  "entPhySensorValueUpdateRate", "entPhySensorDescr",
                  "entPhySensorMin", "entPhySensorMax", "entPhySensorAlarm",
                  "entPhySensorAdminStatus"]
    with allure.step(f"Check snmpwalk has these OIDs : {sensor_obj} "):
        for sensorobj in sensor_obj:
            if (output.find(sensorobj) == -1):
                log.error(f"Failed: {sensorobj} missing")
                assert False, f"Failed: {sensorobj} missing"

    log.info("Success: CUMULUS-SENSOR-MIB::entitySensorObjects")


def verify_CUMULUS_STATUS_MIB(engines, port=None):
    with allure.step("Checking: CUMULUS-STATUS-MIB::cumulusSystemStatus"):
        output = HostMethods.host_snmp_walk_v2(engines.dut,
                                               ip_address='localhost',
                                               mib='1.3.6.1.4.1.40310.5',
                                               param='', port=port)

    status_obj = ["agentSwitchCpuProcessMemFree",
                  "agentSwitchCpuProcessMemAvailable",
                  "agentSwitchCpuProcessMemTotal",
                  "agentSwitchCpuProcessMemPrecision",
                  "agentSwitchCpuProcessRisingThreshold",
                  "agentSwitchCpuProcessRisingThresholdInterval",
                  "agentSwitchCpuProcessFallingThreshold",
                  "agentSwitchCpuProcessFallingThresholdInterval",
                  "agentSwitchCpuProcessFreeMemoryThreshold",
                  "agentSwitchCpuProcessTotalUtilization",
                  "agentSwitchCpuProcess5SecUtilization",
                  "agentSwitchCpuProcess1minUtilization",
                  "agentSwitchCpuProcess5minUtilization",
                  "agentSwitchCpuUtzPrecision", "agentSwitchCpuCores",
                  "agentSwitchCPUUtzErrorFlag", "agentSwitchCPUUtzErrorMsg",
                  "agentSwitchMemErrorFlag", "agentSwitchMemErrorMsg",
                  "agentSwitchCpuutilizationStatus", "agentSwitchMemStatus"]
    with allure.step(f"Check snmpwalk has these OIDs : {status_obj} "):
        for statusobj in status_obj:
            if (output.find(statusobj) == -1):
                log.error(f"Failed: {statusobj} missing")
                assert False, f"Failed: {statusobj} missing"

    log.info("Success: CUMULUS-SENSOR-MIB::entitySensorObjects")


def obj_index(output, object):
    index = [i for i, s in enumerate(output) if object in s]
    if "STRING" in output[index[0]]:
        object_value = output[index[0]].split('\"')[-2]
    else:
        if object == "agentSwitchCpuProcessMemFree":
            object_value = output[index[0]].split(' ')[-2]
        elif object == "agentSwitchCpuProcessMemTotal":
            object_value = output[index[0]].split(' ')[-2]
        else:
            object_value = output[index[0]].split(' ')[-1]
    return object_value


def verify_CPU_MEMORY_utilization(engines, port=None):

    with allure.step("Checking CPU and Memory utilization status"):
        out = HostMethods.host_snmp_walk_v2(engines.dut,
                                            ip_address='localhost',
                                            mib='1.3.6.1.4.1.40310.5',
                                            param='', port=port)

        out = out.split('\n')

        oneMinUtz = int(obj_index(out, "agentSwitchCpuProcess1minUtilization"))
        CpuutilizationStatus = obj_index(out, "agentSwitchCpuutilizationStatus")
        CPUUtzErrorFlag = obj_index(out, "agentSwitchCPUUtzErrorFlag")
        CPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")
        fullUtz = 100
        freeMem = obj_index(out, "agentSwitchCpuProcessMemFree")
        totalMem = obj_index(out, "agentSwitchCpuProcessMemTotal")
        freeMemPercentage = int(int(freeMem) * 100 / int(totalMem))
        SwitchMemStatus = obj_index(out, "agentSwitchMemStatus")
        SwitchMemErrorFlag = obj_index(out, "agentSwitchMemErrorFlag")
        SwitchCPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")

        with allure.step("Checking CPU utilization status"):
            if oneMinUtz <= fullUtz / 4:
                log.info(f"Current CPU utilization {oneMinUtz} ")
            if CpuutilizationStatus != "normal(3)":
                log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status NORMAL")
                assert False, "Failed: CPU utilization status incorrect"
            if CPUUtzErrorFlag != "noError(0)":
                log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                assert False, "Failed: CPU utilization Error flag incorrect"
            if CPUUtzErrorMsg != "No Error":
                log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz / 4 <= oneMinUtz < fullUtz / 2:
                log.info(f"Current CPU utilization {oneMinUtz} ")
                if CpuutilizationStatus != "warning(4)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status WARNING ")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "noError(0)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz / 2 <= oneMinUtz < fullUtz * 3 / 4:
                log.info(f"Current CPU utilization {oneMinUtz}")
                if CpuutilizationStatus != "alert(5)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "noError(0)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'noError' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'NoError' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"
            elif fullUtz * 3 / 4 <= oneMinUtz:
                log.info(f"Current CPU utilization {oneMinUtz}")
                if CpuutilizationStatus != "critical(6)":
                    log.error(f"Failed: CPU utilization status \
{CpuutilizationStatus} incorrect.Expected status CRITICAL")
                    assert False, "Failed: CPU utilization status incorrect"
                if CPUUtzErrorFlag != "error(1)":
                    log.error(f"Failed: CPU utilization Error flag \
{CPUUtzErrorFlag} incorrect. Expected 'error(1)' flag")
                    assert False, "Failed:CPU utilization Error flag incorrect"
                if CPUUtzErrorMsg != "CPU Utilization exceeds threshold":
                    log.error(f"Failed: CPU utilization Error Msg \
{CPUUtzErrorMsg} incorrect. Expected 'CPU Utilization exceeds threshol' Msg")
                    assert False, "Failed: CPU utilization Error Msg incorrect"

        with allure.step("Checking Memory utilization status"):
            if freeMemPercentage >= 75:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "normal(3)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status NORMAL ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "noError(0)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 75 > freeMemPercentage >= 50:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "warning(4)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status WARNING ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "noError(0)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 50 > freeMemPercentage >= 25:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "alert(5)":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "error(1)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'error(1)' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "No Error":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"
            elif 25 > freeMemPercentage:
                log.info(f"Current Memory utilization {freeMemPercentage}")
                if SwitchMemStatus != "":
                    log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status ALERT ")
                    assert False, "Failed: MEM utilization status incorrect"
                if SwitchMemErrorFlag != "error(1)":
                    log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'error(1)' flag")
                    assert False, "Failed:MEM utilization Error flag incorrect"
                if SwitchCPUUtzErrorMsg != "Free Memory gone below threshold":
                    log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. \
Expected 'Free Memory gone below threshold' flag")
                    assert False, "Failed: MEM utilization Error Msg incorrect"


def verify_mem_utilization(engines, port=None):
    with allure.step("Checking Memory utilization status"):
        out = HostMethods.host_snmp_walk_v2(engines.dut,
                                            ip_address='localhost',
                                            mib='1.3.6.1.4.1.40310.5',
                                            param='', port=port)
        out = out.split('\n')
        freeMem = obj_index(out, "agentSwitchCpuProcessMemFree")
        totalMem = obj_index(out, "agentSwitchCpuProcessMemTotal")
        freeMemPercentage = int(int(freeMem) * 100 / int(totalMem))
        SwitchMemStatus = obj_index(out, "agentSwitchMemStatus")
        SwitchMemErrorFlag = obj_index(out, "agentSwitchMemErrorFlag")
        SwitchCPUUtzErrorMsg = obj_index(out, "agentSwitchCPUUtzErrorMsg")
        if freeMemPercentage >= 75:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "normal(3)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status NORMAL ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
        if SwitchCPUUtzErrorMsg != "No Error":
            log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect.Expected 'No Error' flag")
            assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 75 > freeMemPercentage >= 50:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "warning(4)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect.Expected status WARNING ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error("Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect.Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 50 > freeMemPercentage >= 25:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "alert(5)":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect. Expected status ALERT ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "noError(0)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect. Expected 'noError' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "No Error":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'No Error' flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"
        elif 25 > freeMemPercentage:
            log.info(f"Current Memory utilization {freeMemPercentage}")
            if SwitchMemStatus != "":
                log.error(f"Failed: Memory utilization status \
{SwitchMemStatus} incorrect. Expected status ALERT ")
                assert False, "Failed: MEM utilization status incorrect"
            if SwitchMemErrorFlag != "error(1)":
                log.error(f"Failed: Memory utilization Error flag \
{SwitchMemErrorFlag} incorrect. Expected 'error(1)' flag")
                assert False, "Failed: MEM utilization Error flag incorrect"
            if SwitchCPUUtzErrorMsg != "Free Memory gone below threshold":
                log.error(f"Failed: Memory utilization Error Msg \
{SwitchCPUUtzErrorMsg} incorrect. Expected 'Free Memory gone below threshold' \
flag")
                assert False, "Failed: MEM utilization Error Msg incorrect"


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test01_snmp_support_on_EntitySensor_mib(engines, topology_obj):
    """
        Verify snmpwalk(v1/v2) support on Sensor/Status MIB using localhost
        SNMP support should present for Sensor/Status MIB
    """
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify Sensor and Status MIB using localhost v2 snmpwalk"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test02_verify_CPU_MEMORY_utilization(engines):
    """
        Verify Status MIB is showing various CPU and Memory utilization
        states/ErrorFlag using localhost.
        SNMP support should present for various CPU and Memory utilization
        states/ErrorFlag.
    """
    snmp_port = 1
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port, cumulus=True)

    with allure.step("Verify CPU Memory Utilization using localhost v2 snmpwalk"):
        verify_CPU_MEMORY_utilization(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test03_verify_memory_utilization(engines):
    """
        Verify Status MIB is showing various MEM utilization states/ErrorFlag
        using localhost.
        SNMP support should present for various MEM utilization
        states/ErrorFlag.
    """
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify memory utilization using localhost v2 snmpwalk"):
        verify_mem_utilization(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test10_verify_snmp_on_EntitySensorMib_after_snmp_restart(engines):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after snmpd restart
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    snmp_port = 65535
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port, cumulus=True)

    with allure.step("Verify MIBs before SNMP service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)
    with allure.step("Restart SNMP service"):
        cmd1 = "sudo systemctl reset-failed"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd1)
        cmd2 = "sudo systemctl restart snmpd"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After SNMP service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test11_verify_snmp_on_EntitySensorMib_after_networking_restart(engines):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after networking restart
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", cumulus=True)

    with allure.step("Verify MIBs before networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("Restart Networking service"):
        cmd1 = "sudo systemctl restart networking"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd1)
        cmd2 = "sudo systemctl restart snmpd.service"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After Networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines)
        verify_CUMULUS_STATUS_MIB(engines)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.localhost
def test12_verify_snmp_on_EntitySensorMib_after_switch_reboot(engines, devices):
    """
        Verify snmpwalk on Sensor/Status MIB OIDs after switch reboot
        using localhost.
        SNMP support should present for Sensor/Status MIB
    """
    snmp_port = 333
    system = System(None)
    with allure.step("Enable snmp"):
        HostMethods.start_snmp_server(engine=engines.dut,
                                      state=NvosConst.ENABLED,
                                      readonly_community='defaultuser',
                                      listening_address='all',
                                      access="any", vrf="mgmt", port=snmp_port,
                                      cumulus=True)

    with allure.step("Verify MIBs before networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("Reboot Dut"):
        engines.dut.run_cmd("sudo reboot")
        DutUtilsTool.wait_on_system_reboot(engines.dut)
        cmd2 = "sudo systemctl restart snmpd.service"
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command=cmd2)

    with allure.step("Verify MIBs After Networking service restart"):
        verify_CUMULUS_SENSOR_MIB(engines, port=snmp_port)
        verify_CUMULUS_STATUS_MIB(engines, port=snmp_port)

    with allure.step("SNMP unset"):
        system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()

# Commenting out below testcases till there is more common OM alignment
# @pytest.mark.system
# def test_CUMULUS_SNMP_MIB(engines, topology_obj):
#     """
#     Verify that walk includes CUMULUS-RESOURCES-MIB, and CUMULUS-COUNTERS-MIB
#     mibs. CUMULUS-SNMP-MIB is just an anchor.
#     """
#     #skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     #host_engine = engines.ha
#     host_engine = LinuxSshEngine(snmp_host, snmp_host_user, snmp_host_pass)
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     snmp_mib_oids = [
#         'CUMULUS-RESOURCES-MIB',
#         'CUMULUS-COUNTERS-MIB'
#     ]
#     with allure.step("Checking: CUMULUS-SNMP-MIB::cumulusMib"):
#         output = HostMethods.host_snmp_walk_v2(host_engine,
#                                                ip_address=ip_address,
#                                                community='public',
#                                                mib='CUMULUS-SNMP-MIB::cumulusMib')

#         for mib in snmp_mib_oids:
#             if not re.search("{0}.*".format(mib), output):
#                 log.error("Failed: {0} missing".format(mib))
#                 assert False, "Failed: {0} missing".format(mib)

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True, ask_for_confirmation=True).verify_result()


# @pytest.mark.system
# def test_ENTITY_MIB(engines, topology_obj):
#     """
#     Verify OIDs under ENTITY-MIB via snmp getnext
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: ENTITY-MIB::entPhysicalDescr"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalDescr')
#         if not re.search(".entPhysicalDescr.*", out):
#             log.error("Failed: entPhysicalDescr missing")
#             assert False, "Failed: entPhysicalDescr missing"
#         log.info("Success: ENTITY-MIB::entPhysicalDescr")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalVendorType"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalVendorType')
#         if not re.search(".entPhysicalVendorType.*%s" % ("SNMPv2-SMI::zeroDotZero"), out):
#             log.error("Failed: entPhysicalVendorType missing or wrong")
#             assert False, "Failed: entPhysicalVendorType missing or wrong"
#         log.info("Success: ENTITY-MIB::entPhysicalVendorType")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalContainedIn"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalContainedIn')
#         if not re.search(".entPhysicalContainedIn.*", out):
#             log.error("Failed: entPhysicalContainedIn missing")
#             assert False, "Failed: entPhysicalContainedIn missing"
#         log.info("Success: ENTITY-MIB::entPhysicalContainedIn")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalClass"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalClass')
#         if not re.search(".entPhysicalClass.*", out):
#             log.error("Failed: entPhysicalClass missing")
#             assert False, "Failed: entPhysicalClass missing"
#         log.info("Success: ENTITY-MIB::entPhysicalClass")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalParentRelPos"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalParentRelPos')
#         if not re.search(".entPhysicalParentRelPos.*", out):
#             log.error("Failed: entPhysicalParentRelPos missing")
#             assert False, "Failed: entPhysicalParentRelPos missing"
#         log.info("Success: ENTITY-MIB::entPhysicalParentRelPos")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalName"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalName')
#         if not re.search(".entPhysicalName.*", out):
#             log.error("Failed: entPhysicalName missing")
#             assert False, "Failed: entPhysicalName missing"
#         log.info("Success: ENTITY-MIB::entPhysicalName")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalHardwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalHardwareRev')
#         if not re.search(".entPhysicalHardwareRev.*", out):
#             log.error("Failed: entPhysicalHardwareRev missing")
#             assert False, "Failed: entPhysicalHardwareRev missing"
#         log.info("Success: ENTITY-MIB::entPhysicalHardwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalFirmwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalFirmwareRev')
#         if not re.search(".entPhysicalFirmwareRev.*", out):
#             log.error("Failed: entPhysicalFirmwareRev missing")
#             assert False, "Failed: entPhysicalFirmwareRev missing"
#         log.info("Success: ENTITY-MIB::entPhysicalFirmwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalSoftwareRev"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalSoftwareRev')
#         if not re.search(".entPhysicalSoftwareRev.*%s" % ("Cumulus-linux"), out):
#             log.error("Failed: entPhysicalSoftwareRev missing or wrong")
#             assert False, "Failed: entPhysicalSoftwareRev missing or wrong"
#         log.info("Success: ENTITY-MIB::entPhysicalSoftwareRev")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalSerialNum"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalSerialNum')
#         if not re.search(".entPhysicalSerialNum.*", out):
#             log.error("Failed: entPhysicalSerialNum missing")
#             assert False, "Failed: entPhysicalSerialNum missing"
#         log.info("Success: ENTITY-MIB::entPhysicalSerialNum")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalMfgName"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalMfgName')
#         if not re.search(".entPhysicalMfgName.*", out):
#             log.error("Failed: entPhysicalMfgName missing")
#             assert False, "Failed: entPhysicalMfgName missing"
#         log.info("Success: ENTITY-MIB::entPhysicalMfgName")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalAlias"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalAlias')
#         if not re.search(".entPhysicalAlias.*", out):
#             log.error("Failed: entPhysicalAlias missing")
#             assert False, "Failed: entPhysicalAlias missing"
#         log.info("Success: ENTITY-MIB::entPhysicalAlias")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalAssetID"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalAssetID')
#     if not re.search(".entPhysicalAssetID.*", out):
#         log.error("Failed: entPhysicalAssetID missing")
#         assert False, "Failed: entPhysicalAssetID missing"
#     log.info("Success: ENTITY-MIB::entPhysicalAssetID")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalIsFRU"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalIsFRU')
#         if not re.search(".entPhysicalIsFRU.*", out):
#             log.error("Failed: entPhysicalIsFRU missing")
#             assert False, "Failed: entPhysicalIsFRU missing"
#         log.info("Success: ENTITY-MIB::entPhysicalIsFRU")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalMfgDate"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalMfgDate')
#         if not re.search(".entPhysicalMfgDate.*", out):
#             log.error("Failed: entPhysicalMfgDate missing")
#             assert False, "Failed: entPhysicalMfgDate missing"
#         log.info("Success: ENTITY-MIB::entPhysicalMfgDate")

#     with allure.step("Checking: ENTITY-MIB::entPhysicalUris"):
#         out = HostMethods.host_snmp_getnext(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='ENTITY-MIB::entPhysicalUris')
#         if not re.search(".entPhysicalUris.*", out):
#             log.error("Failed: entPhysicalUris missing")
#             assert False, "Failed: entPhysicalUris missing"
#         log.info("Success: ENTITY-MIB::entPhysicalUris")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_MPD_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Mpd MIB
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Mpd MIB"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.11')
#         oids_list = [
#             'snmpUnknownSecurityModels',
#             'snmpInvalidMsgs',
#             'snmpUnknownPDUHandlers'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Snmp Mpd Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_VACM_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Vacm Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Vacm Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.4.1.8072.1.9')
#         oids_list = [
#             'nsVacmContextMatch',
#             'nsVacmViewName',
#             'nsVacmStorageType',
#             'nsVacmStatus'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Snmp Vacm Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Notification_Log_MIB(engines, topology_obj):
#     """
#     Checking: Notification Log Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Notification Log Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.2.1.92')
#         oids_list = [
#             'nlmConfigGlobalEntryLimit',
#             'nlmConfigGlobalAgeOut',
#             'nlmStatsGlobalNotificationsLogged',
#             'nlmStatsGlobalNotificationsBumped'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: Notification Log Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_Target_MIB(engines, topology_obj):
#     """
#     Checking: Snmp Target MIB
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp Target MIB"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.12')
#         oids_list = [
#             'snmpTargetSpinLock',
#             'snmpUnavailableContexts',
#             'snmpUnknownContexts'
#         ]
#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)
#         log.info("Success: Snmp Target Mib")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_System_MIB(engines, topology_obj):
#     """
#     Checking: SNMPv2-MIB::system
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: SNMPv2-MIB::system"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='SNMPv2-MIB::system')

#         if not re.search(".*sysDescr.*%s.*%s.*" % ("Cumulus-linux", "Linux Kernel"), out):
#             log.error("Failed: sysDescr missing or wrong")
#             assert False, "Failed: sysDescr missing or wrong"

#         if not re.search(".*sysContact.*", out):
#             log.error("Failed: sysContact missing")
#             assert False, "Failed: sysContact missing"

#         snmpname = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['hostname']
#         if not re.search(".*sysName.*%s.*" % (snmpname), out):
#             log.error("Failed: sysName missing or wrong")
#             assert False, "Failed: sysName missing or wrong"

#         if not re.search(".*sysLocation.*", out):
#             log.error("Failed: sysLocation missing")
#             assert False, "Failed: sysLocation missing"

#         log.info("Success: SNMPv2-MIB::system")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()


# @pytest.mark.system
# def test_Snmp_User_Base_Cm_MIB(engines, topology_obj):
#     """
#     Checking: Snmp User Based Cm Mib
#     """
#     skip_if_engines_does_not_exist_in_setup([NvosConst.HOST_HA], engines)
#     system = System(None)
#     host_engine = engines.ha
#     ip_address = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['ip_address']
#     with allure.step("Enable snmp"):
#         HostMethods.start_snmp_server(engine=engines.dut,
#                                       state=NvosConst.ENABLED,
#                                       readonly_community='public',
#                                       listening_address='all',
#                                       access="any", vrf="mgmt", cumulus=True)

#     with allure.step("Checking: Snmp User Based Cm Mib"):
#         out = HostMethods.host_snmp_walk_v2(host_engine,
#                                             ip_address=ip_address,
#                                             community='public',
#                                             mib='1.3.6.1.6.3.15')

#         oids_list = [
#             'usmStatsUnsupportedSecLevels',
#             'usmStatsNotInTimeWindows',
#             'usmStatsUnknownUserNames',
#             'usmStatsUnknownEngineIDs',
#             'usmStatsWrongDigests',
#             'usmStatsDecryptionErrors',
#             'usmUserSpinLock',
#             'usmUserSecurityName',
#             'usmUserCloneFrom',
#             'usmUserAuthProtocol',
#             'usmUserAuthKeyChange',
#             'usmUserOwnAuthKeyChange',
#             'usmUserPrivProtocol',
#             'usmUserPrivKeyChange',
#             'usmUserOwnPrivKeyChange',
#             'usmUserPublic',
#             'usmUserStorageType',
#             'usmUserStatus'
#         ]

#         for oid in oids_list:
#             if not re.search(".{0}.*".format(oid), out):
#                 log.error("Failed: {0} missing".format(oid))
#                 assert False, "Failed: {0} missing".format(oid)

#         log.info("Success: SNMP-USER-BASED-SM-MIB")

#     with allure.step("SNMP unset"):
#         system.snmp_server.unset(apply=True).verify_result()
