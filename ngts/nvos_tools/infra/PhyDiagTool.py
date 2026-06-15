"""
Wrapper around the phy team's ``phy_diag.py`` register-access tool.

``phy_diag.py`` exposes a friendlier view of Mellanox PRM registers than bare
``mlxreg``: enum names instead of bit-masks, single-integer fields instead of
exp/mantissa pairs, and — most importantly — surfaces firmware-side status
codes rather than silently no-op'ing.

Used by the zombie-link injection test to drive PPBMC / PPBMP_BW_LOSS / PTER
on Quantum3 and similar Mellanox switching ASICs.
"""

import logging
import os
import re

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import PhyDiagConsts
from ngts.nvos_tools.infra.EngineAdapterTool import EngineAdapterTool
from ngts.nvos_tools.infra.FilesTool import FilesTool

logger = logging.getLogger()


class PhyDiagTool:
    """Wrapper around ``/tmp/phy_package/phy_diag/phy_diag.py``.

    The tool path is configurable via :data:`PhyDiagConsts.PHY_DIAG_BIN`.
    All methods accept the ``-d`` device path the caller resolved — typically
    the CR-space variant (``mt54004_pci_cr<N>``) since several BW-loss
    registers aren't reachable via the ``pciconf`` form on Quantum3.
    """

    @staticmethod
    def _run(engine, cmd, validate=False):
        """Run a phy_diag command on the DUT."""
        return EngineAdapterTool.run_cmd(engine, cmd, validate=validate)

    @staticmethod
    def is_available(engine) -> bool:
        """Return True if phy_diag.py is deployed at the expected path."""
        return FilesTool.file_exists_sudo(engine, PhyDiagConsts.PHY_DIAG_BIN).result

    @staticmethod
    def ensure_deployed(engine) -> bool:
        """Make sure phy_diag.py is present on the DUT, deploying it if not.

        ``/auto/mswg`` (the canonical NFS location) isn't mounted on NVOS
        switches, so when the tool is missing we SCP the package from the
        sonic-mgmt host (where ``/auto/mswg`` IS mounted) to the DUT's
        :data:`PhyDiagConsts.PHY_DIAG_DUT_DIR`. Idempotent: no-op if the
        binary already exists. Returns True on success / False if the
        source dir isn't reachable (caller should skip).
        """
        if PhyDiagTool.is_available(engine):
            return True
        if not os.path.isdir(PhyDiagConsts.PHY_DIAG_SOURCE_DIR):
            logger.warning(
                f"phy_diag source dir not accessible from sonic-mgmt host: "
                f"{PhyDiagConsts.PHY_DIAG_SOURCE_DIR}")
            return False
        logger.info(
            f"Deploying phy_package: {PhyDiagConsts.PHY_DIAG_SOURCE_DIR} -> "
            f"{engine.ip}:{PhyDiagConsts.PHY_DIAG_DUT_DIR}")
        engine.copy_file(
            source_file=PhyDiagConsts.PHY_DIAG_SOURCE_DIR,
            dest_file=os.path.basename(PhyDiagConsts.PHY_DIAG_DUT_DIR),
            file_system=os.path.dirname(PhyDiagConsts.PHY_DIAG_DUT_DIR),
            direction='put',
            recursive=True,
        )
        engine.run_cmd(f"chmod +x {PhyDiagConsts.PHY_DIAG_BIN}", validate=False)
        return PhyDiagTool.is_available(engine)

    @staticmethod
    def cr_mst_dev_for(pciconf_mst_dev: str) -> str:
        """Translate a ``mt5xxxx_pciconf<N>`` path to the CR-space variant.

        Some PRM registers (PPBMC / PPBMP_BW_LOSS / PTER) aren't reachable via
        the ``pciconf`` space on Quantum3 — they only respond on ``pci_cr``.
        """
        return pciconf_mst_dev.replace("pciconf", "pci_cr")

    @staticmethod
    def get(engine, mst_dev: str, reg_name: str, indexes: str):
        """Run ``phy_diag.py r -d <mst> -r <REG> -m get -i <indexes>``."""
        cmd = (
            f"sudo {PhyDiagConsts.PHY_DIAG_BIN} r "
            f"-d {mst_dev} -r {reg_name} -m get -i '{indexes}'"
        )
        return PhyDiagTool._run(engine, cmd)

    @staticmethod
    def set(engine, mst_dev: str, reg_name: str, indexes: str, set_params: str = ""):
        """Run ``phy_diag.py r -d <mst> -r <REG> -m set -i <indexes[,set_params]>``.

        ``set_params`` is appended to ``indexes`` only when non-empty — a
        trailing comma in the ``-i`` payload makes phy_diag reject the call.
        """
        payload = f"{indexes},{set_params}" if set_params else indexes
        cmd = (
            f"sudo {PhyDiagConsts.PHY_DIAG_BIN} r "
            f"-d {mst_dev} -r {reg_name} -m set -i '{payload}'"
        )
        return PhyDiagTool._run(engine, cmd)

    # ------------------------------------------------------------------
    # PPBMC — Port Phy BER Monitor Control
    # ------------------------------------------------------------------

    @staticmethod
    def ppbmc_set_monitor_cntl(engine, mst_dev: str, local_port: int,
                               monitor_cntl: int = None):
        """Set the PPBMC ``monitor_cntl`` bitmask on a port.

        Default value (``0x20``) enables the literal ``Tx_BW_loss`` monitor
        type, which is what classifies a link-down event with the local
        reason code 45 (``BW_LOSS_THRESHOLD_EXCEEDED``). The firmware
        default (``0x24``) enables a wider set of BER monitors but does NOT
        produce the BW-loss-specific local reason code for our injection
        path — without this explicit set the local reason ends up as code
        33 (peer reset us first).
        """
        monitor_cntl = monitor_cntl if monitor_cntl is not None else PhyDiagConsts.PPBMC_MONITOR_CNTL_TX_BW_LOSS
        indexes = (
            f"local_port={local_port},port_type=0,lp_msb=0,pnat=0,"
            f"monitor_e_ctrl_ind=0,monitor_cntl={hex(monitor_cntl)}"
        )
        return PhyDiagTool.set(engine, mst_dev, PhyDiagConsts.REG_PPBMC, indexes)

    # ------------------------------------------------------------------
    # BW-loss monitor — PPBMP_BW_LOSS_MONITOR_PARAMETERS
    # ------------------------------------------------------------------

    @staticmethod
    def ppbmp_bw_loss_set_threshold(engine, mst_dev: str, local_port: int,
                                    monitor_group: int = None,
                                    bw_loss_threshold: int = None,
                                    time_window: int = None):
        """Set the BW-loss threshold for one monitor group on one port.

        Defaults pulled from :class:`PhyDiagConsts` are the "trip-immediately"
        values used by the injection test (Quantum3, ``monitor_group=8`` =
        ``Tx_BW_loss``).
        """
        monitor_group = monitor_group if monitor_group is not None else PhyDiagConsts.PPBMP_MONITOR_GROUP_TX_BW_LOSS
        bw_loss_threshold = bw_loss_threshold if bw_loss_threshold is not None else PhyDiagConsts.PPBMP_BW_LOSS_THRESHOLD_LOW
        time_window = time_window if time_window is not None else PhyDiagConsts.PPBMP_TIME_WINDOW_DEFAULT
        indexes = (
            f"local_port={local_port},monitor_group={monitor_group},"
            f"bw_loss_threshold={bw_loss_threshold},time_window={time_window},"
            f"time_window_w_en={PhyDiagConsts.PPBMP_TIME_WINDOW_W_EN}"
        )
        return PhyDiagTool.set(
            engine, mst_dev, PhyDiagConsts.REG_PPBMP_BW_LOSS, indexes, set_params="")

    @staticmethod
    def ppbmp_bw_loss_get(engine, mst_dev: str, local_port: int,
                          monitor_group: int = None):
        monitor_group = monitor_group if monitor_group is not None else PhyDiagConsts.PPBMP_MONITOR_GROUP_TX_BW_LOSS
        indexes = f"local_port={local_port},monitor_group={monitor_group}"
        return PhyDiagTool.get(
            engine, mst_dev, PhyDiagConsts.REG_PPBMP_BW_LOSS, indexes)

    # ------------------------------------------------------------------
    # PTER — Port Transmit Errors injection
    # ------------------------------------------------------------------

    @staticmethod
    def pter_clear(engine, mst_dev: str, local_port: int):
        """Reset PTER injection (admin=0). Required before re-arming on
        Quantum3 — fresh arm without a clear gets ``status=2`` from FW.
        """
        indexes = f"local_port={local_port},error_type_admin=0"
        return PhyDiagTool.set(
            engine, mst_dev, PhyDiagConsts.REG_PTER_PHY, indexes, set_params="")

    @staticmethod
    def pter_arm(engine, mst_dev: str, local_port: int,
                 error_type_admin: int = None,
                 ber_mantissa: int = None, ber_exp: int = None,
                 error_injection_time: int = None):
        """Arm a PTER FEC-error injection. Defaults match the verified-working
        recipe on Quantum3 (``Effective_BER`` with ``mantissa=1, exp=4``)."""
        error_type_admin = error_type_admin if error_type_admin is not None else PhyDiagConsts.PTER_ERROR_TYPE_EFFECTIVE_BER
        ber_mantissa = ber_mantissa if ber_mantissa is not None else PhyDiagConsts.PTER_BER_MANTISSA_DEFAULT
        ber_exp = ber_exp if ber_exp is not None else PhyDiagConsts.PTER_BER_EXP_DEFAULT
        error_injection_time = error_injection_time if error_injection_time is not None else PhyDiagConsts.PTER_INJECTION_TIME_MAX
        indexes = (
            f"local_port={local_port},error_type_admin={error_type_admin},"
            f"error_injection_time={error_injection_time},"
            f"ber_mantissa={ber_mantissa},ber_exp={ber_exp}"
        )
        return PhyDiagTool.set(
            engine, mst_dev, PhyDiagConsts.REG_PTER_PHY, indexes, set_params="")

    @staticmethod
    def pter_get(engine, mst_dev: str, local_port: int):
        indexes = f"local_port={local_port}"
        return PhyDiagTool.get(
            engine, mst_dev, PhyDiagConsts.REG_PTER_PHY, indexes)

    @staticmethod
    def is_pter_armed(pter_output: str) -> bool:
        """True iff the firmware armed the injection (the ``error_type_oper``
        row in the PTER response table reads ``1``). phy_diag's table widths
        depend on field-name lengths so we match the row via regex rather than
        an exact whitespace literal. An un-armed response (``oper=0``) means
        the FW silently rejected — engineering-FW-only path."""
        return re.search(PhyDiagConsts.PTER_ARMED_REGEX, pter_output) is not None

    # ------------------------------------------------------------------
    # PDDR — Port Diagnostics Database (read-only)
    # ------------------------------------------------------------------

    @staticmethod
    def pddr_link_down_info(engine, mst_dev: str, local_port: int):
        """Read PDDR page 6 (link-down info) for ``local_reason_opcode``
        and friends. Independent of NVOS — used as a hardware-side
        cross-check on the injection's effect."""
        indexes = (
            f"local_port={local_port},"
            f"page_select={PhyDiagConsts.PDDR_PAGE_LINK_DOWN_INFO}"
        )
        return PhyDiagTool.get(
            engine, mst_dev, PhyDiagConsts.REG_PDDR_LINK_DOWN_INFO, indexes)
