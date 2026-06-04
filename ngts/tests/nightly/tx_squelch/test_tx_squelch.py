import pytest
import logging

from ngts.constants.constants import TxSquelchConsts
from ngts.tests.nightly.tx_squelch.conftest import verify_all_ports_tx_squelch_mode
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure

logger = logging.getLogger(__name__)
allure.logger = logger


class TestTxSquelchKV:
    def verify_tx_squelch_mode(self, tx_squelch_class_context, expected_mode):
        """Assert all physical ports report the expected TX squelch mode"""
        with allure.step(
                f"Verify all {len(tx_squelch_class_context.expected_ports_list)} physical ports report "
                f"SAI_PORT_ATTR_TX_SQUELCH_MODE='{expected_mode}'"):
            verify_all_ports_tx_squelch_mode(
                tx_squelch_class_context.duthost, tx_squelch_class_context.expected_ports_list, expected_mode,
                tx_squelch_class_context.sonic_to_sdk_map)

    @pytest.mark.parametrize("configure_kv_and_reboot", TxSquelchConsts.ALL_TX_SQUELCH_MODES, indirect=True)
    def test_ports_tx_squelch_mode_after_reboot_with_kv(self, tx_squelch_class_context, configure_kv_and_reboot):
        """Verify each configured mode after reboot."""
        self.verify_tx_squelch_mode(tx_squelch_class_context, configure_kv_and_reboot)

    def test_ports_tx_squelch_mode_enable_when_kv_absent(self, tx_squelch_class_context, delete_kv_and_reboot):
        """Verify ENABLE fallback on all ports when KV line is absent from sai.profile"""
        self.verify_tx_squelch_mode(tx_squelch_class_context, TxSquelchConsts.TX_SQUELCH_MODE_ENABLE)
