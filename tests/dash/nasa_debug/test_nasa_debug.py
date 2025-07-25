from itertools import chain
import logging
import os
import pytest
from shlex import quote
from collections.abc import Iterable

from ngts.tools.nasa_debug.nasa_debug_plugin import NASA_DEBUG_ENTITY, NASA_DEBUG_DUMP_DIR, nasa_entity_debug_set
from ngts.tools.nasa_debug.nasa_debug_plugin import get_nasa_entity_debug_enabled, get_nasa_entity_debug_file
from ngts.tools.nasa_debug.nasa_debug_plugin import nasa_debuggability_enable, nasa_debuggability_disable
from ngts.tools.nasa_debug.nasa_debug_plugin import get_file_size
from ngts.constants.constants import PytestConst


logger = logging.getLogger(__name__)
pytestmark = [
    pytest.mark.topology("any")
]

@pytest.fixture(autouse=True)
def nasa_debug_cleanup(dpuhost):

    yield
    # for the debuggability tests, disable the debuggability on the selected DPU
    # this is the cleanup in case the debuggability test failed
    logger.info("Disable/Clean up NASA debuggability after the debuggability tests")
    nasa_debuggability_disable(dpuhost)

# these tests are parametrized by the config record and packet drop, since the CLI commands are very similar
@pytest.mark.nasa_debuggability_tests
@pytest.mark.parametrize("entity", NASA_DEBUG_ENTITY)
def test_nasa_debug_enabled(dpuhost, entity):
    assert not get_nasa_entity_debug_enabled(dpuhost, entity), f"Expected {entity.value.title} to be disabled at the beginning"
    assert get_nasa_entity_debug_file(dpuhost, entity) is None, f"Expected {entity.value.title} debug file to be None at the beginning"
    debug_files = []
    # check enable and double enable
    for _ in range(2):
        # repeat 2 times
        nasa_entity_debug_set(dpuhost, entity, True)
        assert get_nasa_entity_debug_enabled(dpuhost, entity), f"Expected {entity.value.title} to be enabled both times"
        debug_file = get_nasa_entity_debug_file(dpuhost, entity)
        assert debug_file is not None, f"Expected {entity.value.title} debug file to be set"
        debug_files.append(debug_file)
    assert debug_files[0] == debug_files[1], f"Expected {entity.value.title} debug file to be same"

    # Disable the debug
    nasa_entity_debug_set(dpuhost, entity, False)
    assert not get_nasa_entity_debug_enabled(dpuhost, entity), f"Expected {entity.value.title} to be disabled after disabling"
    assert get_nasa_entity_debug_file(dpuhost, entity) is None, f"Expected {entity.value.title} debug file to be None after disabling"

    # check enable after disable
    nasa_entity_debug_set(dpuhost, entity, True)
    assert get_nasa_entity_debug_enabled(dpuhost, entity), f"Expected {entity.value.title} to be enabled"
    debug_file = get_nasa_entity_debug_file(dpuhost, entity)
    assert debug_file is not None and debug_file != debug_files[0], f"Expected {entity.value.title} debug file to be set and different from the previous one"

    # finally disable the NASA debug for the entity
    nasa_entity_debug_set(dpuhost, entity, False)
    assert not get_nasa_entity_debug_enabled(dpuhost, entity), f"Expected {entity.value.title} to be disabled after disabling"
    assert get_nasa_entity_debug_file(dpuhost, entity) is None, f"Expected {entity.value.title} debug file to be None after disabling"

    # finally check for the extra files present along the reported debug files
    debug_dir = os.path.dirname(debug_file)
    # Get the last 2 files from the debug directory, catch any extra empty files, that should not be there
    result = dpuhost.shell(f"ls {quote(debug_dir)}/* | tail -2")
    found_files = result['stdout_lines']
    from infra.tools.redmine.redmine_api import is_redmine_issue_active
    if not is_redmine_issue_active([4545888])[0]:
        assert len(found_files) == 2, f"Expected at least 2 files in the debug directory, but got {len(found_files)}"
        assert found_files[0] == debug_files[0], f"Expected the first file to be the first debug file"
        assert found_files[1] == debug_file, f"Expected the second file to be the debug file after disabling and re-enabling"


@pytest.mark.nasa_debuggability_tests
@pytest.mark.parametrize("entity", NASA_DEBUG_ENTITY)
def test_nasa_debug_disabled(dpuhost, entity):
    # expect the feature to be disabled and remain disabled after disabling
    assert not get_nasa_entity_debug_enabled(dpuhost, entity), "Expected config record to be disabled at the beginning"
    assert get_nasa_entity_debug_file(dpuhost, entity) is None, "Expected config record debug file to be None at the beginning"
    nasa_entity_debug_set(dpuhost, entity, False)
    assert not get_nasa_entity_debug_enabled(dpuhost, entity), "Expected config record to be disabled after disabling"
    assert get_nasa_entity_debug_file(dpuhost, entity) is None, "Expected config record debug file to be None after disabling"


@pytest.fixture(scope="session")
def eni_counter_test_params(request):
    "this fixture will build the test params for the ENI counter test based on the current environment"

    # ENI counter test script
    ENI_COUNTER_TEST_SCRIPT_SELECT = ['dash/test_dash_eni_counter.py', '-k', 'test_outbound_pkt_ca_pa_entry_miss_drop_counter[vxlan-tcp]']

    # options to reuse from the current environment
    READ_OPTIONS = ['--inventory', '--host-pattern','--module-path', '--testbed', '--setup_name', '--testbed_file', '--topology', '--dpu-pattern']
    OTHER_OPTIONS = ['--allow_recover', '--assert', 'plain', '--show-capture=no', '-ra',
                     '--showlocals', '--log-cli-level', 'info', '--skip_sanity', '--dynamic_update_skip_reason', '--disable_loganalyzer', '--strict-markers', '--collect_techsupport=False']

    # build the params for the pytest command
    params = ENI_COUNTER_TEST_SCRIPT_SELECT.copy()
    for option in READ_OPTIONS:
        option_value = request.config.getoption(option)
        # check if the option is iterable and not a string (list for example), join with commas
        if isinstance(option_value, Iterable) and not isinstance(option_value, str):
            option_value = ','.join(map(quote, option_value))
        else:
            option_value  = quote(str(option_value))
        params.append(f'{option}={option_value}')
    params.extend(OTHER_OPTIONS)

    return params

@pytest.fixture(scope="session")
def eni_counter_test_params_debug(eni_counter_test_params):
    """This fixture will add the --nasa_debug option to the ENI counter test params"""
    return eni_counter_test_params + ['--nasa_debug']

def get_host_epoch(dpuhost):
    """This function will return the host epoch"""
    return int(dpuhost.shell(f"date +%s")['stdout'].strip())


def run_external_pytest(params):
    """This function will run the pytest command with the given params
       With the disabled sysdump generation
    """
    env_saved = os.environ.copy()
    os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"
    result = pytest.main(params)
    os.environ = env_saved
    return result


@pytest.mark.nasa_debuggability_tests
def test_nasa_debug_action(dpuhost, eni_counter_test_params):
    """Test the NASA debuggability action, by running the ENI counter test with the NASA debuggability enabled, and checking the debug files
    The test has multiple steps:
    1. Enable NASA debuggability
    2. Building the pytest params to run the ENI counter test with the NASA debuggability enabled
    3. Check the debug files are present and the size is increased
    4. Run the packet analyzer of the dropped packets
    5. Check the packet analyzer output and create a pcap file
    5. Check the pcap file is present
    6. Check the pcap file not empty and created recently
    7. Generate the tech support information and check the debug files are present
    """

    # Enable NASA debuggability
    nasa_debuggability_enable(dpuhost)

    debug_files = {}
    for entity in NASA_DEBUG_ENTITY:
        # confirm the debug is enabled
        assert get_nasa_entity_debug_enabled(dpuhost, entity), \
            f"Expected {entity.value.title} to be enabled"
        # get the debug file name
        debug_file = get_nasa_entity_debug_file(dpuhost, entity)
        assert debug_file is not None, \
            f"Expected {entity.value.title} debug file to be set and different from the previous one"
        # save the file along with the size
        debug_files[entity] = [debug_file, get_file_size(dpuhost, debug_file)]

    # run the ENI counter test with the NASA debuggability enabled
    result = run_external_pytest(eni_counter_test_params)
    if result != pytest.ExitCode.OK:
        logger.warning(f"ENI counter test failed with pytest exit code {result}")
    nasa_debuggability_disable(dpuhost)

    # check the debug files, size must increase from the original
    for entity, (debug_file, original_size) in debug_files.items():
        assert get_file_size(dpuhost, debug_file) > original_size, \
            f"Expected {entity.value.title} debug file size to increase from {original_size}"

    # Run the packet analyzer of the dropped packets
    result = dpuhost.shell(f"docker exec syncd pkt_log_analyzer {quote(debug_files[NASA_DEBUG_ENTITY.PACKET_DROP][0])}")

    # Expecting 1 packet to be dropped due to CA2PA table lookup failed
    dropped_packet_count = 0
    for line in result['stdout_lines']:
        if line.startswith('#Pkt hdr:: reason: '):
            dropped_packet_count += 1
            assert "SDN_DBG_PKT_DROP_REASON_ENCAP_CA2PA_TABLE_LOOKUP_FAILED" in line, f"Expecting the packet to be dropped due to CA2PA table lookup failed, found {line}"
            assert dropped_packet_count == 1, f"Expected 1 packet to be dropped due to CA2PA table lookup failed, found at least{dropped_packet_count}"

    # checking in the pcap file was created
    host_epoch = get_host_epoch(dpuhost)

    # expecting the packet to PCAPNG file
    pcap_filename = f"/tmp/{os.path.basename(debug_files[NASA_DEBUG_ENTITY.PACKET_DROP][0])}"
    result = dpuhost.shell(f"docker exec syncd pkt_log_analyzer {quote(debug_files[NASA_DEBUG_ENTITY.PACKET_DROP][0])} -p {quote(pcap_filename)}")

    result = dpuhost.shell(f"docker exec syncd stat -c %s,%F,%W {quote(pcap_filename)}")

    f_size, f_type, f_ctime = result['stdout'].strip().split(',')
    f_size, f_ctime = int(f_size), int(f_ctime)
    assert f_size > 0, f"Expected generated pcap file size to be greater than 0, got {f_size}"
    assert f_type == "regular file", f"Expected generated pcap regular file, got {f_type}"
    assert f_ctime >= host_epoch, f"Expected generated pcap file creation time to be no earlier than host epoch {host_epoch}, got {f_ctime}"


def get_nasa_debug_dump_files(dpuhost):
    """This function will return the list of the files in the NASA debug dump directories"""
    files_list = dict()
    for entity in NASA_DEBUG_ENTITY:
        files_list[entity] = set(dpuhost.shell(f"ls {quote(NASA_DEBUG_DUMP_DIR)}/{quote(entity.value.config_key)}/*")['stdout_lines'])
    return files_list


@pytest.mark.nasa_debuggability_tests
def test_nasa_debug_tech_support(dpuhost, eni_counter_test_params_debug):
    """This test will run the ENI counter test with the NASA debuggability enabled,
       by CLI option.
       After the test, it will ensure the debug files are created and present in the tech support dump.
    """
    # Get the host epoch
    host_epoch = get_host_epoch(dpuhost)

    # get the list of the files in the NASA debug dump directory
    logger.info(f"Getting the list of the files in the NASA debug dump directory before the test")
    before_files_list = get_nasa_debug_dump_files(dpuhost)

    logger.info(f"Running the ENI counter test with the NASA debuggability enabled: {eni_counter_test_params_debug}")
    # run the test with the NASA debuggability enabled
    result = run_external_pytest(eni_counter_test_params_debug)
    if result != pytest.ExitCode.OK:
        logger.warning(f"ENI counter test failed with pytest exit code {result}")

    # get the new list of the files in the NASA debug dump directory
    logger.info(f"Getting the list of the files in the NASA debug dump directory after the test")
    after_files_list = get_nasa_debug_dump_files(dpuhost)

    # Verify there is exactly one new NASA debug dump file in each folder
    logger.info(f"Verifying there is exactly one new NASA debug dump file in each folder")
    for entity in NASA_DEBUG_ENTITY:
        temp_before_files = before_files_list[entity]
        temp_after_files = after_files_list[entity]
        temp_new_files = temp_after_files - temp_before_files
        assert len(temp_new_files) == 1, f"Expected exactly one new file in {entity.value.title} folder, but got {len(temp_new_files)}: {temp_new_files}"
        new_filename = temp_new_files.pop()
        file_epoch = int(dpuhost.shell(f"stat -c %W {quote(new_filename)}")['stdout'].strip())
        assert file_epoch > host_epoch, "Expecting the nasa debug file to be created recently"

    # Generate the tech support information
    logger.info(f"Generating the tech support information to check the debug files are present")
    result = dpuhost.shell("show techsupport")
    tech_support_file = result['stdout_lines'][-1].strip()
    logger.info(f"Tech support file: {tech_support_file}")

    tech_support_file_basename = os.path.basename(tech_support_file)
    tech_support_file_basename, ext = os.path.splitext(tech_support_file_basename)
    assert ext == ".gz", "Expecting the tech support file to be a .gz file"
    tech_support_file_basename, ext = os.path.splitext(tech_support_file_basename)
    assert ext == ".tar", "Expecting the tech support file to be a .tar.gz file"

    # Check if the debug files are present in the tech support information
    # expecting the tech support file /var/dump/<name>.tar.gz
    # Example: /var/dump/sonic_dump_sonic_20250724_231154.tar.gz
    # containing <name>/log/cfg_record_\*.gz <name>/log/pkt_dump_record_\*.gz
    # Example:  sonic_dump_sonic_20250724_231154/log/cfg_record_\*.gz sonic_dump_sonic_20250724_231154/log/pkt_dump_record_\*.gz
    # The same .gz files as are in the /var/log/bluefield/sdk-dumps/config-record/ and /var/log/bluefield/sdk-dumps/packet-drop/
    logger.info(f"Comparing file lists in the tech support file and in the NASA debug dump directories")
    # Example of listing NASA debug files in the tech support file
    # tar --wildcards --sort=name -tf /var/dump/sonic_dump_sonic_20250724_231154.tar.gz sonic_dump_sonic_20250724_231154/log/cfg_record_\*.gz sonic_dump_sonic_20250724_231154/log/pkt_dump_record_\*.gz
    nasa_debug_files_in_tech_support = dpuhost.shell(f"tar --wildcards -tf {quote(tech_support_file)} "
                                                     f"{quote(tech_support_file_basename)}/log/cfg_record_*.gz "
                                                     f"{quote(tech_support_file_basename)}/log/pkt_dump_record_*.gz")['stdout_lines']

    logger.info(f"NASA debug files in the tech support file: {nasa_debug_files_in_tech_support}")
    # remove the path from the file name and the .gz
    nasa_debug_files_in_tech_support_set = {os.path.splitext(os.path.basename(file))[0] for file in nasa_debug_files_in_tech_support}
    assert len(nasa_debug_files_in_tech_support_set) == len(nasa_debug_files_in_tech_support), \
        f"Expected the same number of files in the tech support file and in the NASA debug dump directories, but got {len(nasa_debug_files_in_tech_support_set)} and {len(nasa_debug_files_in_tech_support)}"
    nasa_debug_files_in_folders_set = {os.path.basename(filename) for filename in chain(*after_files_list.values())}
    assert len(nasa_debug_files_in_folders_set) == sum(map(len, after_files_list.values())), "Expecting only unique files in NASA debug dump directories"
    assert nasa_debug_files_in_tech_support_set == nasa_debug_files_in_folders_set, \
        f"Expected the same files in the tech support file and in the NASA debug dump directories, but got {nasa_debug_files_in_tech_support_set} and {nasa_debug_files_in_folders_set}"
