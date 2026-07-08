import re
import pytest
import logging
from types import SimpleNamespace

from ngts.constants.constants import MarsConstants, SonicConst, TxSquelchConsts
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure


logger = logging.getLogger(__name__)

# Batch parser: table block.
TX_SQUELCH_SECTION_RE = re.compile(
    r'\|\s*Port ID\s*\|\s*Tx Squelch\s*\|'
    r'.+?'
    r'={2,}',
    re.DOTALL)

# Batch parser: data rows.
TX_SQUELCH_DATA_ROW_RE = re.compile(
    r'\|\s*(0x[0-9a-fA-F]+)\s*\|\s*(\w+)\s*\|')

# GNU sed: strip trailing blank lines so appended KV entries sit on the next line.
_TRIM_TRAILING_BLANK_LINES_SED = "-e :a -e '/^\\s*$/{ $d; N; ba; }'"


@pytest.fixture(scope="session", autouse=True)
def verify_supported_hwsku(duthosts):
    """Skip TX squelch tests when DUT HWSKU is not supported"""
    with allure.step("Check HWSKU is supported"):
        hwsku = duthosts[0].facts["hwsku"]
        if hwsku not in TxSquelchConsts.SUPPORTED_HWSKUS:
            pytest.skip(
                f"HWSKU '{hwsku}' is not supported by the TX squelch KV tests. "
                f"Supported HWSKUs: {sorted(TxSquelchConsts.SUPPORTED_HWSKUS)}")


def get_tx_squelch_kv(duthost, sai_profile_path):
    """Read current TX squelch KV value from sai.profile"""
    result = duthost.shell(
        f"grep '^{TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV}=' {sai_profile_path}",
        module_ignore_errors=True)
    if result['rc'] != 0 or not result['stdout'].strip():
        return None
    value = result['stdout'].strip().split('=', 1)[-1]
    logger.info(f"Current {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} in sai.profile: {value}")
    return value


def write_tx_squelch_kv(duthost, sai_profile_path, mode):
    """Set KV to mode ('0'/'1'/'2'), or delete the line when mode is None"""
    kv = TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV
    if mode is None:
        duthost.shell(
            f"sudo sed -i -e '/^{kv}=/d' {_TRIM_TRAILING_BLANK_LINES_SED} {sai_profile_path}")
        logger.info(f"Deleted {kv} line from {sai_profile_path}")
        return

    line = f"{kv}={mode}"
    if get_tx_squelch_kv(duthost, sai_profile_path) is None:
        duthost.shell(
            f"sudo sed -i {_TRIM_TRAILING_BLANK_LINES_SED} -e '$a\\{line}' {sai_profile_path}")
    else:
        duthost.shell(f"sudo sed -i 's/^{kv}=.*/{line}/' {sai_profile_path}")
    logger.info(f"Updated {kv}={mode} in {sai_profile_path}")


def reboot_dut(dut_cli, topology_obj, ports_list, reboot_type=None):
    """Reboot DUT via NGTS and wait for recovery (no config save)"""
    if reboot_type is None:
        reboot_type = MarsConstants.REBOOT_TYPES["reboot"]
    with allure.step("Reboot switch with reboot type: {}".format(reboot_type)):
        logger.info("Reload switch with reboot type: %s", reboot_type)
        dut_cli.general.reboot_reload_flow(r_type=reboot_type, topology_obj=topology_obj, ports_list=ports_list)


def apply_tx_squelch_kv_and_reboot(
        duthost, sai_profile_path, dut_cli, topology_obj, ports_list, mode, allure_step):
    """Write or delete TX squelch KV in sai.profile, then reboot the DUT"""
    with allure.step(allure_step):
        write_tx_squelch_kv(duthost, sai_profile_path, mode)
        if mode is None:
            assert get_tx_squelch_kv(duthost, sai_profile_path) is None, (
                f"Expected {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} to be absent from sai.profile after deletion")
    reboot_dut(dut_cli, topology_obj, ports_list)


def get_all_ports_tx_squelch_modes(duthost, ports, sonic_to_sdk_map):
    """Return TX squelch strings for all ports (topology ports must be in sonic_to_sdk_map)"""
    oid_arg = ",".join(sonic_to_sdk_map[p] for p in ports)

    cmd = f"docker exec syncd bash -c 'sx_api_port_ext_params.py --get --log_port {oid_arg}'"
    output = duthost.shell(cmd)['stdout']

    section = TX_SQUELCH_SECTION_RE.search(output)
    if not section:
        logger.warning("Could not find Tx Squelch table section in batch output")
        return {}
    matches = TX_SQUELCH_DATA_ROW_RE.findall(section.group(0))
    oid_to_squelch = {oid.lower(): val.lower() for oid, val in matches}

    result = {}
    for ethernet in ports:
        sdk_oid = sonic_to_sdk_map[ethernet].lower()
        if sdk_oid in oid_to_squelch:
            result[ethernet] = oid_to_squelch[sdk_oid]

    logger.info("Batch TX squelch query returned %d/%d ports", len(result), len(ports))
    return result


def verify_all_ports_tx_squelch_mode(duthost, ports, expected_mode, sonic_to_sdk_map):
    """Assert all ports match expected TX squelch mode"""
    expected_str = TxSquelchConsts.KV_TO_SQUELCH_STR[expected_mode]

    failures = []
    port_to_squelch = get_all_ports_tx_squelch_modes(duthost, ports, sonic_to_sdk_map)

    for port in ports:
        if port not in port_to_squelch:
            msg = f"{port}: TX squelch value missing from batch query output"
            failures.append(msg)
            logger.error(msg)
            with allure.step(f"MISMATCH: {msg}"):
                pass
            continue

        actual = port_to_squelch[port]
        logger.info("%s (OID %s) → Tx Squelch: %s", port, sonic_to_sdk_map[port], actual)
        if actual != expected_str:
            sdk = sonic_to_sdk_map[port]
            actual_display = TxSquelchConsts.KV_TO_SQUELCH_STR.get(actual, actual)
            msg = f"{port} (SDK {sdk}): expected '{expected_str}', got '{actual_display}'"
            failures.append(msg)
            logger.error("TX squelch mode mismatch — %s", msg)
            with allure.step(f"MISMATCH: {msg}"):
                pass

    assert not failures, "TX squelch mode mismatch on the following ports:\n" + "\n".join(failures)


def verify_default_kv_baseline(
        duthost, sai_profile_path, dut_cli, topology_obj, expected_ports_list, sonic_to_sdk_map):
    """Verify default KV is present, applied after reboot, and reflected on all ports"""
    default_mode = TxSquelchConsts.TX_SQUELCH_MODE_DISABLE

    with allure.step(f"Verify {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} is {default_mode} (default) in sai.profile"):
        current_mode = get_tx_squelch_kv(duthost, sai_profile_path)
        assert current_mode == default_mode, (
            f"Expected {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} to be {default_mode} (default) in sai.profile, "
            f"but found '{current_mode}'. The DUT must be in its default state before running tests.")

    with allure.step("Reboot DUT to verify default KV is applied on all ports"):
        reboot_dut(dut_cli, topology_obj, expected_ports_list)

    with allure.step(
            f"Verify all {len(expected_ports_list)} physical ports report "
            f"SAI_PORT_ATTR_TX_SQUELCH_MODE='{default_mode}'"):
        verify_all_ports_tx_squelch_mode(duthost, expected_ports_list, default_mode, sonic_to_sdk_map)


@pytest.fixture(scope="class")
def tx_squelch_class_context(duthosts, topology_obj, cli_objects):
    """Shared DUT and port context for the TX squelch test class; restores default KV on teardown"""
    with allure.step("Resolve DUT host"):
        duthost = duthosts[0]
        dut_cli = cli_objects.dut
        dut_alias = dut_cli.dut_alias

    with allure.step("Collect DUT ports from topology"):
        expected_ports_list = topology_obj.players_all_ports[dut_alias]
        logger.info("Found %d topology port(s) for %s: %s", len(expected_ports_list), dut_alias, expected_ports_list)

    with allure.step("Build Ethernet -> SDK port mapping"):
        sonic_to_sdk_map, _ = dut_cli.performance.get_sonic_to_sdk_port_mapping()
        assert sonic_to_sdk_map, "Ethernet -> SDK port mapping is empty"
        missing_from_map = [p for p in expected_ports_list if p not in sonic_to_sdk_map]
        assert not missing_from_map, (
            f"Topology port(s) missing from Ethernet->SDK mapping: {missing_from_map}")
        logger.info("Built mapping for %d port(s)", len(sonic_to_sdk_map))

    sai_profile_path = SonicConst.SAI_PROFILE_FILE_PATH.format(
        PLATFORM=duthost.facts['platform'], HWSKU=duthost.facts['hwsku'])

    ctx = SimpleNamespace(
        duthost=duthost,
        dut_alias=dut_alias,
        dut_cli=dut_cli,
        expected_ports_list=expected_ports_list,
        sonic_to_sdk_map=sonic_to_sdk_map,
        sai_profile_path=sai_profile_path)

    with allure.step("Class setup: verify default KV baseline"):
        verify_default_kv_baseline(
            ctx.duthost,
            ctx.sai_profile_path,
            ctx.dut_cli,
            topology_obj,
            ctx.expected_ports_list,
            ctx.sonic_to_sdk_map)

    yield ctx

    apply_tx_squelch_kv_and_reboot(
        ctx.duthost,
        ctx.sai_profile_path,
        ctx.dut_cli,
        topology_obj,
        ctx.expected_ports_list,
        TxSquelchConsts.TX_SQUELCH_MODE_DISABLE,
        f"Class teardown: restore {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} to default")


@pytest.fixture()
def configure_kv_and_reboot(tx_squelch_class_context, request, topology_obj):
    """Write KV and reboot"""
    mode = request.param
    apply_tx_squelch_kv_and_reboot(
        tx_squelch_class_context.duthost,
        tx_squelch_class_context.sai_profile_path,
        tx_squelch_class_context.dut_cli,
        topology_obj,
        tx_squelch_class_context.expected_ports_list,
        mode,
        f"Write {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV}={mode} to sai.profile")
    yield mode


@pytest.fixture()
def delete_kv_and_reboot(tx_squelch_class_context, topology_obj):
    """Remove KV line from sai.profile and reboot the DUT"""
    apply_tx_squelch_kv_and_reboot(
        tx_squelch_class_context.duthost,
        tx_squelch_class_context.sai_profile_path,
        tx_squelch_class_context.dut_cli,
        topology_obj,
        tx_squelch_class_context.expected_ports_list,
        None,
        f"Delete {TxSquelchConsts.SAI_TX_SQUELCH_MODE_KV} line from sai.profile")
