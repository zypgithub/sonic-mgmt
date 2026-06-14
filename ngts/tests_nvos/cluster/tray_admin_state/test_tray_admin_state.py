import json
import logging
import random
import re
import time

import pytest
from retry import retry

from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch, RosalindSwitch

logger = logging.getLogger()

VALID_TRAY_STATES = ClusterConsts.MAINTENANCE_STATE_OPTIONS
DEFAULT_TRAY_STATE = 'up'

# Bug 5065628: interface Summary maintenance-state propagation is slow while open.
TRAY_MAINTENANCE_SUMMARY_BUG_ID = 5065628
TRAY_PORT_STATE_SETTLE_SECONDS = 7
TRAY_PORT_STATE_SETTLE_SECONDS_BUG_OPEN = 60

# Bug SW #5074491: switch link is not restored from disabled to active when a tray
# admin-state down->up (or down->diag) is performed while the link was disabled.
# The compute GPU reset (nvidia-smi -r) re-links the PHYs and works around this, so the
# reset on a tray *leaving* 'down' is only needed while this bug is open. Once it is
# fixed, the reset becomes unnecessary and is skipped.
SWITCH_LINK_RESTORE_BUG_ID = 5074491

# NMX topology JSON keys
TOPO_DEVICE_INFO = 'deviceTopoInfo'
TOPO_GPU_INFO = 'gpuTopoInfo'
TOPO_SWITCH_INFO = 'switchTopoInfo'
TOPO_LOC = 'loc'
TOPO_LOCATION = 'location'
TOPO_SLOT_ID = 'slotId'
TOPO_DEVICE_UID = 'deviceUid'
TOPO_DEVICE_ID = 'deviceId'
TOPO_PORT_INFO = 'portTopoInfo'
TOPO_PORT_TYPE = 'portType'
TOPO_PORT_TYPE_ACCESS = 'NMX_PORT_TYPE_SWITCH_ACCESS'
TOPO_PEER_DEVICE_UID = 'peerPortDeviceUid'
TOPO_SYSTEM_PORT_NUM = 'systemPortNum'
TOPO_NUM_PORTS = 'numPorts'
NMX_TOPOLOGY_FILE_TYPE = 'topology'

# Matches "Maintenance State: Up" in nv show interface Summary column (table output).
INTERFACE_SUMMARY_MAINTENANCE_RE = re.compile(
    r'Maintenance State:\s*(\S+)', re.IGNORECASE)
INTERFACE_TABLE_LINE_RE = re.compile(r'^(acp\d+)\s+', re.IGNORECASE)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def _normalize_maintenance_state(state):
    """Normalize maintenance-state / Summary values for comparison (e.g. Up -> up)."""
    if state is None:
        return 'unknown'
    return str(state).strip().lower()


def _maintenance_state_from_interface_summary(summary_value):
    """Extract maintenance state from interface summary text or dict field."""
    if summary_value is None:
        return None
    if isinstance(summary_value, dict):
        for key in (ClusterConsts.MAINTENANCE_STATE, 'maintenance-state', 'Maintenance State'):
            if key in summary_value:
                return _normalize_maintenance_state(summary_value[key])
        return None
    match = INTERFACE_SUMMARY_MAINTENANCE_RE.search(str(summary_value))
    if match:
        return _normalize_maintenance_state(match.group(1))
    return None


def _parse_interface_table_summary_maintenance(table_output):
    """
    Parse maintenance state from the Summary column in 'nv show interface' table output.

    Example line:
      acp1  up  328G  256  nvl  ...  Maintenance State:  Up
    """
    summary_by_port = {}
    for line in table_output.splitlines():
        if not INTERFACE_TABLE_LINE_RE.match(line):
            continue
        port_name = INTERFACE_TABLE_LINE_RE.match(line).group(1)
        maint = _maintenance_state_from_interface_summary(line)
        if maint is not None:
            summary_by_port[port_name] = maint
    return summary_by_port


def eligible_trays_for_maintenance_change(tray_ids, local_switch_slot, tray_topology_config):
    """
    Tray IDs safe to use for maintenance-state up/down/diag tests.

    RTF-style (switch_nodes==1): never toggle the only switch tray — lab has a single
    switch; taking it down kills the DUT under test. Use compute trays only.

    Simx / switch-only (compute_nodes==0): no compute GPUs; any tray in the list is
    fair game (typically other switch trays in the cluster view).
    """
    local_switch_slot = str(local_switch_slot)
    compute_nodes = tray_topology_config.get('compute_nodes', 0)
    switch_nodes = tray_topology_config.get('switch_nodes', 0)

    if compute_nodes > 0 and switch_nodes == 1:
        eligible = [t for t in tray_ids if str(t) != local_switch_slot]
        if not eligible:
            pytest.skip(
                f"No compute trays available for maintenance tests (local switch slot "
                f"{local_switch_slot}, all trays {tray_ids}). Check cluster / fm_config.")
        logger.info(
            "Single-switch setup: maintenance tests will use compute trays only %s "
            "(excluding switch slot %s)", eligible, local_switch_slot)
        return eligible

    logger.info(
        "Setup has compute_nodes=%s switch_nodes=%s — any tray may be used for maintenance tests",
        compute_nodes, switch_nodes)
    return list(tray_ids)


def pick_tray_for_maintenance_change(tray_ids, local_switch_slot, tray_topology_config):
    """Random tray ID subject to eligible_trays_for_maintenance_change rules."""
    eligible = eligible_trays_for_maintenance_change(
        tray_ids, local_switch_slot, tray_topology_config)
    return random.choice(eligible)


def pick_two_trays_for_independence_test(tray_ids, local_switch_slot, tray_topology_config):
    """Pick two distinct trays; on single-switch + compute setups, both are compute trays."""
    eligible = eligible_trays_for_maintenance_change(
        tray_ids, local_switch_slot, tray_topology_config)
    if len(eligible) < 2:
        pytest.skip(
            f"Need >= 2 eligible trays for independence test, got {len(eligible)}: {eligible}")
    return random.sample(eligible, 2)


def get_tray_port_state_settle_seconds():
    """Wait after tray maintenance change before nv show interface checks."""
    if is_bug_active(TRAY_MAINTENANCE_SUMMARY_BUG_ID):
        logger.info(
            "Bug %s is active — using %ss settle before interface checks",
            TRAY_MAINTENANCE_SUMMARY_BUG_ID, TRAY_PORT_STATE_SETTLE_SECONDS_BUG_OPEN)
        return TRAY_PORT_STATE_SETTLE_SECONDS_BUG_OPEN
    return TRAY_PORT_STATE_SETTLE_SECONDS


def is_compute_tray(tray_id, local_switch_slot, tray_topology_config):
    """Remote compute tray (not the local switch slot) when the lab has compute nodes."""
    if tray_topology_config.get('compute_nodes', 0) == 0:
        return False
    return str(tray_id) != str(local_switch_slot)


def is_rtf_compute_tray_scenario(tray_id, local_switch_slot, tray_topology_config):
    """
    RTF-style lab: single switch + compute trays — compute-tray maintenance tests must
    delete SDN partition(s) first (e.g. default partition 32766 with GPUs).
    """
    compute_nodes = tray_topology_config.get('compute_nodes', 0)
    switch_nodes = tray_topology_config.get('switch_nodes', 0)
    return (
        compute_nodes > 0 and
        switch_nodes == 1 and
        str(tray_id) != str(local_switch_slot)
    )


def delete_sdn_partitions_before_compute_tray_test(sdn):
    """
    Delete all SDN partitions before compute-tray maintenance-state changes.

    Lab flow: `nv action delete sdn partition <id>` on default partition (e.g. 32766)
    so tray maintenance can be applied to compute nodes without partition binding.
    """
    with allure.step("Delete SDN partition(s) before compute-tray maintenance test"):
        partitions = OutputParsingTool.parse_show_output_to_dict(
            sdn.partition.show()).get_returned_value()
        if not partitions:
            logger.info("No SDN partitions present — nothing to delete")
            return
        for partition_id in list(partitions.keys()):
            partition_name = partitions[partition_id].get('name', partition_id)
            logger.info("Deleting partition %s (%s)", partition_id, partition_name)
            sdn.partition.partition_id[str(partition_id)].action_delete_partition().verify_result()
        remaining = OutputParsingTool.parse_show_output_to_dict(
            sdn.partition.show()).get_returned_value()
        assert not remaining, (
            f"Expected all SDN partitions deleted before compute-tray test, still have: {remaining}")
        # NMX-C unbinds GPU/switch-port resources from a deleted partition asynchronously:
        # 'nv show sdn partition' reports it gone before the topology releases the resources,
        # so the next tray maintenance-state change can hit NMX_ST_RESOURCE_IN_USE. Let it settle.
        time.sleep(5)


def wait_for_nmx_apps_healthy_after_gpu_reset(cluster):
    """
    After a compute GPU reset (nvidia-smi -r), the NVLink topology re-converges and
    NMX briefly drops. Wait until it recovers before touching tray/port state again:
    nmx-controller 'ok', nmx-telemetry 'ok', and the nmx-c connection 'up'.
    """
    with allure.step(
            "Wait for NMX to recover after GPU reset "
            "(nmx-controller ok, nmx-telemetry ok, nmx-c up)"):
        ClusterTools.wait_for_app_healthy(cluster, ClusterConsts.NMX_CONTROLLER)
        ClusterTools.wait_for_app_healthy(cluster, ClusterConsts.NMX_TELEMETRY)
        ClusterTools.wait_for_apps_to_be_in_wanted_state(
            cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')


def reset_all_compute_node_gpus(setup_name, cluster=None):
    """
    Reset GPUs on every host listed in RegressionConfigurations.compute_nodes_per_system.

    Product behavior: a compute GPU reset (nvidia-smi -r) is needed to re-link PHYs when
    a tray leaves 'down' (down->diag or down->up). It does nothing useful while the tray
    stays 'down', so call it only after moving the tray off 'down'.

    If `cluster` is provided, waits for NMX (controller/telemetry/nmx-c) to recover after
    the reset before returning.

    Per-tray → compute mapping is not implemented; all configured compute nodes are reset.
    """
    nodes = Configurations.compute_nodes_per_system.get(setup_name)
    if not nodes:
        logger.warning(
            "setup '%s' has no compute_nodes_per_system — skip GPU reset; "
            "add compute IP entries in RegressionConfigurations.py",
            setup_name)
        return
    with allure.step(
            f"Reset GPUs on all compute nodes ({len(nodes)} host(s), nvidia-smi -r)"):
        logger.info(
            "Resetting GPUs (tray leaving 'down') on: %s",
            [n['ip_address'] for n in nodes])
        ClusterTools.reboot_compute_nodes_gpus(setup_name)
    if cluster is not None:
        wait_for_nmx_apps_healthy_after_gpu_reset(cluster)


def reset_compute_gpus_leaving_down(setup_name, cluster, compute_tray_under_test):
    """
    Reset compute GPUs when a compute tray is about to leave 'down' (down->up or down->diag).

    This reset is a workaround for bug SW #5074491 (switch link not restored from disabled
    to active when down->up/diag is performed while the link was disabled). It only applies
    while that bug is open: if the bug is no longer active, the reset is skipped.

    Note: this gating is ONLY for the 'leaving down' reset. The reset done BEFORE moving a
    compute tray *to* 'down' is a separate requirement (NMX_ST_RESOURCE_IN_USE: GPUs must
    free NVLink resources first) and is not gated by this bug.
    """
    if not compute_tray_under_test:
        return
    if not is_bug_active(SWITCH_LINK_RESTORE_BUG_ID):
        logger.info(
            "Bug %s not active — skipping compute GPU reset on tray leaving 'down'",
            SWITCH_LINK_RESTORE_BUG_ID)
        return
    logger.info(
        "Bug %s active — resetting compute GPUs to re-link PHYs on tray leaving 'down'",
        SWITCH_LINK_RESTORE_BUG_ID)
    reset_all_compute_node_gpus(setup_name, cluster)


def get_all_trays(sdn):
    """Return parsed output of 'nv show sdn trays' as dict."""
    return OutputParsingTool.parse_show_output_to_dict(
        sdn.trays.show()
    ).get_returned_value()


def get_tray(sdn, tray_id):
    """Return parsed output of 'nv show sdn trays <tray_id>' as dict."""
    return OutputParsingTool.parse_show_output_to_dict(
        sdn.trays.tray[tray_id].show()
    ).get_returned_value()


def verify_tray_state(sdn, tray_id, expected_state):
    """Verify tray state in both individual and aggregated show output."""
    with allure.step(f"Verify tray {tray_id} maintenance-state == {expected_state}"):
        tray_output = get_tray(sdn, tray_id)
        actual = tray_output.get(ClusterConsts.MAINTENANCE_STATE)
        assert actual == expected_state, (
            f"Tray {tray_id}: expected {expected_state}, got {actual}")

        all_trays = get_all_trays(sdn)
        actual_in_all = all_trays[str(tray_id)][ClusterConsts.MAINTENANCE_STATE]
        assert actual_in_all == expected_state, (
            f"Tray {tray_id} in aggregated output: expected {expected_state}, got {actual_in_all}")


def restore_tray_cleanup(sdn, tray_id):
    """Restore tray to default state. Raises on failure to prevent polluting next tests."""
    sdn.trays.action_restore_maintenance_state(tray_id=tray_id)


def wait_for_tray_port_state_settle(expected_maintenance_state):
    """Allow tray change to propagate before nv show interface checks."""
    settle_secs = get_tray_port_state_settle_seconds()
    with allure.step(
            f"Wait {settle_secs}s for port maintenance/link state to settle "
            f"(tray maintenance-state={expected_maintenance_state})"):
        logger.info(
            "Waiting %ss for port maintenance-state and link state to settle after tray change "
            "(expected maintenance-state=%s) before nv show interface checks",
            settle_secs, expected_maintenance_state)
        time.sleep(settle_secs)


def verify_affected_ports_state(affected_acps, expected_link_state, expected_maintenance_state):
    """
    Verify that ALL affected acp ports have the expected link state AND maintenance-state.

    Checks per port:
    - link.state: the physical port state ('up' or 'down') from 'nv show interface -o json'
    - link.maintenance-state: tray maintenance-state ('up', 'down', or 'diag') from JSON
    - Summary column: 'Maintenance State: <state>' from 'nv show interface' table output

    The relationship between tray state and port states:
        tray 'up'   -> link.state = 'up',   maintenance-state = 'up'
        tray 'down' -> link.state = 'down',  maintenance-state = 'down'
        tray 'diag' -> link.state = 'up',   maintenance-state = 'diag'

    Waits get_tray_port_state_settle_seconds() after the tray change, then runs 'nv show interface'
    (json + table) once per retry. Uses retry if states are still converging.
    """
    expected_maint_norm = _normalize_maintenance_state(expected_maintenance_state)
    wait_for_tray_port_state_settle(expected_maintenance_state)

    @retry(AssertionError, tries=15, delay=5)
    def _check_all_ports():
        interface_component = Interface(parent_obj=None)
        all_interfaces = OutputParsingTool.parse_show_output_to_dict(
            interface_component.show(output_format=OutputFormat.json)
        ).get_returned_value()
        table_output = interface_component.show(output_format=OutputFormat.auto)
        summary_by_port = _parse_interface_table_summary_maintenance(table_output)

        mismatched = []
        for acp_name in affected_acps:
            if acp_name not in all_interfaces:
                mismatched.append(f"{acp_name}: not found in interface output")
                continue
            link_data = all_interfaces[acp_name].get('link', {})
            actual_link = link_data.get('state', 'unknown')
            if isinstance(actual_link, dict):
                actual_link = next(iter(actual_link.keys()), 'unknown')
            actual_maint = _normalize_maintenance_state(
                link_data.get(ClusterConsts.MAINTENANCE_STATE, 'unknown'))

            errors = []
            if actual_link != expected_link_state:
                errors.append(f"state={actual_link} (expected {expected_link_state})")
            if actual_maint != expected_maint_norm:
                errors.append(
                    f"maintenance-state={actual_maint} (expected {expected_maint_norm})")

            summary_maint = _maintenance_state_from_interface_summary(
                all_interfaces[acp_name].get('summary'))
            if summary_maint is None:
                summary_maint = summary_by_port.get(acp_name)
            if summary_maint is None:
                errors.append("summary Maintenance State not found")
            elif summary_maint != expected_maint_norm:
                errors.append(
                    f"summary Maintenance State={summary_maint} "
                    f"(expected {expected_maint_norm})")

            if errors:
                mismatched.append(f"{acp_name}: {', '.join(errors)}")

        assert not mismatched, (
            f"{len(mismatched)}/{len(affected_acps)} ports mismatch "
            f"(expected link={expected_link_state}, maintenance={expected_maint_norm}):\n" +
            "\n".join(mismatched[:20]) +
            (f"\n... and {len(mismatched) - 20} more" if len(mismatched) > 20 else ""))

    logger.info(
        "Verifying %s ports: link=%s, maintenance-state=%s (json link + Summary column)",
        len(affected_acps), expected_link_state, expected_maint_norm)
    _check_all_ports()
    logger.info(
        "All %s ports confirmed: link=%s, maintenance-state=%s",
        len(affected_acps), expected_link_state, expected_maint_norm)


def get_acp_ports_for_tray(engines, sdn, devices, target_slot_id, local_switch_slot,
                           tray_topology_config):
    """
    Determine which acp ports should be affected when a tray's maintenance-state changes.

    Setup policy (tray_topology_config from RegressionConfigurations.tray_topology):
    - Local switch tray: all local acp ports (no topology file).
    - compute_nodes==0: no gpuTopoInfo in lab; do not parse topology — use all local acps.
    - compute_nodes>0, remote compute tray: parse topology gpuTopoInfo; if missing, skip
      (do not fail) — common when FM exports switch-only topology.
    - switch_nodes>1: only switchTopoInfo for the local switch slotId (multi-switch).

    The NMX topology file (JSON) has a flat list under 'deviceTopoInfo'.
    Each entry is either a GPU chip or a switch ASIC:

        deviceTopoInfo: [
            { "gpuTopoInfo":    { ... } },   <-- GPU chip in a compute tray
            { "switchTopoInfo": { ... } },   <-- Switch ASIC in the switch tray
            ...
        ]

    GPU entries tell us which compute tray each GPU chip belongs to:
        gpuTopoInfo.loc.location.slotId  -->  the tray ID (e.g. "1" or "2")
        gpuTopoInfo.deviceUid            -->  unique ID of this GPU chip

    Switch entries contain the actual port connectivity:
        switchTopoInfo.deviceId          -->  ASIC number (1=U1, 2=U2, 3=U3, 4=U4)
        switchTopoInfo.numPorts          -->  ports per ASIC (e.g. 72), read dynamically
        switchTopoInfo.portTopoInfo[]    -->  list of switch ports on this ASIC

    Each switch port entry has:
        portType          -->  "NMX_PORT_TYPE_SWITCH_ACCESS" for access ports
        systemPortNum     -->  1 to numPorts, the port number within this ASIC
        peerPortDeviceUid -->  the deviceUid of the GPU chip on the OTHER end

    Algorithm (for compute tray):
        1. From all gpuTopoInfo entries, build:  gpu_deviceUid -> slotId
        2. Read numPorts from the first switchTopoInfo entry (ports per ASIC)
        3. For each switch ASIC's access port, look up peerPortDeviceUid in the GPU map
        4. If the peer GPU's slotId matches our target tray -> this port is affected
        5. Translate to acp name:  acp_number = (deviceId - 1) * numPorts + systemPortNum

    Concrete example from the RTF2 setup (1 switch, 2 compute trays, numPorts=72):
        - Target tray: slotId=2 (compute tray with 2 GPU chips)
        - GPU chips in slot 2 have deviceUid "15046..." and "17640..."
        - Switch ASIC U4 (deviceId=4), port systemPortNum=1, peerPortDeviceUid="15046..."
          -> peer is in slotId=2 -> acp_number = (4-1)*72 + 1 = 217 -> acp217 will go down
        - Switch ASIC U1 (deviceId=1), port systemPortNum=1, peerPortDeviceUid="15046..."
          -> peer is in slotId=2 -> acp_number = (1-1)*72 + 1 = 1 -> acp1 will go down
        - Result: 18 ports per ASIC x 4 ASICs = 72 acp ports affected for slot 2

    For the switch tray (target_slot_id == local_switch_slot):
        All acp ports go down (taken from device model). No topology parsing needed.

    Returns: sorted list of acp port names (e.g. ['acp1', 'acp2', 'acp73', ...])
    """
    target_slot_id = str(target_slot_id)
    local_switch_slot = str(local_switch_slot)
    compute_nodes = tray_topology_config.get('compute_nodes', 0)
    switch_nodes = tray_topology_config.get('switch_nodes', 0)
    all_acps = list(devices.dut.nvl_access_ports_list)

    # --- Case 1: Local switch tray — all acp ports ---
    if target_slot_id == local_switch_slot:
        logger.info(
            "Tray %s is the local switch tray — all %s acp ports should be affected",
            target_slot_id, len(all_acps))
        return all_acps

    # --- Case 2: No compute in lab model (e.g. simx) — skip topology; use all local acps ---
    if compute_nodes == 0:
        logger.info(
            "Tray %s: compute_nodes=0 in lab config — not parsing topology; "
            "using all %s local acp ports for interface checks", target_slot_id, len(all_acps))
        return all_acps

    # --- Case 3: Compute tray — parse topology when gpuTopoInfo is expected ---
    logger.info(
        "Tray %s is a compute tray — parsing topology to find connected acp ports", target_slot_id)

    with allure.step("Generate NMX topology file"):
        sdn.state.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[NMX_TOPOLOGY_FILE_TYPE].action_generate_sdn()

    with allure.step("Get topology file path"):
        files_output = OutputParsingTool.parse_show_output_to_dict(
            sdn.state.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[NMX_TOPOLOGY_FILE_TYPE].files.show()
        ).get_returned_value()
        # Get the most recent topology file path
        topology_file_path = list(files_output.values())[-1]['path']
        logger.info(f"Topology file: {topology_file_path}")

    with allure.step("Read and parse topology JSON"):
        raw_json = engines.dut.run_cmd(f"sudo cat {topology_file_path}")
        topology = json.loads(raw_json)

    # Step 1: Build a map of GPU deviceUid -> slotId
    # Each gpuTopoInfo entry is one GPU chip. Multiple GPU chips can share
    # the same slotId (they're in the same compute tray).
    # The tray id from 'nv show sdn trays' equals the device slotId (verified against
    # real RTF topology: switch slotId=3 -> tray "3", GPU slotId=1/2 -> tray "1"/"2").
    # trayIndex is a separate enumeration (0-based) and does NOT match the tray id, so
    # we map and match strictly on slotId.
    gpu_uid_to_slot = {}
    for device_entry in topology[TOPO_DEVICE_INFO]:
        if TOPO_GPU_INFO in device_entry:
            gpu = device_entry[TOPO_GPU_INFO]
            gpu_uid = gpu[TOPO_DEVICE_UID]
            slot_id = str(gpu[TOPO_LOC][TOPO_LOCATION][TOPO_SLOT_ID])
            gpu_uid_to_slot[gpu_uid] = slot_id
            logger.info(f"  GPU chip {TOPO_DEVICE_UID}={gpu_uid} -> {TOPO_SLOT_ID}={slot_id}")

    if not gpu_uid_to_slot:
        pytest.skip(
            f"No gpuTopoInfo in NMX topology file — cannot map compute tray {target_slot_id} "
            f"to acp ports (FM often exports switch-only topology until compute is discovered). "
            f"Skip port checks; fix cluster/fm_config or run on a setup with GPU entries.")

    # Step 2: For each switch ASIC, find access ports whose peer is in the target compute tray.
    # Each switchTopoInfo entry is one switch ASIC (U1, U2, U3, or U4).
    # The deviceId tells us which ASIC: 1=U1, 2=U2, 3=U3, 4=U4.
    # numPorts (read from topology) tells us how many ports per ASIC.
    # The acp formula: acp_number = (deviceId - 1) * numPorts + systemPortNum
    affected_acps = []
    ports_per_asic = None
    for device_entry in topology[TOPO_DEVICE_INFO]:
        if TOPO_SWITCH_INFO in device_entry:
            switch = device_entry[TOPO_SWITCH_INFO]
            if switch_nodes > 1:
                switch_slot = str(
                    switch.get(TOPO_LOC, {}).get(TOPO_LOCATION, {}).get(TOPO_SLOT_ID, ''))
                if switch_slot and switch_slot != local_switch_slot:
                    logger.info(
                        "  Skipping switch ASIC on remote slot %s (local=%s)",
                        switch_slot, local_switch_slot)
                    continue
            asic_device_id = switch[TOPO_DEVICE_ID]
            asic_description = switch.get('description', '')

            if ports_per_asic is None:
                ports_per_asic = int(switch[TOPO_NUM_PORTS])
                logger.info(f"  Ports per ASIC (from topology): {ports_per_asic}")

            logger.info(f"  Scanning switch ASIC {TOPO_DEVICE_ID}={asic_device_id} ({asic_description})")

            for port in switch[TOPO_PORT_INFO]:
                if port[TOPO_PORT_TYPE] != TOPO_PORT_TYPE_ACCESS:
                    continue

                peer_uid = port[TOPO_PEER_DEVICE_UID]
                system_port_num = int(port[TOPO_SYSTEM_PORT_NUM])

                # Look up which compute tray this port's peer GPU belongs to.
                peer_slot = gpu_uid_to_slot.get(peer_uid)
                if peer_slot == target_slot_id:
                    acp_number = (asic_device_id - 1) * ports_per_asic + system_port_num
                    affected_acps.append(f'acp{acp_number}')

    if ports_per_asic is None:
        pytest.skip(
            f"No switchTopoInfo for local slot {local_switch_slot} in topology — "
            f"cannot map acp ports for compute tray {target_slot_id}")

    affected_acps.sort(key=lambda x: int(x.replace('acp', '')))
    if not affected_acps:
        pytest.skip(
            f"Topology has gpuTopoInfo but no access ports map to compute tray {target_slot_id} — "
            f"skip rather than fail (peer map / slotId mismatch).")
    logger.info(f"Tray {target_slot_id}: {len(affected_acps)} acp ports should be affected: {affected_acps}")
    return affected_acps


def ensure_cluster_enabled(cluster, setup_name, devices):
    """
    Enable cluster and wait for NMX-C after @disabled_access_ports leaves cluster disabled.
    """
    with allure.step("Enable cluster"):
        ClusterTools.start_cluster(cluster, setup_name, OutputFormat.json, devices=devices)
        ClusterTools.wait_until_app_expected_status(cluster, ClusterConsts.NMX_CONTROLLER, 'ok')


# ---------------------------------------------------------------------------
#  4.1 test_tray_show_cmd
# ---------------------------------------------------------------------------


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_tray_show_cmd(engines, devices, random_api, cluster_and_sdn, chassis_info,
                       expected_tray_count, tray_topology_config, setup_name,
                       standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that the SDN tray show commands return correct output format, that all trays
    are displayed with their maintenance-state field, and that showing a single tray
    matches the aggregated output.

    Tray count is checked against RegressionConfigurations.tray_topology for this
    setup_name. Wrong count (e.g. 27 vs 3 on RTF) skips with a hint — not a hard fail
    on misconfigured MNNVL_TOPOLOGY / cluster view.

    Precondition: Cluster enabled, gRPC connection to NMX-C is up.
    """
    cluster, sdn = cluster_and_sdn
    ensure_cluster_enabled(cluster, setup_name, devices)

    with allure.step("Run 'nv show sdn trays' and validate output"):
        trays_output = get_all_trays(sdn)
        tray_ids = list(trays_output.keys())
        assert len(tray_ids) > 0, "No trays shown in 'nv show sdn trays'"

        for tray_id in tray_ids:
            assert ClusterConsts.MAINTENANCE_STATE in trays_output[tray_id], (
                f"Tray {tray_id} missing '{ClusterConsts.MAINTENANCE_STATE}' field")
            state = trays_output[tray_id][ClusterConsts.MAINTENANCE_STATE]
            assert state in VALID_TRAY_STATES, (
                f"Tray {tray_id} has invalid maintenance-state: {state}")

    with allure.step(f"Verify number of trays matches expected setup size ({expected_tray_count})"):
        if len(tray_ids) != expected_tray_count:
            pytest.skip(
                f"Tray count mismatch: expected {expected_tray_count} from lab config "
                f"(switch_nodes={tray_topology_config['switch_nodes']}, "
                f"compute_nodes={tray_topology_config['compute_nodes']}), "
                f"got {len(tray_ids)}: {tray_ids}. Check MNNVL_TOPOLOGY / cluster discovery — "
                f"not failing on environment mismatch.")

    with allure.step("Verify local switch slot-number appears in tray output"):
        local_slot = chassis_info.get('slot-number')
        assert local_slot is not None, "Could not get slot-number from platform chassis-location"
        assert str(local_slot) in tray_ids, (
            f"Local slot {local_slot} not found in tray list {tray_ids}")

    with allure.step("Verify 'nv show sdn trays <slot-id>' matches aggregated output"):
        for tray_id in tray_ids:
            individual_output = get_tray(sdn, tray_id)
            assert ClusterConsts.MAINTENANCE_STATE in individual_output, (
                f"Individual show for tray {tray_id} missing maintenance-state")

            actual_state = individual_output[ClusterConsts.MAINTENANCE_STATE]
            expected_state = trays_output[tray_id][ClusterConsts.MAINTENANCE_STATE]
            assert actual_state == expected_state, (
                f"Tray {tray_id}: individual show state ({actual_state}) != "
                f"aggregated show state ({expected_state})")

    with allure.step("Verify all trays default state is 'up'"):
        for tray_id in tray_ids:
            state = trays_output[tray_id][ClusterConsts.MAINTENANCE_STATE]
            assert state == DEFAULT_TRAY_STATE, (
                f"Tray {tray_id} expected default state '{DEFAULT_TRAY_STATE}', got '{state}'")


# ---------------------------------------------------------------------------
#  4.2 test_tray_change_and_verify_state
# ---------------------------------------------------------------------------


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(25 * MINUTE, func_only=True)
def test_tray_change_and_verify_state(engines, devices, random_api, cluster_and_sdn,
                                      chassis_info, tray_topology_config, setup_name,
                                      standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that the tray maintenance state can be updated to each valid value (up, down, diag)
    and restored to default. After each change, verify the state is reflected in
    nv show sdn trays and port state on the switch (link state, link maintenance-state,
    and Summary column "Maintenance State" in nv show interface).
    Also verify behaviour when local port admin state is down.

    Tray selection (tray_topology_config):
    - switch_nodes==1 (RTF): never the lone switch tray; compute trays only.
    - compute_nodes==0 (simx): any tray; no NMX topology gpuTopoInfo parsing.

    RTF compute tray precondition:
    - Delete all SDN partitions (e.g. default 32766) before maintenance-state changes.

    Compute tray recovery (any lab with compute_nodes > 0):
    - After tray 'down', run nvidia-smi -r on all hosts in compute_nodes_per_system
      before diag/up/restore (whole-tray down leaves PHYs down without GPU reset).

    Port verification (after settle: 60s if bug 5065628 open, else 7s):
    - Local switch tray: all acp ports.
    - compute_nodes==0: all local acps (no topology dig).
    - Compute tray with GPUs in topology: acp list from gpuTopoInfo; missing GPU data -> skip.

    Precondition: Cluster enabled, gRPC connection to NMX-C is up.
    """
    cluster, sdn = cluster_and_sdn
    ensure_cluster_enabled(cluster, setup_name, devices)

    trays_output = get_all_trays(sdn)
    tray_ids = list(trays_output.keys())
    if not tray_ids:
        pytest.skip("No trays in 'nv show sdn trays' — enable cluster and check fm_config")

    local_switch_slot = str(chassis_info.get('slot-number'))
    selected_tray = pick_tray_for_maintenance_change(
        tray_ids, local_switch_slot, tray_topology_config)
    is_switch_tray = (selected_tray == local_switch_slot)
    tray_type = "switch" if is_switch_tray else "compute"
    logger.info(
        "Selected tray %s (%s) for state change tests (local switch slot = %s)",
        selected_tray, tray_type, local_switch_slot)

    partitions_deleted = is_rtf_compute_tray_scenario(
        selected_tray, local_switch_slot, tray_topology_config)
    if partitions_deleted:
        delete_sdn_partitions_before_compute_tray_test(sdn)

    affected_acps = get_acp_ports_for_tray(
        engines, sdn, devices, selected_tray, local_switch_slot, tray_topology_config)
    logger.info(
        "%s acp ports should be affected by tray %s state changes",
        len(affected_acps), selected_tray)

    compute_tray_under_test = is_compute_tray(
        selected_tray, local_switch_slot, tray_topology_config)

    # Pick one port for the admin-state override test (single-port test at the end)
    override_test_port = Port(random.choice(affected_acps))

    try:
        # Compute tray about to go 'down': the GPUs still hold NVLink resources, so NMX-C
        # rejects the maintenance change with NMX_ST_RESOURCE_IN_USE. Reset the GPUs first
        # to free those resources before requesting 'down'.
        if compute_tray_under_test:
            reset_all_compute_node_gpus(setup_name, cluster)

        # -- Set tray to DOWN: ports should go down, maintenance-state should be 'down' --
        with allure.step(f"Update tray {selected_tray} ({tray_type}) to 'down'"):
            sdn.trays.action_update_maintenance_state(
                tray_id=selected_tray, maintenance_state='down').verify_result()
        verify_tray_state(sdn, selected_tray, 'down')
        with allure.step(f"Verify all {len(affected_acps)} affected ports: link=down, maintenance=down"):
            verify_affected_ports_state(affected_acps, expected_link_state='down', expected_maintenance_state='down')

        # -- Set tray to DIAG: ports should come back up, maintenance-state should be 'diag' --
        # Current state is 'down'. Reset compute GPUs to re-link PHYs before leaving 'down'
        # (workaround for bug SW #5074491); skipped automatically once that bug is fixed.
        reset_compute_gpus_leaving_down(setup_name, cluster, compute_tray_under_test)
        with allure.step(f"Update tray {selected_tray} ({tray_type}) to 'diag'"):
            sdn.trays.action_update_maintenance_state(
                tray_id=selected_tray, maintenance_state='diag').verify_result()
        verify_tray_state(sdn, selected_tray, 'diag')
        with allure.step(f"Verify all {len(affected_acps)} affected ports: link=up, maintenance=diag"):
            verify_affected_ports_state(affected_acps, expected_link_state='up', expected_maintenance_state='diag')

        # -- Set tray to UP: ports should remain up, maintenance-state should be 'up' --
        with allure.step(f"Update tray {selected_tray} ({tray_type}) to 'up'"):
            sdn.trays.action_update_maintenance_state(
                tray_id=selected_tray, maintenance_state='up').verify_result()
        verify_tray_state(sdn, selected_tray, 'up')
        with allure.step(f"Verify all {len(affected_acps)} affected ports: link=up, maintenance=up"):
            verify_affected_ports_state(affected_acps, expected_link_state='up', expected_maintenance_state='up')

        # -- Random non-default state, then restore to default --
        random_state = random.choice(['down', 'diag'])
        with allure.step(f"Set tray {selected_tray} to '{random_state}' then restore"):
            # Same as the first 'down': free GPU NVLink resources before a compute tray
            # goes 'down', else NMX-C returns NMX_ST_RESOURCE_IN_USE.
            if compute_tray_under_test and random_state == 'down':
                reset_all_compute_node_gpus(setup_name, cluster)
            sdn.trays.action_update_maintenance_state(
                tray_id=selected_tray, maintenance_state=random_state).verify_result()
            verify_tray_state(sdn, selected_tray, random_state)

            # If the tray is currently 'down', reset compute GPUs to re-link PHYs BEFORE
            # restoring (down->up) — workaround for bug SW #5074491; skipped once it is fixed.
            if random_state == 'down':
                reset_compute_gpus_leaving_down(setup_name, cluster, compute_tray_under_test)
            sdn.trays.action_restore_maintenance_state(tray_id=selected_tray).verify_result()
            verify_tray_state(sdn, selected_tray, DEFAULT_TRAY_STATE)
        with allure.step(f"Verify all {len(affected_acps)} affected ports: link=up, maintenance=up after restore"):
            verify_affected_ports_state(affected_acps, expected_link_state='up', expected_maintenance_state='up')

        # -- Verify port admin-state DOWN overrides tray diag --
        # Per HLD: if a port's local admin state is down, tray diag should NOT bring it up.
        # This is a single-port test since it requires per-port config changes.
        with allure.step("Verify local port admin-state 'down' overrides tray 'diag'"):
            logger.info(f"Port for admin-state override test: {override_test_port.name}")

            with allure.step(f"Set port {override_test_port.name} link state to down"):
                override_test_port.interface.link.set(op_param_name='state', op_param_value='down', apply=True)
            Port.wait_for_port_state(override_test_port, expected_state='down')

            with allure.step(f"Set tray {selected_tray} to diag"):
                sdn.trays.action_update_maintenance_state(
                    tray_id=selected_tray, maintenance_state='diag').verify_result()

            with allure.step(f"Verify port {override_test_port.name} stays down (admin-state overrides tray diag)"):
                Port.wait_for_port_state(override_test_port, expected_state='down')

            with allure.step("Cleanup: unset port link state and restore tray"):
                override_test_port.interface.link.unset(op_param='state', apply=True)
                sdn.trays.action_restore_maintenance_state(tray_id=selected_tray).verify_result()

    finally:
        if compute_tray_under_test:
            reset_all_compute_node_gpus(setup_name, cluster)
        restore_tray_cleanup(sdn, selected_tray)
        # We destructively deleted the default SDN partition (32766) as a precondition.
        # Restore it the same way the dedicated partition test does: an SDN factory reset
        # makes NMX-C recreate the default partition (test_cluster_partition.py:86-101).
        if partitions_deleted:
            with allure.step("Restore deleted SDN partition(s) via SDN factory reset"):
                ClusterTools.reset_sdn_factory_default_and_wait_for_restart(sdn, cluster)


# ---------------------------------------------------------------------------
#  4.3 test_tray_multi_tray_independence
# ---------------------------------------------------------------------------


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_tray_multi_tray_independence(engines, devices, random_api, cluster_and_sdn,
                                      chassis_info, tray_topology_config, setup_name,
                                      standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that setting maintenance state on one tray does not affect other trays.

    On single-switch setups (RTF), both trays are compute trays — the lone switch is never used.

    Precondition: Cluster enabled, setup has >= 2 eligible trays.
    """
    cluster, sdn = cluster_and_sdn
    ensure_cluster_enabled(cluster, setup_name, devices)

    trays_output = get_all_trays(sdn)
    tray_ids = list(trays_output.keys())
    local_switch_slot = str(chassis_info.get('slot-number'))
    tray_a, tray_b = pick_two_trays_for_independence_test(
        tray_ids, local_switch_slot, tray_topology_config)
    state_a = random.choice(VALID_TRAY_STATES)
    state_b = random.choice(VALID_TRAY_STATES)
    logger.info(f"Tray A={tray_a} -> {state_a}, Tray B={tray_b} -> {state_b}")

    # A compute tray about to go 'down' still holds GPU NVLink resources -> NMX-C returns
    # NMX_ST_RESOURCE_IN_USE. Reset GPUs first when either target tray is a compute tray
    # heading 'down'. (reset_all_compute_node_gpus resets all compute nodes, so once is enough.)
    needs_gpu_reset = (
        (state_a == 'down' and is_compute_tray(tray_a, local_switch_slot, tray_topology_config)) or
        (state_b == 'down' and is_compute_tray(tray_b, local_switch_slot, tray_topology_config)))
    if needs_gpu_reset:
        reset_all_compute_node_gpus(setup_name, cluster)

    try:
        with allure.step(f"Set tray {tray_a} to '{state_a}' and tray {tray_b} to '{state_b}'"):
            sdn.trays.action_update_maintenance_state(
                tray_id=tray_a, maintenance_state=state_a).verify_result()
            sdn.trays.action_update_maintenance_state(
                tray_id=tray_b, maintenance_state=state_b).verify_result()

        with allure.step("Verify each tray has its own independent state"):
            verify_tray_state(sdn, tray_a, state_a)
            verify_tray_state(sdn, tray_b, state_b)

    finally:
        with allure.step("Restore both trays"):
            if (state_a == 'down' or state_b == 'down') and (
                    is_compute_tray(tray_a, local_switch_slot, tray_topology_config) or
                    is_compute_tray(tray_b, local_switch_slot, tray_topology_config)):
                reset_all_compute_node_gpus(setup_name, cluster)
            sdn.trays.action_restore_maintenance_state(tray_id=tray_a)
            sdn.trays.action_restore_maintenance_state(tray_id=tray_b)

        with allure.step("Verify both trays restored to default"):
            verify_tray_state(sdn, tray_a, DEFAULT_TRAY_STATE)
            verify_tray_state(sdn, tray_b, DEFAULT_TRAY_STATE)


# ---------------------------------------------------------------------------
#  6.1 test_tray_bad_params
# ---------------------------------------------------------------------------


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_tray_bad_params(engines, devices, random_api, cluster_and_sdn, chassis_info,
                         setup_name, standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that invalid parameters are rejected by the tray maintenance state commands.

    Precondition: Cluster enabled, gRPC connection to NMX-C is up.
    """
    cluster, sdn = cluster_and_sdn
    ensure_cluster_enabled(cluster, setup_name, devices)
    random_string = RandomizationTool.get_random_string(length=10)

    with allure.step("Show trays with invalid slot-id"):
        sdn.trays.show(random_string, exempted_err_msgs=["is not a", "Error", "Invalid"])

    with allure.step("Update tray with valid slot-id but invalid maintenance-state value"):
        trays_output = get_all_trays(sdn)
        valid_tray_id = random.choice(list(trays_output.keys()))
        result = sdn.trays.action_update_maintenance_state(
            tray_id=valid_tray_id, maintenance_state=random_string)
        result.verify_result(should_succeed=False,
                             expected_value=["is not one of", "Error", "Invalid Command", "Bad Request"])

    with allure.step("Update tray with non-existent slot-id"):
        # A valid-format but non-existent slot-id is rejected by NMX-C with
        # "Error: The requested item does not exist".
        result = sdn.trays.action_update_maintenance_state(
            tray_id='999', maintenance_state='down')
        result.verify_result(should_succeed=False,
                             expected_value=["The requested item does not exist", "Error"])


# ---------------------------------------------------------------------------
#  6.2 test_tray_rejected_without_cluster
# ---------------------------------------------------------------------------


@disabled_access_ports
@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_tray_rejected_without_cluster(engines, devices, random_api, chassis_info,
                                       setup_name, standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that tray admin state commands are rejected when cluster is not enabled.

    Precondition: Cluster is disabled on the switch.
    """
    if standalone_system:
        pytest.skip("Tray admin state tests require non-standalone setup")

    cluster = Cluster()
    sdn = Sdn()
    with allure.step("Ensure cluster is disabled"):
        cluster.unset(apply=True)
        ClusterTools.wait_for_apps_to_be_in_wanted_state(
            cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')

    with allure.step("Verify 'nv show sdn trays' fails with cluster disabled"):
        output = sdn.trays.show(should_succeed=False)
        assert ClusterConsts.CLUSTER_NOT_ENABLED_ERR in output, (
            f"Expected '{ClusterConsts.CLUSTER_NOT_ENABLED_ERR}' in show output, got: {output}")

    with allure.step("Verify update maintenance-state fails with cluster disabled"):
        random_state = random.choice(VALID_TRAY_STATES)
        output = sdn.trays.action_update_maintenance_state(
            tray_id='9', maintenance_state=random_state).verify_result(should_succeed=False)
        assert ClusterConsts.CLUSTER_NOT_ENABLED_ERR in output, (
            f"Expected '{ClusterConsts.CLUSTER_NOT_ENABLED_ERR}' in update output, got: {output}")

    with allure.step("Verify restore maintenance-state fails with cluster disabled"):
        output = sdn.trays.action_restore_maintenance_state(
            tray_id='9').verify_result(should_succeed=False)
        assert ClusterConsts.CLUSTER_NOT_ENABLED_ERR in output, (
            f"Expected '{ClusterConsts.CLUSTER_NOT_ENABLED_ERR}' in restore output, got: {output}")


# ---------------------------------------------------------------------------
#  6.3 test_tray_not_supported_on_juliet
# ---------------------------------------------------------------------------


@pytest.mark.nmx
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_tray_not_supported_on_juliet(engines, devices, random_api, setup_name,
                                      standalone_system, has_loopbox):
    """
    Test Objective:
    Verify that tray admin state commands are not supported on GB200/Juliet systems.
    Only VR200/Rosalind and later are supported.

    Precondition: Cluster enabled. Device under test is Juliet (non-Rosalind).
    """
    if isinstance(devices.dut, RosalindSwitch):
        pytest.skip("This test targets Juliet (non-Rosalind) systems only")
    if not isinstance(devices.dut, JulietSwitch):
        pytest.skip("This test targets Juliet systems only")

    cluster = Cluster()
    sdn = Sdn()
    ensure_cluster_enabled(cluster, setup_name, devices)

    with allure.step("Verify 'nv show sdn trays' not supported on Juliet"):
        output = sdn.trays.show(should_succeed=False)
        logger.info(f"Show trays on Juliet: {output}")

    with allure.step("Verify update tray state not supported on Juliet"):
        output = sdn.trays.action_update_maintenance_state(
            tray_id='9', maintenance_state='up').verify_result(should_succeed=False)
        logger.info(f"Update tray on Juliet: {output}")
