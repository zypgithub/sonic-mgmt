import pytest

from ngts.nvos_constants.constants_nvos import DatabaseConst
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.constants.constants import GnmiConsts
from ngts.tests_nvos.system.gnmi.mapping.helpers import *
from ngts.tests_nvos.system.gnmi.mapping.constants import MAPPINGS_FILE_PATH


@pytest.mark.gnmi
@pytest.mark.system
def test_gnmi_mapping(engines, devices):
    """
    Validate the mapping between the state DB and the GNMI output
    """
    with allure.step("Get GNMI client"):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                            devices.dut.default_username, devices.dut.default_password,
                            verify_tools_installed=True)

    with allure.step("Get mapping file"):
        mapping_output = engines.dut.run_cmd(f"cat {MAPPINGS_FILE_PATH}")

    with allure.step("convert mapping file to grouped dict by DB, then pick test each DB group"):
        groups = build_external_maps_by_db(mapping_output)
        main_groups = {DatabaseConst.STATE_DB_NAME, DatabaseConst.COUNTERS_DB_NAME, DatabaseConst.CONFIG_DB_NAME, DatabaseConst.EVENT_DB_NAME}
        other_group = {}
        for db_name, items in (groups or {}).items():
            if db_name not in main_groups and isinstance(items, dict):
                other_group.update(items)
        groups["OTHER_MAPPINGS"] = other_group
        with allure.independent_step(f"Testing {DatabaseConst.EVENT_DB_NAME} group"):
            event_db_mapping_dict: Dict[str, dict] = groups.get(DatabaseConst.EVENT_DB_NAME, {})
            compare_event_db_mappings(event_db_mapping_dict, client)
        with allure.independent_step(f"Testing OTHER_MAPPINGS group"):
            other_db_mapping_dict: Dict[str, dict] = groups.get("OTHER_MAPPINGS", {})
            assert not other_db_mapping_dict, "Expected empty OTHER_MAPPINGS group, we have not implemented cases yet"
