import re
from collections.abc import Iterable, Mapping

from ngts.nvos_constants.constants_nvos import Cpov2Consts, HealthConsts
from ngts.nvos_tools.Devices.cpo.CpoTopology import CpoTopology
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.platform.Cpo import Cpo


CPO_SUMMARY_FIELDS = (
    Cpov2Consts.FW_VERSION,
    Cpov2Consts.ASSOCIATED_PORTS,
    Cpov2Consts.ASSOCIATED_LASER_SOURCES,
    Cpov2Consts.ASSOCIATED_OPTICAL_ENGINES,
)
CPO_DETAIL_FIELDS = (
    Cpov2Consts.STATUS,
    Cpov2Consts.ERROR_STATUS,
    Cpov2Consts.IDENTIFIER,
    Cpov2Consts.FW_VERSION,
    Cpov2Consts.ASSOCIATED_PORTS,
    Cpov2Consts.ASSOCIATED_LASER_SOURCES,
    Cpov2Consts.ASSOCIATED_OPTICAL_ENGINES,
    Cpov2Consts.THRESHOLDS,
    Cpov2Consts.OE,
    Cpov2Consts.CHANNEL,
)
CPO_THRESHOLD_FIELDS = (
    Cpov2Consts.RX_POWER_HIGH,
    Cpov2Consts.RX_POWER_LOW,
    Cpov2Consts.TX_POWER_HIGH,
    Cpov2Consts.TX_POWER_LOW,
)
OE_FIELDS = (
    Cpov2Consts.IDENTIFIER,
    Cpov2Consts.OE_SERIAL_NUMBER,
    Cpov2Consts.OE_TEMPERATURE,
)
CHANNEL_FIELDS = (
    Cpov2Consts.CH_RX_POWER,
    Cpov2Consts.CH_TX_POWER,
    Cpov2Consts.CH_RX_LOS,
    Cpov2Consts.CH_TX_LOS,
    Cpov2Consts.CH_TX_FAULT,
    Cpov2Consts.CH_LASER_SOURCE_INPUT_POWER,
    Cpov2Consts.CH_FAULT_OPCODE,
    Cpov2Consts.CH_DP_STATE,
)
POWER_FIELDS = (Cpov2Consts.POWER, Cpov2Consts.ALARM, Cpov2Consts.ALARM_SEVERITY)
LASER_SOURCE_SUMMARY_FIELDS = (
    Cpov2Consts.IDENTIFIER,
    Cpov2Consts.ELS_VENDOR_NAME,
    Cpov2Consts.ELS_VENDOR_PN,
    Cpov2Consts.ELS_VENDOR_SN,
    Cpov2Consts.ELS_VENDOR_REV,
    Cpov2Consts.FW_VERSION,
)
LASER_SOURCE_DETAIL_FIELDS = (
    Cpov2Consts.DIAGNOSTICS_STATUS,
    Cpov2Consts.STATUS,
    Cpov2Consts.ERROR_STATUS,
    Cpov2Consts.ELS_VENDOR_DATE_CODE,
    Cpov2Consts.IDENTIFIER,
    Cpov2Consts.ELS_VENDOR_NAME,
    Cpov2Consts.ELS_VENDOR_REV,
    Cpov2Consts.ELS_VENDOR_PN,
    Cpov2Consts.ELS_VENDOR_SN,
    Cpov2Consts.FW_VERSION,
    Cpov2Consts.PARENT,
    Cpov2Consts.TEMPERATURE,
    Cpov2Consts.ELS_POWER_CONSUMPTION,
    Cpov2Consts.ELS_ICC_CURRENT,
    Cpov2Consts.THRESHOLD,
    Cpov2Consts.LASER,
)
LASER_SOURCE_THRESHOLD_FIELDS = (Cpov2Consts.TX_POWER_UPPER, Cpov2Consts.TX_POWER_LOWER)
LASER_FIELDS = (
    Cpov2Consts.LASER_ENABLED,
    Cpov2Consts.LASER_OPER_STATUS,
    Cpov2Consts.LASER_ERROR_STATUS,
    Cpov2Consts.LASER_RAMPING_STATUS,
    Cpov2Consts.LASER_POWER_RESTRICTION,
    Cpov2Consts.LASER_AGE,
    Cpov2Consts.LASER_TARGET_OUTPUT_POWER,
    Cpov2Consts.LASER_MPD_CURRENT,
    Cpov2Consts.LASER_BIAS_CURRENT,
    Cpov2Consts.LASER_TEC_CURRENT,
    Cpov2Consts.LASER_TEC_VOLTAGE,
    Cpov2Consts.LASER_TEMPERATURE,
    Cpov2Consts.LASER_HEALTH,
    Cpov2Consts.TEC_HEALTH,
    Cpov2Consts.FREQUENCY_ERROR,
    Cpov2Consts.LASER_TX_POWER,
)
INTERFACE_CPO_FIELDS = CPO_DETAIL_FIELDS + (Cpov2Consts.PARENT,)
_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


def assert_fields(data: Mapping, fields: Iterable[str], context: str) -> None:
    missing = set(fields) - data.keys()
    assert not missing, f"{context} missing fields: {sorted(missing)}"


def assert_same_shape(actual: Mapping, expected: Mapping, context: str) -> None:
    assert set(actual) == set(expected), f"{context} fields differ from parent subtree"


def sample_names(names: Iterable[str]) -> list[str]:
    values = list(names)
    assert values, "cannot sample an empty collection"
    return list(dict.fromkeys((values[0], values[len(values) // 2], values[-1])))


def unwrap_instance(data: dict, instance: str) -> dict:
    nested = data.get(instance)
    return nested if isinstance(nested, dict) else data


def _assert_named_entries(
    actual: Mapping, expected: Iterable[str], context: str
) -> None:
    expected_names = set(expected)
    assert set(actual) == expected_names, (
        f"{context} instances differ: expected {sorted(expected_names)}, got {sorted(actual)}"
    )


def _number(value: object) -> float:
    match = _NUMBER_PATTERN.search(str(value))
    assert match, f"value has no numeric part: {value!r}"
    return float(match.group())


def _assert_threshold_order(
    thresholds: Mapping, fields: Iterable[str], context: str
) -> None:
    assert_fields(thresholds, (Cpov2Consts.WARNING, Cpov2Consts.ALARM), context)
    for field in fields:
        warning = _number(thresholds[Cpov2Consts.WARNING][field])
        alarm = _number(thresholds[Cpov2Consts.ALARM][field])
        if field.endswith(("low", "lower")):
            assert alarm <= warning, (
                f"{context} {field}: alarm {alarm} > warning {warning}"
            )
        else:
            assert alarm >= warning, (
                f"{context} {field}: alarm {alarm} < warning {warning}"
            )


def validate_cpo_summary(summary: Mapping, topology: CpoTopology) -> None:
    _assert_named_entries(summary, topology.cpo_names(), "CPO summary")
    for cpo, data in summary.items():
        assert_fields(data, CPO_SUMMARY_FIELDS, cpo)


def validate_cpo_detail(cpo: str, detail: Mapping, topology: CpoTopology) -> None:
    assert_fields(detail, CPO_DETAIL_FIELDS, cpo)
    assert set(Cpo.split_names(detail[Cpov2Consts.ASSOCIATED_OPTICAL_ENGINES])) == set(
        topology.oes_for_cpo(cpo)
    )
    assert set(Cpo.split_names(detail[Cpov2Consts.ASSOCIATED_LASER_SOURCES])) == set(
        topology.els_for_cpo(cpo)
    )
    _assert_named_entries(
        detail[Cpov2Consts.OE], topology.oes_for_cpo(cpo), f"{cpo} OEs"
    )
    _assert_named_entries(
        detail[Cpov2Consts.CHANNEL], topology.channels_for_cpo(cpo), f"{cpo} channels"
    )
    for oe, data in detail[Cpov2Consts.OE].items():
        assert_fields(data, OE_FIELDS, f"{cpo}/{oe}")
    for channel, data in detail[Cpov2Consts.CHANNEL].items():
        assert_fields(data, CHANNEL_FIELDS, f"{cpo}/{channel}")
        for field in (Cpov2Consts.CH_RX_POWER, Cpov2Consts.CH_TX_POWER):
            assert_fields(data[field], POWER_FIELDS, f"{cpo}/{channel}/{field}")
    thresholds = detail[Cpov2Consts.THRESHOLDS]
    for severity in (Cpov2Consts.WARNING, Cpov2Consts.ALARM):
        assert_fields(thresholds[severity], CPO_THRESHOLD_FIELDS, f"{cpo}/{severity}")
    _assert_threshold_order(thresholds, CPO_THRESHOLD_FIELDS, f"{cpo} thresholds")


def validate_laser_source_summary(summary: Mapping, topology: CpoTopology) -> None:
    _assert_named_entries(summary, topology.els_names(), "laser-source summary")
    for els, data in summary.items():
        assert_fields(data, LASER_SOURCE_SUMMARY_FIELDS, els)


def validate_laser_source_detail(
    els: str, detail: Mapping, topology: CpoTopology
) -> None:
    assert_fields(detail, LASER_SOURCE_DETAIL_FIELDS, els)
    assert detail[Cpov2Consts.PARENT] == topology.cpo_for_els(els)
    _assert_named_entries(
        detail[Cpov2Consts.LASER], topology.lasers_for_els(els), f"{els} lasers"
    )
    for laser, data in detail[Cpov2Consts.LASER].items():
        assert_fields(data, LASER_FIELDS, f"{els}/{laser}")
        assert_fields(
            data[Cpov2Consts.LASER_TX_POWER], POWER_FIELDS, f"{els}/{laser}/tx-power"
        )
    thresholds = detail[Cpov2Consts.THRESHOLD]
    for severity in (Cpov2Consts.WARNING, Cpov2Consts.ALARM):
        assert_fields(
            thresholds[severity], LASER_SOURCE_THRESHOLD_FIELDS, f"{els}/{severity}"
        )
    _assert_threshold_order(
        thresholds, LASER_SOURCE_THRESHOLD_FIELDS, f"{els} thresholds"
    )


def validate_interface_cpo(port: str, detail: Mapping, cpo_detail: Mapping) -> str:
    assert_fields(detail, INTERFACE_CPO_FIELDS, port)
    parent = detail[Cpov2Consts.PARENT]
    assert port in Cpo.split_names(cpo_detail[Cpov2Consts.ASSOCIATED_PORTS])
    for subtree in (Cpov2Consts.OE, Cpov2Consts.CHANNEL):
        assert set(detail[subtree]) <= set(cpo_detail[subtree]), (
            f"{port} {subtree} is not a subset of {parent}"
        )
        for name, entry in detail[subtree].items():
            assert_same_shape(
                entry, cpo_detail[subtree][name], f"{port}/{subtree}/{name}"
            )
    return parent


def read_interface_cpo(port: str, engine) -> dict:
    return Interface(parent_obj=None, port_name=port).cpo.parse_show(dut_engine=engine)


def validate_healthy_instances(
    component: str, data: Mapping, expected: Iterable[str]
) -> None:
    instances = data[component][HealthConsts.Component.INSTANCE]
    _assert_named_entries(instances, expected, f"health {component}")
    for instance, health in instances.items():
        assert health[HealthConsts.Component.STATE] == HealthConsts.Component.HEALTHY
        assert int(health[HealthConsts.Component.UNHEALTHY_COUNT]) == 0, (
            f"{component}/{instance} has a non-zero unhealthy count"
        )
