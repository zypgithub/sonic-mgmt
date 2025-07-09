import pytest
from contextlib import contextmanager
from datetime import datetime
from typing import Union, Iterable, Dict

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import EventConsts
from ngts.nvos_tools.Devices import IbDevice
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
def test_physical_monitor(devices):
    """
    Tests the Physical Monitor feature, which raises a system event in case of a PSC failure. Flow:
    0.  Choose 2 ASICs randomly and make sure their counter is currently at 0 (otherwise the test cannot proceed).
    1.  "Open backdoor" for both ASICs (enables error injection).
    2.  Inject PSC error into one ASIC and make sure a system event is created, specifying this ASIC.
    3.  Inject PSC error to the other ASIC and make sure a system event is created for this ASIC.
    4.  Inject 4 more errors into the first ASIC and make sure another event was created.
    5.  Cleanup: close backdoor.

    Note: event is raised only for the first error and every fifth error (per ASIC).
    Step #3 is crucial because steps 2 and 4 cause identical events to be created, and the system-events mechanism
    ignores a repeated event.
    """
    device: IbDevice = devices.dut
    nv = NvCommand()

    with allure.step("Choose 2 ASICs randomly"):
        asics = RandomizationTool.select_random_asics(device, how_many=2).get_returned_value()
        asic_devices = [device.mst_dev_name[i - 1] for i in asics]

    with allure.step("Make sure PSC event counter is 0 before the test begins"):
        for asic_dev in asic_devices:
            event_counter = get_physical_counter(asic_dev)
            if event_counter > 0:
                raise Exception(f"Cannot test feature because the physical-monitor event counter must be 0 before the test "
                                f"starts, but it's current value for {asic_dev} is {event_counter}")

    with enable_backdoor(asic_devices):
        prepare_and_inject_error(asic_devices[0])
        event = nv.system.events.get_last()
        assert_event(event, asics[0])
        prepare_and_inject_error(asic_devices[1])
        event = nv.system.events.get_last()
        assert_event(event, asics[1])
        for _ in range(4):
            inject_error(asic_devices[0])
        event = nv.system.events.get_last()
        assert_event(event, asics[0])


def run_mcra_commands(mst_device: str, commands: Union[str, Iterable[str]], validate=True) -> str:
    """
    Runs `sudo mcra <mst_device> <cmd>` for each command in the list.
    `commands` can be a string, then it's interpreted as a single command.
    Returns the output of the last command; for write operations it's an empty string and for read operation it's the
    register's value.
    """
    engine: LinuxSshEngine = TestToolkit.engines.dut
    last_output = ''
    if isinstance(commands, str):
        commands = (commands,)
    for command in commands:
        last_output = engine.run_cmd(f"sudo mcra {mst_device} {command}", validate=validate)
    return last_output


def prepare_and_inject_error(mst_device: str) -> None:
    """
    From FW team - the following commands are used for injecting a PSC event:
    mcra /dev/mst/mt54004_pciconf0 0x3ffffffc 0x80000000    # open backdoor
    # prepare register values:
    mcra /dev/mst/mt54004_pciconf0 0x201b50.0 0x4e444247
    mcra /dev/mst/mt54004_pciconf0 0x201b54.0 0xc
    mcra /dev/mst/mt54004_pciconf0 0x201b58.0 0x10000000
    mcra /dev/mst/mt54004_pciconf0 0x201b5c.0 0x000f4c1c
    mcra /dev/mst/mt54004_pciconf0 0x201b60.0 0x200
    # inject:
    mcra /dev/mst/mt54004_pciconf0 0x201f4c 0xa0300001
    """
    with allure.step(f"Preparing error-injection to {mst_device}"):
        run_mcra_commands(mst_device, ("0x201b50.0 0x4e444247", "0x201b54.0 0xc", "0x201b58.0 0x10000000",
                                       "0x201b5c.0 0x000f4c1c", "0x201b60.0 0x200"))
    inject_error(mst_device)


def inject_error(mst_device: str) -> None:
    with allure.step(f"Performing error injection into {mst_device}"):
        run_mcra_commands(mst_device, "0x201f4c 0xa0300001")


@contextmanager
def enable_backdoor(mst_device: Union[str, Iterable[str]]) -> str:
    """Enables error-injection to the given device, then disables it when exiting the context"""
    if isinstance(mst_device, str):
        mst_device = (mst_device, )
    for dev in mst_device:
        with allure.step(f"Enabling error-injection for ASIC {dev}"):
            run_mcra_commands(dev, "0x3ffffffc 0x80000000")
    try:
        yield
    finally:
        with allure.step("Cleanup"):
            for dev in mst_device:
                with allure.step(f"Disabling error-injection for ASIC {dev}"):
                    run_mcra_commands(dev, "0x3ffffffc 0x90000000", validate=False)


def get_physical_counter(mst_device: str) -> int:
    """
    Reads the PSC event counter directly from the ASIC. The counter is initially 0 and increases by 1 after each event
    happens (or is simulated) up to a maximum value of 15, then it stops increasing.
    """
    return int(run_mcra_commands(mst_device, "0x318ffc.4"), base=16)


def assert_event(event: Dict[str, str], asic: int):
    """Asserts that the last system event has the proper message, severity and component (ASIC)"""
    with allure.step(f"Asserting system-event was raised for asic {asic} and validating its content"):
        ValidationTool.validate_fields_values_in_output(*zip(
            (EventConsts.SEVERITY, EventConsts.MAJOR),
            (EventConsts.RESOURCE, f'asic {asic}'),
            (EventConsts.TEXT, "PSC detected failure")
        ), event).verify_result()
        if not is_bug_active(4506815):  # bug in system events: timestamps are UTC instead of local
            event_time = ClockTools.parse_datetime(event[EventConsts.TIME_CREATED])
            assert (datetime.now() - event_time).total_seconds() < 5, (
                f"Current datetime is {datetime.now().isoformat()}, event timestamp doesn't match: {event}"
            )
