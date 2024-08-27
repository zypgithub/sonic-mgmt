import pytest

from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.Devices.IbDevice import CrocodileSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.general.security.nmx_cert.test_nmx_cert import factory_reset_nmx_cert_checker
from ngts.tests_nvos.general.security.test_ssh_pka.test_ssh_pka import factory_reset_ssh_pka_checker
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tools.test_utils import allure_utils as allure


def factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, last_status_line, machine_type,
                                       not_apply_port, system, init_cluster_status):
    with allure.step('update timezone'):
        update_timezone(system)
    if machine_type != 'MQM9520':
        with allure.step("Validate health status and report"):
            validate_health_status_report(system, last_status_line)
    with allure.step("Verify description has been deleted"):
        validate_port_description(engines.dut, apply_and_save_port, "")
        validate_port_description(engines.dut, just_apply_port, "")
        validate_port_description(engines.dut, not_apply_port, "")
    with allure.step('pre factory reset security checks'):
        post_factory_reset_security_checks()
    with allure.step('Check is Juliet Device'):
        if not isinstance(TestToolkit.devices.dut, JulietSwitch):
            pytest.skip("It's not a Juliet Switch. Skipping NMX configuration")
        else:
            with allure.step("Make sure cluster initial state restored"):
                cluster = Cluster()
                # Enable cluster and validate its enabled.
                state = ClusterTools.check_cluster_state(cluster, output_format=OutputFormat.json)
                assert state == init_cluster_status, f"State is {state} instead of {init_cluster_status}"
                cluster.unset(apply=True)


def set_ports_to_legacy_on_croc(engines, devices):
    if not isinstance(devices.dut, CrocodileSwitch):
        logger.info("Not a crocodile switch... Skipping...")
        return

    # This is WA to switch ports which are connected to CX7 to legacy (ndr) because every port is xdr by default.
    legacy_ports = ['swA1p1', 'swA1p2', 'swA2p1', 'swA2p2']
    with allure.step(f"Setting {legacy_ports} to legacy"):
        for legacy_port in legacy_ports:
            interface = Interface(parent_obj=None, port_name=legacy_port)
            interface.link.connection_mode.set(LinkDetectionConsts.CONNECTION_MODE_NDR, apply=True,
                                               ask_for_confirmation=True).verify_result()


def post_factory_reset_security_checks():
    with allure.step('TPM check'):
        next(factory_reset_tpm_checker)
    with allure.step('GNMI cert check'):
        next(factory_reset_gnmi_checker)
    with allure.step('NMX cert check'):
        next(factory_reset_nmx_cert_checker)
    with allure.step('ssh PKA check'):
        next(factory_reset_ssh_pka_checker)
