import logging
import pytest
from ngts.constants.constants import CliType

EXPECTED_MLNX_VERSION = ["3.10.4206", "3.10.4302"]
EXPECTED_SONIC_VERSION_LIST = ["202311_RC.101-7a2264a36_Internal", "202405_RC.15-1b6cdc9ce_Internal",
                               "202405_RC.54-f4c156aaf_Internal", "202405_RC.55-f4c156aaf_Internal"]

logger = logging.getLogger()


def validate_fanout_version(fanout_engine, fanout_type):
    if fanout_type == CliType.SONIC:
        logger.info("This is a SONiC fanout switch")
        current_version = fanout_engine.run_cmd('show version')
        exp_version_list = EXPECTED_SONIC_VERSION_LIST
    else:
        logger.info("This is an ONYX fanout switch")
        current_version = fanout_engine.run_cmd('show version concise')
        exp_version_list = EXPECTED_MLNX_VERSION
    is_version_expected = False
    for expected_version in exp_version_list:
        if expected_version in current_version:
            is_version_expected = True
            break
    assert is_version_expected, \
        f"Fanout version is not one of the expected version: {exp_version_list}"


@pytest.mark.disable_loganalyzer
def test_verify_fanout_version(topology_obj):
    """
    Checks if the fanout version is correct
    """
    logger.info("Show version concise on the fanout")
    fanout_engine = topology_obj.players['fanout']['engine']
    fanout_engine_type = topology_obj.players['fanout']['attributes'].noga_query_data['attributes']['Topology Conn.'][
        'CLI_TYPE']

    validate_fanout_version(fanout_engine, fanout_engine_type)
