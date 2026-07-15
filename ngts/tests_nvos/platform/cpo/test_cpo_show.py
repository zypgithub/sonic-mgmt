import re
import time

import pytest

from ngts.nvos_constants.constants_nvos import Cpov2Consts, HealthConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.platform.Cpo import Cpo
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.platform.cpo.helpers import (
    assert_same_shape,
    read_interface_cpo,
    sample_names,
    unwrap_instance,
    validate_cpo_detail,
    validate_cpo_summary,
    validate_healthy_instances,
    validate_interface_cpo,
    validate_laser_source_detail,
    validate_laser_source_summary,
)


TELEMETRY_REFRESH_WAIT_SECONDS = 11
LEGACY_CPO_INSTANCE_PATTERN = re.compile(r"^(?:cpo|els|oe)\d+$", re.IGNORECASE)


def _read_cpo_details(platform: Platform, topology, engine) -> dict[str, dict]:
    return {
        cpo: unwrap_instance(
            platform.cpo.cpo_id[cpo].parse_show(dut_engine=engine), cpo
        )
        for cpo in topology.cpo_names()
    }


def _read_laser_source_details(platform: Platform, topology, engine) -> dict[str, dict]:
    return {
        els: unwrap_instance(
            platform.laser_source.els_id[els].parse_show(dut_engine=engine), els
        )
        for els in topology.els_names()
    }


@pytest.mark.platform
@pytest.mark.cpov2
def test_cpo_show_platform(engines, devices, random_api):
    topology = devices.dut.cpo
    platform = Platform()
    summary = platform.cpo.parse_show(dut_engine=engines.dut)
    validate_cpo_summary(summary, topology)

    details = _read_cpo_details(platform, topology, engines.dut)
    for cpo, detail in details.items():
        validate_cpo_detail(cpo, detail, topology)
        for oe in topology.oes_for_cpo(cpo):
            drilldown = unwrap_instance(
                platform.cpo.cpo_id[cpo]
                .oe.oe_id[oe]
                .parse_show(dut_engine=engines.dut),
                oe,
            )
            assert_same_shape(drilldown, detail[Cpov2Consts.OE][oe], f"{cpo}/{oe}")
        for channel in sample_names(topology.channels_for_cpo(cpo)):
            drilldown = unwrap_instance(
                platform.cpo.cpo_id[cpo]
                .channel.channel_id[channel]
                .parse_show(dut_engine=engines.dut),
                channel,
            )
            assert_same_shape(
                drilldown, detail[Cpov2Consts.CHANNEL][channel], f"{cpo}/{channel}"
            )

    transceivers = platform.transceiver.parse_show(dut_engine=engines.dut)
    legacy_objects = {
        name for name in transceivers if LEGACY_CPO_INSTANCE_PATTERN.fullmatch(name)
    }
    assert not legacy_objects, (
        f"Gen1 CPO objects leaked into transceiver output: {legacy_objects}"
    )

    sampled_cpo = topology.cpo_names()[0]
    time.sleep(TELEMETRY_REFRESH_WAIT_SECONDS)
    refreshed = unwrap_instance(
        platform.cpo.cpo_id[sampled_cpo].parse_show(dut_engine=engines.dut), sampled_cpo
    )
    validate_cpo_detail(sampled_cpo, refreshed, topology)


@pytest.mark.platform
@pytest.mark.cpov2
def test_cpo_show_laser_source(engines, devices, random_api):
    topology = devices.dut.cpo
    platform = Platform()
    summary = platform.laser_source.parse_show(dut_engine=engines.dut)
    validate_laser_source_summary(summary, topology)

    for els, detail in _read_laser_source_details(
        platform, topology, engines.dut
    ).items():
        validate_laser_source_detail(els, detail, topology)
        for laser in sample_names(topology.lasers_for_els(els)):
            drilldown = unwrap_instance(
                platform.laser_source.els_id[els]
                .laser.laser_id[laser]
                .parse_show(dut_engine=engines.dut),
                laser,
            )
            assert_same_shape(
                drilldown, detail[Cpov2Consts.LASER][laser], f"{els}/{laser}"
            )


@pytest.mark.platform
@pytest.mark.cpov2
def test_cpo_show_interface(engines, devices, random_api):
    topology = devices.dut.cpo
    platform = Platform()
    cpo_details = _read_cpo_details(platform, topology, engines.dut)
    port = devices.dut.nvl_trunk_ports_list[0]
    detail = read_interface_cpo(port, engines.dut)
    parent = detail[Cpov2Consts.PARENT]
    validate_interface_cpo(port, detail, cpo_details[parent])
    interface = Interface(parent_obj=None, port_name=port)
    for oe in detail[Cpov2Consts.OE]:
        drilldown = unwrap_instance(
            interface.cpo.oe.oe_id[oe].parse_show(dut_engine=engines.dut), oe
        )
        assert_same_shape(drilldown, detail[Cpov2Consts.OE][oe], f"{port}/{oe}")
    for channel in sample_names(detail[Cpov2Consts.CHANNEL]):
        drilldown = unwrap_instance(
            interface.cpo.channel.channel_id[channel].parse_show(
                dut_engine=engines.dut
            ),
            channel,
        )
        assert_same_shape(
            drilldown, detail[Cpov2Consts.CHANNEL][channel], f"{port}/{channel}"
        )

    interfaces = Interface(parent_obj=None).parse_show(dut_engine=engines.dut)
    expected_ports = set(
        devices.dut.nvl_access_ports_list + devices.dut.nvl_trunk_ports_list
    )
    assert expected_ports <= set(interfaces), (
        "CPO device interface inventory is incomplete"
    )

    acp_port = devices.dut.nvl_access_ports_list[0]
    output = Interface(parent_obj=None, port_name=acp_port).cpo.show(
        dut_engine=engines.dut, should_succeed=False
    )
    assert "traceback" not in output.lower(), (
        f"{acp_port} CPO rejection produced a traceback"
    )


@pytest.mark.platform
@pytest.mark.cpov2
def test_cpo_show_health(engines, devices, random_api):
    health = System().health.component.parse_show(dut_engine=engines.dut)
    validate_healthy_instances(HealthConsts.Component.CPO, health, devices.dut.cpo_list)
    validate_healthy_instances(
        HealthConsts.Component.Laser_Source, health, devices.dut.laser_source_list
    )

    transceivers = health[HealthConsts.Component.Transceiver][
        HealthConsts.Component.INSTANCE
    ]
    legacy_objects = {
        name for name in transceivers if LEGACY_CPO_INSTANCE_PATTERN.fullmatch(name)
    }
    assert not legacy_objects, (
        f"Gen1 CPO objects leaked into transceiver health: {legacy_objects}"
    )


@pytest.mark.platform
@pytest.mark.cpov2
def test_cpo_topology_consistency(engines, devices, random_api):
    topology = devices.dut.cpo
    platform = Platform()
    cpo_details = _read_cpo_details(platform, topology, engines.dut)
    laser_details = _read_laser_source_details(platform, topology, engines.dut)

    port_to_cpo = {}
    for cpo, detail in cpo_details.items():
        for port in Cpo.split_names(detail[Cpov2Consts.ASSOCIATED_PORTS]):
            interface_detail = read_interface_cpo(port, engines.dut)
            parent = validate_interface_cpo(port, interface_detail, detail)
            assert parent == cpo, f"{port} reports parent {parent}, expected {cpo}"
            port_to_cpo[port] = parent

    assert set(port_to_cpo) == set(devices.dut.nvl_trunk_ports_list)
    assert not set(port_to_cpo) & set(devices.dut.nvl_access_ports_list)
    for els, detail in laser_details.items():
        validate_laser_source_detail(els, detail, topology)

    result = topology.assert_consistent(
        **Cpo.build_topology_maps(cpo_details, port_to_cpo=port_to_cpo)
    )
    result.verify_result()
