"""
Test for running ibdiagnet from the hfnm server (IB host) rather than the DUT.

Validates fabric health by running ibdiagnet diagnostics from the external
host connected to the FNM port, checking PHY info with pemi/pddr registers,
and asserting no errors or warnings in the results.
"""
import pytest
import logging

from ngts.nvos_tools.ib.IbdiagnetServerTool import IbdiagnetServerTool
from ngts.nvos_tools.ib.ibdiagnet_helpers import (
    verify_opensm_running,
    verify_ibdiagnet_no_errors,
    IBDIAGNET_EXPECTED_OUTPUT_FILES,
)
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.fixture
def hfnm_engine(engines):
    """Get the hfnm engine, fail if not available."""
    assert hasattr(engines, 'hfnm') and engines.hfnm, \
        "hfnm engine not found in topology"
    return engines.hfnm


@pytest.fixture(autouse=True)
def ensure_opensm(engines):
    """Ensure OpenSM is running on hfnm before each test."""
    verify_opensm_running(engines)


@pytest.fixture
def ibdiagnet_cleanup(hfnm_engine):
    """Cleanup ibdiagnet output directory after test, even on failure."""
    yield
    IbdiagnetServerTool.cleanup(hfnm_engine)


@pytest.mark.ib
def test_ibdiagnet_server_phy_info(hfnm_engine, ibdiagnet_cleanup):
    """
    Run ibdiagnet from the hfnm server with PHY info and pemi/pddr registers.
    Verify output files are created and no errors or warnings.

    Test flow:
        1. Verify OpenSM is running on hfnm (autouse fixture)
        2. Run ibdiagnet --get_phy_info --enabled_regs pemi,pddr from hfnm
        3. Verify output files are created
        4. Assert no errors or warnings in the summary
    """
    result = IbdiagnetServerTool.run(hfnm_engine, enabled_regs='pemi,pddr')

    with allure.step('Verify ibdiagnet output files were created'):
        actual_files = IbdiagnetServerTool.get_output_files(hfnm_engine, result.output_path)
        ValidationTool.validate_subset_in_superset(
            subset=IBDIAGNET_EXPECTED_OUTPUT_FILES, superset=actual_files
        ).verify_result()

    with allure.step('Verify ibdiagnet summary has no issues'):
        assert result.summary, "ibdiagnet summary table is empty - parsing may have failed"
        verify_ibdiagnet_no_errors(result).verify_result()
