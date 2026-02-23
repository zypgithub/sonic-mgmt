"""
CPO Telemetry Verification Tests

Validates read-only telemetry fields under /fae/system/cpo/telemetry
for ELS and OE transceiver types on CPO systems.

Known Bugs (workarounds applied only while the bug is open):
- Redmine #4891144: some ELS fields report "N/A" instead of hex.
- Redmine #4891803: some fields are completely absent from output.
"""
import logging
import random
import re

import pytest

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.platform.constants import TransceiversConsts
from ngts.tools.test_utils import allure_utils as allure

from .cpo_telemetry_consts import CpoTelemetryConsts

logger = logging.getLogger()


# ==================== Helpers ====================

def _get_all_telemetry(fae_system):
    """Fetch and parse telemetry for all transceivers.

    Returns:
        dict: Mapping of transceiver ID to its field dict.
    """
    return OutputParsingTool.parse_json_str_to_dictionary(
        fae_system.cpo.show(CpoTelemetryConsts.TELEMETRY)
    ).get_returned_value()


def _get_transceiver_telemetry(fae_system, transceiver_id):
    """Fetch and parse telemetry for a specific transceiver.

    Args:
        fae_system: FaeSystem component object.
        transceiver_id: Transceiver identifier string (e.g. 'els1').

    Returns:
        dict: Field-name to hex-value mapping.
    """
    return OutputParsingTool.parse_json_str_to_dictionary(
        fae_system.cpo.show(
            f'{CpoTelemetryConsts.TELEMETRY} {transceiver_id}'
        )
    ).get_returned_value()


def _collect_missing_fields(
    expected_fields, telemetry_data, transceiver_id, known_missing=None
):
    """Return error strings for each expected field not found in telemetry.

    Fields whose base family is in *known_missing* produce a warning
    instead of an error when absent.

    Args:
        expected_fields: Iterable of field names to check.
        telemetry_data: Parsed telemetry dict for the transceiver.
        transceiver_id: Transceiver identifier for error messages.
        known_missing: Set of base field families to treat as known-missing
            (Redmine #4891803). Pass ``None`` or empty set to disable.

    Returns:
        list[str]: One error message per missing field, empty if all present.

    Examples:
        Good (all present): ``[] ``
        Bad (field absent): ``["Field 'temperature' missing for els1"]``
    """
    errors = []
    if known_missing is None:
        known_missing = set()
    for field in expected_fields:
        if field in telemetry_data:
            continue
        base_name = re.sub(r'\d+$', '', field)
        if base_name in known_missing:
            logger.warning(
                f"Field '{field}' missing for {transceiver_id} — "
                f"known issue Redmine #4891803"
            )
            continue
        errors.append(f"Field '{field}' missing for {transceiver_id}")
    return errors


def _collect_lane_index_errors(field_family, telemetry_data, transceiver_id):
    """Return error string if a lane-indexed field family has indices beyond 1-8.

    Args:
        field_family: Base field family name (e.g. 'voltage-monitor').
        telemetry_data: Parsed telemetry dict for the transceiver.
        transceiver_id: Transceiver identifier for error messages.

    Returns:
        list[str]: Single error message if extra indices found, else empty.

    Examples:
        Good (lanes 1-8 only): ``[]``
        Bad (lane 9 present): ``["Field family 'voltage-monitor' has unexpected lane indices {9} for els1"]``
    """
    pattern = re.compile(rf'^{re.escape(field_family)}(\d+)$')
    found_indices = set()
    for key in telemetry_data:
        match = pattern.match(key)
        if match:
            found_indices.add(int(match.group(1)))
    expected = set(range(
        CpoTelemetryConsts.FIRST_LANE,
        CpoTelemetryConsts.NUM_LANES + 1,
    ))
    extra = found_indices - expected
    if extra:
        return [
            f"Field family '{field_family}' has unexpected lane indices "
            f"{extra} for {transceiver_id}"
        ]
    return []


def _collect_hex_errors(telemetry_data, transceiver_id, na_fields=None):
    """Return error strings for values that are not valid hex strings.

    Fields in *na_fields* that report "NA" produce a warning instead of
    an error.

    Args:
        telemetry_data: Parsed telemetry dict for the transceiver.
        transceiver_id: Transceiver identifier for error messages.
        na_fields: Set of base field families allowed to report "NA"
            (Redmine #4891144). Pass ``None`` or empty set to disable.

    Returns:
        list[str]: One error message per invalid value, empty if all valid.

    Examples:
        Good (all hex): ``[]``
        Bad (non-hex): ``["Field 'voltage-monitor1' for els1 has non-hex value: not-hex"]``
        Bad (unexpected N/A): ``["Field 'voltage-monitor1' for els1 has unexpected 'NA' value"]``
    """
    errors = []
    hex_re = re.compile(CpoTelemetryConsts.HEX_PATTERN)
    if na_fields is None:
        na_fields = set()
    for field_name, value in telemetry_data.items():
        str_value = str(value)
        if str_value == CpoTelemetryConsts.NA_VALUE:
            base_name = re.sub(r'\d+$', '', field_name)
            if base_name in na_fields:
                logger.warning(
                    f"Field '{field_name}' for {transceiver_id} has value "
                    f"'NA' — known issue Redmine #4891144"
                )
                continue
            errors.append(
                f"Field '{field_name}' for {transceiver_id} "
                f"has unexpected 'NA' value"
            )
        elif not hex_re.match(str_value):
            errors.append(
                f"Field '{field_name}' for {transceiver_id} "
                f"has non-hex value: {value}"
            )
    return errors


def _field_belongs_to_family(field_name, family):
    """Return True if field_name is the family itself or family + lane digits.

    Args:
        field_name: Actual field name from telemetry data.
        family: Base field family name.

    Returns:
        bool: True if the field belongs to the family.

    Examples:
        Good: ``_field_belongs_to_family('voltage-monitor1', 'voltage-monitor') → True``
        Bad:  ``_field_belongs_to_family('voltage-monitor1', 'bias-current-monitor') → False``
    """
    if field_name == family:
        return True
    return (
        field_name.startswith(family) and
        field_name[len(family):].isdigit()
    )


def _collect_forbidden_field_errors(
    telemetry_data, forbidden_families, transceiver_id, label
):
    """Return error strings for forbidden field families found in telemetry.

    Args:
        telemetry_data: Parsed telemetry dict for the transceiver.
        forbidden_families: List of field family names that must not appear.
        transceiver_id: Transceiver identifier for error messages.
        label: Human-readable label for the forbidden set (e.g. 'ELS-only').

    Returns:
        list[str]: One error message per violating family, empty if clean.

    Examples:
        Good (no forbidden found): ``[]``
        Bad (forbidden present): ``["ELS-only field family 'bias-current-monitor' unexpectedly found in oe1: [...]"]``
    """
    errors = []
    for family in forbidden_families:
        violating = [
            k for k in telemetry_data
            if _field_belongs_to_family(k, family)
        ]
        if violating:
            errors.append(
                f"{label} field family '{family}' unexpectedly found in "
                f"{transceiver_id}: {violating}"
            )
    return errors


def _collect_scalar_indexed_errors(
    scalar_fields, telemetry_data, transceiver_id
):
    """Return error strings for scalar fields that have unexpected indexed variants.

    Args:
        scalar_fields: List of scalar field names.
        telemetry_data: Parsed telemetry dict for the transceiver.
        transceiver_id: Transceiver identifier for error messages.

    Returns:
        list[str]: One error message per scalar with indexed variants.

    Examples:
        Good (no indexed variants): ``[]``
        Bad (indexed variant exists): ``["Scalar field 'temperature' has unexpected indexed variants for els1: ['temperature1']"]``
    """
    errors = []
    for scalar in scalar_fields:
        if scalar not in telemetry_data:
            continue
        indexed = [
            k for k in telemetry_data
            if k != scalar and
            k.startswith(scalar) and
            k[len(scalar):].isdigit()
        ]
        if indexed:
            errors.append(
                f"Scalar field '{scalar}' has unexpected indexed variants "
                f"for {transceiver_id}: {indexed}"
            )
    return errors


def _validate_transceiver_telemetry(
    fae_system, transceiver_list, type_filter, type_label,
    lane_indexed_fields, scalar_fields, forbidden_families, forbidden_label,
):
    """Run the full telemetry validation sequence for one transceiver type.

    Steps performed:
    1. Verify all matching transceivers appear in the all-telemetry output.
    2. Pick one at random and fetch its per-transceiver telemetry.
    3. Check that every expected field family is present.
    4. Check lane-indexed fields have indices 1-8 only.
    5. Check scalar fields have no lane-indexed variants.
    6. Validate every value is a hex string.
    7. Compare per-transceiver output with the all-telemetry entry.
    8. Verify no forbidden (other-type-only) fields are present.

    Args:
        fae_system: FaeSystem component object.
        transceiver_list: Full transceiver list from devices.dut.
        type_filter: Substring used to select transceivers of this type.
        type_label: Human-readable type name for messages (e.g. 'ELS').
        lane_indexed_fields: Field families expected with lane suffixes 1-8.
        scalar_fields: Field names expected without lane suffixes.
        forbidden_families: Field families that must NOT appear.
        forbidden_label: Label for the forbidden set (e.g. 'OE-only').

    Raises:
        pytest.skip: If no matching transceivers are found.
        AssertionError: If any validation errors are collected.
    """
    matching = [t for t in transceiver_list if type_filter in t]
    if not matching:
        pytest.skip(f"No {type_label} transceivers found")

    bug_4891803_fields = (
        CpoTelemetryConsts.BUG_4891803_MISSING_FIELDS
        if is_bug_active(4891803) else None
    )
    bug_4891144_fields = (
        CpoTelemetryConsts.BUG_4891144_NA_ELS_FIELDS
        if is_bug_active(4891144) else None
    )

    errors = []

    with allure.step(
        f"Show all telemetry and verify {type_label} transceivers present"
    ):
        all_telemetry = _get_all_telemetry(fae_system)
        for tid in matching:
            if tid not in all_telemetry:
                errors.append(
                    f"{type_label} transceiver '{tid}' not found in "
                    f"telemetry output"
                )

    with allure.step(
        f"Select random {type_label} and show per-transceiver telemetry"
    ):
        selected = random.choice(matching)
        logger.info(f"Selected {type_label} transceiver: {selected}")
        telemetry = _get_transceiver_telemetry(fae_system, selected)

    with allure.step(f"Validate all {type_label} field families present"):
        expected_fields = [
            f'{family}{lane}'
            for family in lane_indexed_fields
            for lane in range(CpoTelemetryConsts.FIRST_LANE,
                              CpoTelemetryConsts.NUM_LANES + 1)
        ] + list(scalar_fields)
        errors.extend(
            _collect_missing_fields(
                expected_fields, telemetry, selected,
                known_missing=bug_4891803_fields,
            )
        )

    with allure.step("Validate lane-indexed fields have indices 1-8 only"):
        for field_family in lane_indexed_fields:
            errors.extend(
                _collect_lane_index_errors(
                    field_family, telemetry, selected
                )
            )

    with allure.step("Validate scalar fields have no lane-indexed variants"):
        errors.extend(_collect_scalar_indexed_errors(
            scalar_fields, telemetry, selected,
        ))

    with allure.step("Validate all values match hex format"):
        errors.extend(
            _collect_hex_errors(telemetry, selected, na_fields=bug_4891144_fields)
        )

    with allure.step(
        "Compare per-transceiver output with all-telemetry entry"
    ):
        if selected in all_telemetry and telemetry != all_telemetry[selected]:
            errors.append(
                f"Per-transceiver output for {selected} differs from "
                f"all-telemetry entry"
            )

    with allure.step(
        f"Verify no {forbidden_label} fields in {type_label} output"
    ):
        errors.extend(_collect_forbidden_field_errors(
            telemetry, forbidden_families, selected, forbidden_label,
        ))

    assert not errors, (
        f"{len(errors)} validation error(s) for {type_label} telemetry:\n" +
        "\n".join(errors)
    )


# ==================== Test Cases ====================

@pytest.mark.fae
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_cpo_telemetry_els(engines, devices, nv_command, random_api):
    """
    TC-001: ELS transceiver telemetry validation.

    Validates all ELS telemetry field families, lane indexing, hex format,
    consistency between all-telemetry and per-transceiver output, and
    absence of OE-only fields.

    Flow:
    1. Show all telemetry, verify all known ELS transceivers present
    2. Randomly select one ELS, show per-transceiver telemetry
    3. Validate all ELS field families present
    4. Validate lane-indexed fields have indices 1-8 only
    5. Validate scalar fields have no lane-indexed variants
    6. Validate all values match hex format
    7. Compare per-transceiver output with all-telemetry entry
    8. Verify no OE-only fields in ELS output
    """
    TestToolkit.tested_api = random_api
    _validate_transceiver_telemetry(
        fae_system=nv_command.fae.system,
        transceiver_list=devices.dut.transceiver_list,
        type_filter=TransceiversConsts.TRANSCEIVERS_ELS,
        type_label="ELS",
        lane_indexed_fields=CpoTelemetryConsts.ELS_LANE_INDEXED_FIELDS,
        scalar_fields=CpoTelemetryConsts.ELS_SCALAR_FIELDS,
        forbidden_families=CpoTelemetryConsts.OE_ONLY_FIELDS,
        forbidden_label="OE-only",
    )


@pytest.mark.fae
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_cpo_telemetry_oe(engines, devices, nv_command, random_api):
    """
    TC-002: OE transceiver telemetry validation.

    Validates all OE telemetry field families, lane indexing, hex format,
    consistency between all-telemetry and per-transceiver output, and
    absence of ELS-only fields.

    Flow:
    1. Show all telemetry, verify all known OE transceivers present
    2. Randomly select one OE, show per-transceiver telemetry
    3. Validate all 5 OE field families present
    4. Validate lane-indexed fields have indices 1-8 only
    5. Validate scalar field (temperature) present without indexed variants
    6. Validate all values match hex format
    7. Compare per-transceiver output with all-telemetry entry
    8. Verify no ELS-only fields in OE output
    """
    TestToolkit.tested_api = random_api
    if is_bug_active(4891803):
        pytest.skip("Redmine #4891803: OE telemetry fields missing")
    _validate_transceiver_telemetry(
        fae_system=nv_command.fae.system,
        transceiver_list=devices.dut.transceiver_list,
        type_filter=TransceiversConsts.TRANSCEIVERS_OE,
        type_label="OE",
        lane_indexed_fields=CpoTelemetryConsts.OE_LANE_INDEXED_FIELDS,
        scalar_fields=CpoTelemetryConsts.OE_SCALAR_FIELDS,
        forbidden_families=CpoTelemetryConsts.ELS_ONLY_FIELDS,
        forbidden_label="ELS-only",
    )


@pytest.mark.fae
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_cpo_telemetry_invalid_inputs(engines, nv_command, random_api):
    """
    TC-004: Error flow — invalid transceiver IDs.

    Verifies that the CLI returns an error for each invalid transceiver ID.

    Flow:
    1. For each invalid ID, show telemetry and verify error returned
    """
    TestToolkit.tested_api = random_api
    fae_system = nv_command.fae.system

    with allure.step("Validate errors for invalid transceiver IDs"):
        for invalid_id in CpoTelemetryConsts.INVALID_TRANSCEIVER_IDS:
            with allure.independent_step(
                f"Verify error for invalid ID: {repr(invalid_id)}"
            ):
                fae_system.cpo.show(
                    f'{CpoTelemetryConsts.TELEMETRY} {invalid_id}',
                    if_returned_value=False,
                ).verify_result(
                    should_succeed=False,
                    expected_value='does not exist',
                )
