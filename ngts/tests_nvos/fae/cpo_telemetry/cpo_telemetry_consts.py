"""Constants for CPO telemetry verification tests."""


class CpoTelemetryConsts:
    """Field definitions and test constants for CPO transceiver telemetry."""

    TELEMETRY = 'telemetry'
    HEX_PATTERN = r'^0x[0-9a-fA-F]+$'
    NA_VALUE = 'N/A'
    NUM_LANES = 8
    FIRST_LANE = 1

    # ELS transceiver field families (15 lane-indexed, 9 scalar = 24 total)
    ELS_LANE_INDEXED_FIELDS = [
        'voltage-monitor', 'bias-current-monitor', 'opt-power-monitor',
        'laser-mpd-lane', 'tec-voltag-laser', 'laser-health-lane',
        'tec-health-lane', 'laser-age-lane', 'tec-current-laser',
        'cooled-laser-temperature-lane', 'laser-frequency-error-lane',
        'opt-power-setpoint', 'els-input-power-lane', 'tx-power-lane',
        'rx-power-lane',
    ]

    ELS_SCALAR_FIELDS = [
        'icc-monitor', 'module-power-consumption', 'max-tec-power',
        'laser-status', 'laser-enabled', 'laser-restriction',
        'els-oper-state', 'els-laser-fault-state', 'temperature',
    ]

    # OE transceiver field families (4 lane-indexed, 1 scalar = 5 total)
    OE_LANE_INDEXED_FIELDS = [
        'els-input-power-lane', 'tx-power-lane', 'rx-power-lane',
        'cooled-laser-temperature-lane',
    ]

    OE_SCALAR_FIELDS = ['temperature']

    # Field separation: computed from the primary lists above to avoid drift.
    _ALL_ELS = set(ELS_LANE_INDEXED_FIELDS) | set(ELS_SCALAR_FIELDS)
    _ALL_OE = set(OE_LANE_INDEXED_FIELDS) | set(OE_SCALAR_FIELDS)
    ELS_ONLY_FIELDS = sorted(_ALL_ELS - _ALL_OE)
    OE_ONLY_FIELDS = sorted(_ALL_OE - _ALL_ELS)

    # Redmine #4891144: ELS fields whose values are reported as "NA" due to
    # missing SDK sysfs entries (Extended_Module_Info_16 amBER page).
    BUG_4891144_NA_ELS_FIELDS = {
        'laser-health-lane',
        'module-power-consumption',
        'opt-power-setpoint',
        'tec-health-lane',
        'tec-voltag-laser',
    }

    # Redmine #4891803: Fields completely absent from telemetry output.
    # Affects ELS scalars and OE lane-indexed fields.
    BUG_4891803_MISSING_FIELDS = {
        'laser-enabled',
        'laser-status',
        'laser-restriction',
        'els-oper-state',
        'els-laser-fault-state',
        'tx-power-lane',
        'rx-power-lane',
    }

    INVALID_TRANSCEIVER_IDS = [
        'els999', 'oe999'
    ]
