"""Offline unit tests for the Gen2 CPO device layer.

Covers DeviceFactory resolution, PortiaCpoCapability attachment and the flat
name projections - no DUT needed (device objects are built locally).

Run offline (no setup) with:
    python -m pytest ngts/tests_nvos/unit_tests/cpo -c ngts/pytest.ini \
        -o filterwarnings=ignore --noconftest
"""

import pytest

from ngts.nvos_tools.Devices.cpo.CpoTopology import (
    CpoCapable,
    CpoTopology,
    is_cpo_capable,
)

PORTIA_CPO_KEY = "N7220_LD - Portia_CPO"
PORTIA_CPO_4ASIC_KEY = "N7220_LD - Portia_CPO_4ASIC"
PORTIA_CPO_SIMX_KEY = "N7220_LD_simx - Portia_CPO"
PORTIA_CPO_SA_KEY = "N7220_LD - Portia_CPO_SA"
PORTIA_PLAIN_HW_KEY = "N7100_LD - Portia"
PORTIA_PLAIN_KEY = "N7170_LD_simx - Portia"
PORTIA_PLAIN_SA_KEY = "N7170_LD_simx - Portia_SA"


def expected_cpo_trunk_ports(asic_amount):
    """Seven used optical groups per ASIC; each exposes eight 200G subports."""
    return [f"sw{sw}p1s{subport}" for sw in range(1, 7 * asic_amount + 1) for subport in range(1, 9)]


@pytest.fixture(autouse=True)
def switch_env_vars(monkeypatch):
    """BaseSwitch.__init__ reads switch credentials from the environment."""
    monkeypatch.setenv("NVU_SWITCH_NEW_PASSWORD", "dummy")
    monkeypatch.setenv("NVU_SWITCH_USER", "dummy")
    monkeypatch.setenv("NVU_SWITCH_PASSWORD", "dummy")


@pytest.fixture
def cpo_switch(switch_env_vars):
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory

    return DeviceFactory.create_device(PORTIA_CPO_KEY)


def test_factory_resolves_cpo_switch(cpo_switch):
    from ngts.nvos_tools.Devices.IbDevice import PortiaCpoSwitch

    assert cpo_switch.__class__ is PortiaCpoSwitch


def test_cpo_topology_matches_asic_amount(cpo_switch):
    """Fully populated production = 2 SWB floors / 8 ASICs / 8 CPOs."""
    assert isinstance(cpo_switch.cpo, CpoTopology)
    assert cpo_switch.cpo.cpo_count == cpo_switch.asic_amount == 8


def test_flat_projections(cpo_switch):
    assert cpo_switch.cpo_list == [f"cpo{n}" for n in range(1, 9)]
    assert cpo_switch.laser_source_list == [f"els{n}" for n in range(1, 9)]
    assert cpo_switch.oe_list == cpo_switch.cpo.oe_names()
    assert len(cpo_switch.oe_list) == 32


def test_cross_floor_boundary(cpo_switch):
    """One NVOS device spans both SWB floors; every projection must run
    contiguously across the ASIC4/ASIC5 floor boundary."""
    assert cpo_switch.cpo_list[3:5] == ["cpo4", "cpo5"]
    assert cpo_switch.laser_source_list[3:5] == ["els4", "els5"]
    assert cpo_switch.oe_list[15:17] == ["oe16", "oe17"]
    assert cpo_switch.cpo.oes_for_cpo("cpo4")[-1] == "oe16"
    assert cpo_switch.cpo.oes_for_cpo("cpo5")[0] == "oe17"
    trunks = cpo_switch.nvl_trunk_ports_list
    assert trunks[4 * 56 - 1: 4 * 56 + 1] == ["sw28p1s8", "sw29p1s1"]
    accesses = cpo_switch.nvl_access_ports_list
    assert accesses[4 * 72 - 1: 4 * 72 + 1] == ["acp288", "acp289"]


def test_els_list_is_not_set(cpo_switch):
    """els_list belongs to Gen1 (Taipan); Gen2 must not define it, otherwise
    Gen1 transceiver tests (e.g. test_show_transceiver_els) would mis-select."""
    assert not hasattr(cpo_switch, "els_list")


def test_single_asic_flavor(switch_env_vars):
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
    from ngts.nvos_tools.Devices.IbDevice import PortiaCpoSA

    switch = DeviceFactory.create_device(PORTIA_CPO_SA_KEY)
    assert switch.__class__ is PortiaCpoSA
    assert switch.cpo.cpo_count == switch.asic_amount == 1
    assert switch.cpo_list == ["cpo1"]
    assert switch.nvl_trunk_ports_list == expected_cpo_trunk_ports(1)
    assert switch.nvl_trunk_ports_list[0] == "sw1p1s1"
    assert switch.nvl_trunk_ports_list[-1] == "sw7p1s8"


@pytest.mark.parametrize("switch_type", [PORTIA_PLAIN_HW_KEY, PORTIA_PLAIN_KEY, PORTIA_PLAIN_SA_KEY])
def test_non_cpo_portia_has_no_cpo_or_trunk_ports(switch_env_vars, switch_type):
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory

    plain = DeviceFactory.create_device(switch_type)
    assert getattr(plain, "cpo", None) is None
    assert plain.nvl_trunk_ports_list == []


def test_plain_portia_hw_and_simx_flavors(switch_env_vars):
    """The real-HW base is the N7100_LD tray (PN 920-9K51W-00L7-GS0); the simx
    flavor overlays SimxDevice and presents the simx-only N7170_LD profile."""
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
    from ngts.nvos_tools.Devices.IbDevice import PortiaSimx, PortiaSwitch

    hw = DeviceFactory.create_device(PORTIA_PLAIN_HW_KEY)
    assert hw.__class__ is PortiaSwitch
    assert hw.is_simx is False
    assert hw.require_mloop_setup is False
    assert hw.show_platform_output["system-type"] == "N7100_LD"
    assert hw.platform_inventory_switch_values["model"].regex.pattern == "920-9K51W-00L7-GS0"

    simx = DeviceFactory.create_device(PORTIA_PLAIN_KEY)
    assert simx.__class__ is PortiaSimx
    assert isinstance(simx, PortiaSwitch)
    assert simx.is_simx is True
    assert simx.require_mloop_setup is True
    assert simx.show_platform_output["system-type"] == "N7170_LD"
    assert hw.asic_amount == simx.asic_amount == 4


def test_nso_and_cpo_flavors_coexist(switch_env_vars):
    """The NSO tray (PortiaSimxNso: 2 ASICs, N7100_LD, non-CPO) and the
    N7220_LD CPO flavors live side by side in the factory - a merge/rebase
    must not drop either family."""
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
    from ngts.nvos_tools.Devices.IbDevice import PortiaCpoSwitch, PortiaSimxNso

    nso = DeviceFactory.create_device("N7100_LD_NSO_simx - Portia")
    assert nso.__class__ is PortiaSimxNso
    assert nso.asic_amount == 2
    assert nso.show_platform_output["system-type"] == "N7100_LD"
    assert not is_cpo_capable(nso)
    assert nso.nvl_trunk_ports_list == []

    cpo = DeviceFactory.create_device(PORTIA_CPO_KEY)
    assert cpo.__class__ is PortiaCpoSwitch
    assert cpo.show_platform_output["system-type"] == "N7220_LD"
    assert is_cpo_capable(cpo)


def test_is_cpo_capable_discriminates(cpo_switch, switch_env_vars):
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory

    plain = DeviceFactory.create_device(PORTIA_PLAIN_KEY)
    assert is_cpo_capable(cpo_switch)
    assert not is_cpo_capable(plain)


def test_depopulated_4asic_flavor(switch_env_vars):
    """De-populated production tray: 1 SWB floor / 4 ASICs / 4 CPOs - real HW."""
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
    from ngts.nvos_tools.Devices.IbDevice import PortiaCpo4Asic

    switch = DeviceFactory.create_device(PORTIA_CPO_4ASIC_KEY)
    assert switch.__class__ is PortiaCpo4Asic
    # narrowing through the CpoCapable protocol makes the dynamic (capability-set)
    # attributes visible to static type checkers as well
    assert isinstance(switch, CpoCapable)
    assert switch.cpo.cpo_count == switch.asic_amount == 4
    assert switch.cpo_list == ["cpo1", "cpo2", "cpo3", "cpo4"]
    assert len(switch.oe_list) == 16
    assert switch.nvl_access_ports_list == [f"acp{n}" for n in range(1, 72 * 4 + 1)]
    assert switch.nvl_trunk_ports_list == expected_cpo_trunk_ports(4)
    assert switch.nvl_trunk_ports_list[-1] == "sw28p1s8"
    assert switch.is_simx is False
    assert switch.require_mloop_setup is False


def test_simx_flavor(switch_env_vars):
    """Simx is a reduced 2-ASIC profile by verification decision (8-ASIC
    simulation is too resource-heavy) - it is not a hardware SKU."""
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory
    from ngts.nvos_tools.Devices.IbDevice import PortiaCpoSimx

    switch = DeviceFactory.create_device(PORTIA_CPO_SIMX_KEY)
    assert switch.__class__ is PortiaCpoSimx
    assert isinstance(switch, CpoCapable)
    assert switch.cpo.cpo_count == switch.asic_amount == 2
    assert switch.cpo_list == ["cpo1", "cpo2"]
    assert switch.laser_source_list == ["els1", "els2"]
    assert len(switch.oe_list) == 8
    assert switch.nvl_access_ports_list == [f"acp{n}" for n in range(1, 72 * 2 + 1)]
    assert switch.nvl_trunk_ports_list == expected_cpo_trunk_ports(2)
    assert switch.nvl_trunk_ports_list[55:57] == ["sw7p1s8", "sw8p1s1"]
    assert switch.nvl_trunk_ports_list[-1] == "sw14p1s8"
    assert switch.is_simx is True
    assert switch.require_mloop_setup is True


def test_port_model(cpo_switch):
    """Per ASIC: 72 acp ports + 56 used CPO trunks; 8 channels are spare."""
    assert cpo_switch.show_platform_output["system-type"] == "N7220_LD"
    assert cpo_switch.nvl_access_ports_list == [f"acp{n}" for n in range(1, 72 * 8 + 1)]
    assert cpo_switch.nvl_trunk_ports_list == expected_cpo_trunk_ports(8)
    assert cpo_switch.nvl_trunk_ports_list[:3] == ["sw1p1s1", "sw1p1s2", "sw1p1s3"]
    assert cpo_switch.nvl_trunk_ports_list[-1] == "sw56p1s8"
    channels = cpo_switch.SW_GROUPS_PER_ASIC * cpo_switch.SW_SUBPORTS_PER_GROUP + cpo_switch.SPARE_CHANNELS_PER_ASIC
    assert channels == cpo_switch.cpo.channels_per_cpo


@pytest.mark.parametrize(
    ("switch_type", "asic_amount"),
    [
        (PORTIA_CPO_KEY, 8),
        (PORTIA_CPO_4ASIC_KEY, 4),
        (PORTIA_CPO_SIMX_KEY, 2),
        (PORTIA_CPO_SA_KEY, 1),
    ],
)
def test_sensor_inventory_scales_with_asic_amount(switch_env_vars, switch_type, asic_amount):
    """Platform environment expectations must follow the profile's ASIC count -
    the 8-ASIC default must not inherit the one-floor 4-ASIC sensor list.
    Non-ASIC PMIC/PDB naming beyond the first floor is interim (see the
    PortiaSwitch._init_temperature TODOs)."""
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory

    switch = DeviceFactory.create_device(switch_type)
    expected_asics = [f"ASIC{n}" for n in range(1, asic_amount + 1)]
    assert [s for s in switch.temperature_sensors if s.startswith("ASIC")] == expected_asics
    for asic in range(1, asic_amount + 1):
        assert any(f"-ASIC{asic}-VDD-Out-1" in s for s in switch.voltage_sensors)
    assert not any(f"-ASIC{asic_amount + 1}-" in s for s in switch.voltage_sensors)


def test_real_device_attributes(cpo_switch):
    """The CPO tray is real HW, not a simx flavor: no mloop setup, and its sw
    scale-out ports are 1-lane NVL7 simplex (200G), not the inherited 400G."""
    assert cpo_switch.is_simx is False
    assert cpo_switch.require_mloop_setup is False
    assert cpo_switch.nvl_trunk_port_speed == "200G"
