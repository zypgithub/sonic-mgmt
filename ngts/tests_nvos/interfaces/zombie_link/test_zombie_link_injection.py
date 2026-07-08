"""
Functional injection test for tx-bandwidth-loss-monitor (zombie link).

Drives a real BW-loss event end-to-end via ``phy_diag.py`` (PPBMP_BW_LOSS
threshold lowering + PTER FEC-error injection on ``monitor_group=Tx_BW_loss``)
and asserts the NVOS-visible signals on ``nv show interface <port> link
phy detail``:

- ``linkdown-reason-code-local`` first slot == 45 (BW_LOSS_THRESHOLD_EXCEEDED)
- ``linkdown-reason-status-local`` first slot == ``BW_LOSS_THRESHOLD_EXCEEDED``
- ``unintentional-link-down-events`` counter incremented

Skips cleanly when ``phy_diag.py`` isn't deployed on the DUT (so normal
regression runs don't fail) and when the firmware silently rejects the PTER
arm (engineering-FW-only path).

Verified working on Taipan (Quantum3, FW 35.2016.4994-002).
"""

import logging
import pytest
from retry.api import retry_call

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import (
    NvosConsts, PhyDiagConsts, TxBwLossMonitorConsts,
)
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PhyDiagTool import PhyDiagTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

# Retry budget for the FW-side BW-loss detection + NVOS publish.
EVENT_RETRIES = 30
EVENT_RETRY_DELAY_S = 2


def _read_phy_detail(port) -> dict:
    """Read ``nv show interface <port> link phy detail`` as a dict, using the
    same parser path as the rest of the interfaces tests."""
    return OutputParsingTool.parse_show_output_to_dict(
        port.interface.link.phy.detail.show()).get_returned_value()


def _latest_linkdown_signals(port):
    """Return ``(latest_code, latest_status, unintentional_count, detail)``
    from NVOS's ``link phy detail``. First slot of each slash-joined string
    is the most recent link-down event."""
    detail = _read_phy_detail(port)
    splitter = TxBwLossMonitorConsts.NVOS_PHY_DETAIL_PLANE_SPLITTER
    code = detail.get(TxBwLossMonitorConsts.NVOS_PHY_DETAIL_LINKDOWN_CODE_LOCAL,
                      "").split(splitter)[0]
    status = detail.get(TxBwLossMonitorConsts.NVOS_PHY_DETAIL_LINKDOWN_STATUS_LOCAL,
                        "").split(splitter)[0]
    count = int(detail.get(
        TxBwLossMonitorConsts.NVOS_PHY_DETAIL_UNINTENTIONAL_LINK_DOWN, "0"))
    return code, status, count, detail


def _assert_bw_loss_observed(port, baseline_count):
    """Assert NVOS has published a fresh BW-loss event. Raises ``AssertionError``
    while the event hasn't landed yet; ``retry_call`` polls this until it
    succeeds or the retry budget is exhausted."""
    code, status, count, _ = _latest_linkdown_signals(port)
    assert count > baseline_count and code == TxBwLossMonitorConsts.BW_LOSS_DIAG_CODE, \
        (f"waiting for BW-loss event: code={code} "
         f"unintentional={count} (baseline={baseline_count})")
    return code, status, count


@pytest.mark.interface
@pytest.mark.multiplanar
def test_tx_bw_loss_injection_and_link_down(engines, devices):
    """
    End-to-end functional test: drive a real BW-loss event via direct PHY
    register access and verify NVOS publishes it correctly.

    Steps:

    0. **Ensure phy_diag.py is on the DUT** -- if missing,
       :meth:`PhyDiagTool.ensure_deployed` SCPs the canonical phy_package
       from ``/auto/mswg/release/fwshared/phy/utils/phy_tools/...`` (which
       is mounted on the sonic-mgmt host but NOT on the NVOS DUT) to
       ``/tmp/phy_package`` on the DUT. Idempotent. Skips the test only
       when the source NFS path isn't reachable from the sonic-mgmt host.

    1. **Pick a link-up port** -- random selection via
       ``RandomizationTool.select_random_port``; skip if no port is up
       (multi-planar setups may have only some ports wired).

    2. **Resolve the CR-space MST device + local_port** -- the BW-loss
       registers (PPBMC / PPBMP / PTER) aren't reachable via the
       ``pciconf`` MST variant on Quantum3, only via ``pci_cr``.
       ``IbInterfaceTool.get_mst_dev_name`` returns ``pciconf``;
       ``PhyDiagTool.cr_mst_dev_for`` swaps it. ``local_port`` is
       resolved via ``get_local_port_hex``.

    3. **Read baseline NVOS phy detail** -- capture the current value of
       ``unintentional-link-down-events`` so we can assert it increments
       after the injection.

    4. **PPBMC: arm the literal Tx_BW_loss monitor**
       (``monitor_cntl=0x20``). The NVOS-level monitor reads "enabled" by
       default, but the FW-default ``monitor_cntl`` mask (``0x24``) does
       NOT specifically arm the ``Tx_BW_loss`` monitor type. Without this
       step the injection still toggles the link, but the local linkdown
       reason ends up as code 33 (peer reset us) instead of the
       BW-loss-specific code 45.

    5. **PPBMP: lower the BW-loss threshold on the Tx_BW_loss group**
       (``monitor_group=8``, ``bw_loss_threshold=1``, ``time_window=100``,
       ``time_window_w_en=1``). The cap field ``time_window_set_cap`` is
       per-group; only group 8 (``Tx_BW_loss``) is writable on this FW.
       Skips if FW returns ``bad status`` (engineering-FW-only path).

    6. **PTER: clear then arm Effective_BER FEC injection**
       (``error_type_admin=2, ber_mantissa=1, ber_exp=4,
       error_injection_time=0xFFFF``). The clear-first step is required
       on Quantum3 -- a fresh arm without clear gets ``status=2`` from
       the FW. We verify the response shows ``error_type_oper=1``
       (firmware armed); skip if it didn't (engineering-FW-only path).

    7. **Wait for NVOS to publish the BW-loss event** -- ``retry_call``
       polls ``nv show interface <port> link phy detail`` until either
       (a) ``unintentional-link-down-events`` has incremented AND the
       first slot of ``linkdown-reason-code-local`` reads ``"45"``, or
       (b) the retry budget (~60 s) is exhausted.

    8. **Assert NVOS-visible BW-loss signals** -- the first slot of
       ``linkdown-reason-code-local`` must be ``45`` and
       ``linkdown-reason-status-local`` must be
       ``BW_LOSS_THRESHOLD_EXCEEDED`` (uppercase form as NVOS reports).

    Cleanup:
        Stop the PTER injection (``error_type_admin=0``) and wait for the
        port to auto-recover to ``up``. The FW recovers the link on its
        own after a BW-loss event; no admin-up override is needed in the
        normal path. If recovery fails the wait raises -- surfacing the
        real product issue rather than masking it.
    """
    if not PhyDiagTool.ensure_deployed(engines.dut):
        pytest.skip(
            f"phy_diag.py not available at {PhyDiagConsts.PHY_DIAG_BIN} "
            f"and source path {PhyDiagConsts.PHY_DIAG_SOURCE_DIR} is not reachable")

    with allure.step("Select a link-up port"):
        port_res = RandomizationTool.select_random_port(
            requested_ports_state=NvosConsts.LINK_STATE_UP)
        if not port_res.result:
            port_res.result.ignore_result()
            pytest.skip(f"no up port: {port_res.info}")
        port = port_res.get_returned_value()
        port_name = port.name
        logger.info(f"[inject] picked port={port_name}")

    with allure.step("Resolve CR-space MST device + local_port"):
        pciconf = IbInterfaceTool.get_mst_dev_name(engines.dut, port_name=port_name)
        cr_mst = PhyDiagTool.cr_mst_dev_for(pciconf)
        local_port = int(
            IbInterfaceTool.get_local_port_hex(engines.dut, devices.dut, port_name),
            16,
        )
        logger.info(f"[inject] cr_mst={cr_mst} local_port={local_port}")

    with allure.step("Read baseline NVOS phy detail"):
        _, _, baseline_count, _ = _latest_linkdown_signals(port)
        logger.info(f"[inject] baseline unintentional-link-down-events={baseline_count}")

    try:
        # The NVOS-level monitor state is "enabled" by default, but the FW
        # default monitor_cntl mask (0x24) does NOT specifically arm the
        # Tx_BW_loss monitor type. Without the override below the injection
        # still toggles the link, but the linkdown reason ends up as code
        # 33 (peer reset us) instead of the BW-loss-specific code 45.
        with allure.step("PPBMC: arm Tx_BW_loss monitor (monitor_cntl=0x20)"):
            PhyDiagTool.ppbmc_set_monitor_cntl(engines.dut, cr_mst, local_port)

        with allure.step("PPBMP: lower BW-loss threshold on Tx_BW_loss group"):
            out = PhyDiagTool.ppbmp_bw_loss_set_threshold(engines.dut, cr_mst, local_port)
            if "bad status" in out:
                pytest.skip(f"PPBMP write rejected by FW: {out[-200:]}")

        with allure.step("PTER: clear then arm Effective_BER injection"):
            PhyDiagTool.pter_clear(engines.dut, cr_mst, local_port)
            arm_out = PhyDiagTool.pter_arm(engines.dut, cr_mst, local_port)
            if not PhyDiagTool.is_pter_armed(arm_out):
                pytest.skip("PTER did not arm — likely engineering-FW-only path")

        with allure.step("Wait for NVOS to report BW-loss (retry-polled)"):
            code, status, count = retry_call(
                _assert_bw_loss_observed,
                fargs=[port, baseline_count],
                exceptions=AssertionError,
                tries=EVENT_RETRIES,
                delay=EVENT_RETRY_DELAY_S,
            )
            logger.info(f"[inject] event observed: code={code} status={status} count={count}")

        with allure.step("Assert NVOS-visible BW-loss signals"):
            ValidationTool.assert_expected_value(
                TxBwLossMonitorConsts.BW_LOSS_DIAG_CODE, code,
                TxBwLossMonitorConsts.NVOS_PHY_DETAIL_LINKDOWN_CODE_LOCAL)
            ValidationTool.assert_expected_value(
                TxBwLossMonitorConsts.NVOS_LINKDOWN_STATUS_BW_LOSS, status,
                TxBwLossMonitorConsts.NVOS_PHY_DETAIL_LINKDOWN_STATUS_LOCAL)

    finally:
        with allure.step("Cleanup: stop injection, verify port auto-recovered"):
            PhyDiagTool.pter_clear(engines.dut, cr_mst, local_port)

            # The BW-loss event toggles the port; the firmware then auto-
            # recovers it. No admin-up step is needed in the normal path --
            # we just wait for the recovery to complete. If the port doesn't
            # come back up on its own that is a real product issue and the
            # wait_for_port_state failure surfaces it.
            port.interface.wait_for_port_state(
                NvosConsts.LINK_STATE_UP, timeout=60).verify_result()
