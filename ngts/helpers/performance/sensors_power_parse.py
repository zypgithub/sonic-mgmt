"""Parse ``sensors`` output for performance power validation.

This module stays free of CLI wrapper imports so NVUE and SONiC paths can share
logic without import cycles (e.g. ``nvue`` → ``sonic`` → ``srv6`` → ``nvue_cli``).
"""

import re

from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.performance_constants import PowerConsts


SPC6_RAIL_LABEL_REGEX = (
    r"\b(?P<label>swb_mps29816_\d+_STRESS_[A-Za-z0-9_]+_rail(?P<rail>\d+))_"
    r"(?P<metric>[VIP]OUT)\s*:"
)


def get_controllers_info_str_list(sensors_output):
    """Split full ``sensors`` text into per-controller blocks (text after each controller id).

    ``re.split(CONTROLLER_REGEX, text)`` yields one leading segment (preamble before the first
    chip name) then one segment per ``re.findall`` chip, in order. We drop the preamble so the
    returned list aligns index-wise with ``re.findall(PowerConsts.CONTROLLER_REGEX, ...)``.
    """
    parts = re.split(PowerConsts.CONTROLLER_REGEX, sensors_output)
    if not parts or len(parts) <= 1:
        raise TestIssue("No controller blocks found in sensors output")
    return parts[1:]


def normalized_i2c_address(controller_name):
    """Return ``0x..`` I2C address from an lm-sensors chip name (``*-i2c-<bus>-<addr>``)."""
    if not controller_name:
        return None
    name = controller_name.strip()
    address_match = re.search(r'-i2c-\d+-([0-9a-fA-F]+)\s*$', name)
    if not address_match:
        return None
    return str(hex(int(address_match.group(1), 16)))


def parse_sensor_line(line):
    """Parse one line of sensor output into ``(channel, value_str, unit_str)`` or ``None``."""
    spc6_rail_match = re.search(
        SPC6_RAIL_LABEL_REGEX + r"\s+(-?\d*\.?\d+)\s+(m?[VAW])\b", line, re.I)
    if spc6_rail_match:
        channel = f"out{spc6_rail_match.group('rail')}"
        value = spc6_rail_match.group(4)
        unit = spc6_rail_match.group(5)
        return channel, value, unit

    # Compact lm-sensors line: ``vout1: 12.0 V`` / ``iin: 500 mA`` / ``pout2: 1.2 W``
    # Group 1: measure prefix (v/i/p), group 2: channel (outN or in),
    # Group 3: numeric value, group 4: unit (V/A/W or mV/mA/mW).
    compact_match = re.search(
        r"([vip])(out\d+|in):\s+(-?\d*\.?\d+)\s+(m?[VAW])", line)
    if compact_match:
        channel = compact_match.group(2)
        value = compact_match.group(3)
        unit = compact_match.group(4)
        if channel == "in":
            # lm-sensors uses ``in`` for the primary rail; power helpers expect ``out1``.
            channel = "out1"
        measure_unit = unit if len(unit) == 1 else unit
        return channel, value, measure_unit

    # Parenthesized voltage line: ``Volt (out1): 1200 mV`` or ``Volt (in): 12.0 V``
    # Group 1: channel (in/out/outN), group 2: value, group 3: unit (V or mV).
    volt_paren = re.search(
        r"Volt\s*\((in|out\d+|out)\):\s+(-?\d*\.?\d+)\s+(m?V)\b", line, re.I)
    if volt_paren:
        channel = volt_paren.group(1).lower()
        value = volt_paren.group(2)
        unit = volt_paren.group(3)
        if channel in ("in", "out"):
            channel = "out1"
        return channel, value, unit

    curr_paren = re.search(
        r"Curr\s*\((in\d+|out\d+|out|in)\):\s+(-?\d*\.?\d+)\s+(m?A)\b", line, re.I)
    if curr_paren:
        channel = curr_paren.group(1).lower()
        value = curr_paren.group(2)
        unit = curr_paren.group(3)
        if channel == 'out':
            channel = 'out1'
        return channel, value, unit

    pwr_paren = re.search(
        r"Pwr\s*\((in\d+|out\d+|out|in)\):\s+(-?\d*\.?\d+)\s+(m?W)\b", line, re.I)
    if pwr_paren:
        channel = pwr_paren.group(1).lower()
        value = pwr_paren.group(2)
        unit = pwr_paren.group(3)
        if channel == 'out':
            channel = 'out1'
        return channel, value, unit

    labeled = re.search(
        r".*?\b(Rail|Curr|Pwr)\s*\((in\d+|out\d+|out|in)\):\s+(-?\d*\.?\d+)\s+(mV|mW|mA|V|A|W)\b",
        line, re.I)
    if labeled:
        metric = labeled.group(1).lower()
        channel = labeled.group(2).lower()
        value = labeled.group(3)
        unit = labeled.group(4)
        if channel == 'out':
            channel = 'out1'
        elif channel == 'in' and metric == 'volt':
            channel = 'out1'
        return channel, value, unit

    return None


def get_sensors_output_key(key, measure_unit):
    """Map parsed channel + unit to dict keys used by power helpers (``vout1``, ``iout1``, …)."""
    unit_lower = measure_unit.lower()
    if unit_lower in ('mv', 'v'):
        return f"v{key}"
    if unit_lower in ('ma', 'a'):
        return f"i{key}"
    if unit_lower in ('mw', 'w'):
        return f"p{key}"
    raise TestIssue(f"Unrecognized measure unit {measure_unit} in sensors output parsing")


def infer_spc6_supply_label(block_text):
    """Map a full ``sensors`` chip block to a supply name matching ``POWER_TH_PER_ASIC`` regexes.

    SPC6 SN5600-class switches expose many ``mp29816-i2c-<bus>-<addr>`` rails; labels live in
    the block text (``ASIC_HVDD``, ``ASIC_VDD_TILE4``, ``DDR PMIC``, …).

    Args:
        block_text: Text chunk for one chip (from ``re.split(CONTROLLER_REGEX, ...)``).

    Returns:
        Canonical supply string used in power tables and threshold regexes.
    """
    text = " ".join(block_text.split())

    if PowerConsts.SPC6_MARKER_DDR_PMIC in text:
        return PowerConsts.SPC6_SUPPLY_DDR_PMIC

    if (PowerConsts.SPC6_MARKER_CPU_PMIC in text
            and PowerConsts.SPC6_MARKER_VDDCR in text):
        return PowerConsts.SPC6_SUPPLY_VCORE_MAIN

    if (re.search(PowerConsts.SPC6_REGEX_ASIC_VDD_MAIN, text)
            and PowerConsts.SPC6_MARKER_TILE not in text):
        return PowerConsts.SPC6_SUPPLY_VCORE_MAIN

    if re.search(PowerConsts.SPC6_REGEX_ASIC_HVDD, text, re.I):
        return PowerConsts.SPC6_SUPPLY_HVDD_TILES

    dvdd_tile_match = re.search(PowerConsts.SPC6_REGEX_ASIC_DVDD_TILE, text)
    if dvdd_tile_match:
        tile = int(dvdd_tile_match.group(1))
        tile_low, tile_high = (tile // 2) * 2, (tile // 2) * 2 + 1
        return PowerConsts.SPC6_SUPPLY_DVDD_TILES_FMT.format(low=tile_low, high=tile_high)

    vdd_tile_match = re.search(PowerConsts.SPC6_REGEX_ASIC_VDD_TILE, text)
    if vdd_tile_match:
        tile = int(vdd_tile_match.group(1))
        tile_low, tile_high = (tile // 2) * 2, (tile // 2) * 2 + 1
        return PowerConsts.SPC6_SUPPLY_VCORE_TILES_FMT.format(low=tile_low, high=tile_high)

    if re.search(PowerConsts.SPC6_REGEX_ASIC_AVDD_TILE, text):
        return PowerConsts.SPC6_SUPPLY_VDDSCC

    if (PowerConsts.SPC6_MARKER_ASIC_HBID in text
            or PowerConsts.SPC6_MARKER_HBID_TILE in text):
        hbid_tile_match = re.search(PowerConsts.SPC6_REGEX_ASIC_HBID_TILE, text)
        if hbid_tile_match:
            tile = int(hbid_tile_match.group(1))
            tile_low, tile_high = (tile // 2) * 2, (tile // 2) * 2 + 1
            return PowerConsts.SPC6_SUPPLY_VCORE_TILES_FMT.format(low=tile_low, high=tile_high)
        return PowerConsts.SPC6_SUPPLY_VCORE_TILES_45

    if (PowerConsts.SPC6_MARKER_ASIC_OSFP in text
            or PowerConsts.SPC6_MARKER_OSFPX in text):
        return PowerConsts.SPC6_SUPPLY_OSFP_PHY

    if re.search(PowerConsts.SPC6_REGEX_PDB, text):
        return PowerConsts.SPC6_SUPPLY_PDB_CONVERTER

    return PowerConsts.SPC6_SUPPLY_MISC_PMIC


def get_spc6_rail_labels_by_channel(block_text):
    """Return SPC6 raw rail labels keyed by ``outN`` channel from one ``sensors`` chip block."""
    labels_by_channel = {}
    for match in re.finditer(SPC6_RAIL_LABEL_REGEX, block_text, re.I):
        channel = f"out{match.group('rail')}"
        labels_by_channel[channel] = match.group('label')
    return labels_by_channel


def build_controllers_info_dicts_list(sensors_output):
    """Return one dict per I2C controller with ``vout*`` / ``iout*`` / ``pout*`` floats."""
    controllers_info_dicts_list = []
    controller_names_list = re.findall(PowerConsts.CONTROLLER_REGEX, sensors_output)
    controllers_info_str_list = get_controllers_info_str_list(sensors_output)
    for idx, controller_info_str in enumerate(controllers_info_str_list):
        controller_name = controller_names_list[idx]
        is_controller_name_vddscc = 'i2c-5-6e' in controller_name
        controller_info_list = controller_info_str.splitlines()
        if controller_info_list:
            controllers_info_dict = {}
            for controller_info in controller_info_list:
                parsed = parse_sensor_line(controller_info)
                if not parsed:
                    continue
                key, value, measure_unit = parsed
                key = get_sensors_output_key(key, measure_unit)
                scale = 'm' in measure_unit.lower()
                val = float(value)
                if is_controller_name_vddscc and '1' in key:
                    controllers_info_dict[key] = val / 1000 if scale else val
                elif not is_controller_name_vddscc:
                    controllers_info_dict[key] = val / 1000 if scale else val
            controllers_info_dicts_list.append(controllers_info_dict)
    return controllers_info_dicts_list
