"""
System feature verification module for NVOS.

This module provides a framework for creating and running feature checkers
that verify system functionality across different operations. Each checker
is designed to validate a specific feature or functionality of the system.

The checkers are implemented as generator functions with a two-phase execution:
1. Setup phase - configure the system for testing (before the first yield)
2. Verification phase - verify the feature works correctly (after the yield)

The module provides decorators to specify compatibility requirements:
- Device types the checker can run on
- Minimum system version required

Usage:
* Adding a new checker:
    - Create a new function with the @_requires_compatibility decorator
    - Implement the two-phase generator pattern (setup, yield, verification)
    - Add the function to the _CHECKERS list

* Running the checkers:
    ```python
    results_generator = feature_checkers.run_checkers(
        engines=engines,
        devices=devices,
        base=base_package,
        target=target_package
    )

    # Get pre-check results
    pre_check_errors = next(results_generator)

    # Run the operation being tested

    # Get post-check results
    post_check_errors = next(results_generator)
    ```
"""

import functools
import logging
import os
import re
import time
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, Generator, List, Optional, Union

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.ngts_types import DevicesT, EnginesT
from ngts.nvos_constants.constants_nvos import (
    ApiType,
    ClusterApps,
    ClusterConsts,
    RbacConsts,
    SystemConsts,
    TestFlowType,
)
from ngts.nvos_tools.Devices import IbDevice
from ngts.nvos_tools.infra.CrlValidator import CrlValidator
from ngts.nvos_tools.infra.NmxRbacTool import NmxRbacTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.nmx.Apps import ClusterApp
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import get_dut_hostname
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.helpers import (
    get_tmp_revision_number_for_test_only,
)
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.test_api_mtls_spiffe_id import (
    TestSetup,
    setup_test,
)
from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.test_api_mtls_spiffe_id import (
    check_spiffe_positive as check_spiffe_positive_api,
)
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import (
    verify_ca_in_expected_locations,
    verify_cert_in_expected_locations,
)
from ngts.tests_nvos.general.security.certificate.test_cert_cacert_mgmt import (
    setup_cert_mgmt_checker,
)
from ngts.tests_nvos.general.security.crl.helpers import ApiCrlClient, GnmiCrlClient
from ngts.tests_nvos.general.security.gnmi_server.mtls.spiffe_id.test_gnmi_server_spiffe_id import (
    check_spiffe_positive as check_spiffe_positive_gnmi,
)
from ngts.tests_nvos.general.security.helpers import (
    cleanup_certs_for_tests,
    get_test_certs_dir_location,
    setup_certs_for_tests,
)
from ngts.tests_nvos.general.security.mtls.generic_testing.helpers import get_scp_player, verify_ca_configuration, verify_connection
from ngts.tests_nvos.general.security.nmx_cert.helpers import (
    enable_cluster,
    run_manager_hello_request,
    verify_manager_show,
)
from ngts.tests_nvos.general.security.nmx_cert.test_cluster_app_mngr_security import (
    setup_cluster_app_mngr_security_checker,
)
from ngts.tests_nvos.general.security.radius.constants import (
    RadiusConsts,
    RadiusPhysicalServer,
    RadiusVmServer,
)
from ngts.tests_nvos.general.security.radius.radius_test_utils import (
    update_radius_server_auth_type,
)
from ngts.tests_nvos.general.security.rbac.helpers import verify_rbac_classes_in_role
from ngts.tests_nvos.general.security.security_test_tools.constants import (
    AaaConsts,
    AddressingType,
    AuthMedium,
    AuthMode,
    UserRole,
)
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import (
    RemoteAaaType,
)
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import (
    set_local_users,
    verify_auth_mediums,
)
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import (
    update_active_aaa_server,
)
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import (
    UserInfo,
)
from ngts.tests_nvos.general.security.tacacs.constants import TacacsDockerServer1
from ngts.tests_nvos.general.security.tacacs.tacacs_test_utils import (
    update_tacacs_server_auth_mode,
)
from ngts.tests_nvos.general.security.test_aaa_ldap.constants import LdapEncryptionModes
from ngts.tests_nvos.general.security.test_aaa_ldap.ldap_servers_info import (
    LdapServersP3,
)
from ngts.tests_nvos.general.security.test_aaa_ldap.ldap_test_utils import (
    update_ldap_encryption_mode,
)
from ngts.tests_nvos.general.security.test_api_server_security.constants import API_INSTALLED
from ngts.tests_nvos.general.security.test_api_server_security.helpers import cleanup_mtls_test, run_curl_and_verify, setup_mtls_checker
from ngts.tests_nvos.general.security.test_ssh_cert_auth.helpers import (
    SshCertAuthHelper,
    get_random_key_type,
    get_random_principal,
    set_cert_auth,
    set_trusted_ca_key,
    verify_user_login,
)
from ngts.tests_nvos.system.aaa.helpers import create_new_user
from ngts.tests_nvos.system.gnmi.helpers import verify_gnmi_client_tools_installed
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import (
    wait_for_ldap_nvued_restart_workaround,
)
from ngts.tools.test_utils.switch_recovery import generate_strong_password
from ngts.scripts.sonic_deploy.nvos_only_methods import NvosInstallationSteps
from ngts.nvos_tools.infra.InterfaceConfigurationTool import InterfaceConfigurationTool

from .helpers import Result, SystemPackage

logger = logging.getLogger(__name__)
CheckerFn = Callable[..., Generator[None, None, None]]


class Skipped(Exception):
    """
    Skipped checker.
    """

    def __init__(self, reason: str):
        self.reason = reason


def run_checkers(*, engines: EnginesT, devices: DevicesT, base: SystemPackage, target: SystemPackage) -> Generator[List[Result], None, List[Result]]:
    """
        Run the feature checkers.

        Args:
            engines: The engines.
            devices: The devices.
            min_ver: The minimal version of the nvos.

        Returns:
            A generator that yields a list of results.
    """
    errors, checkers = [], []
    errors: List[Result]
    min_ver = _get_min_version(base.nvos, target.nvos)
    max_ver = target.nvos.name if min_ver == base.nvos.name else base.nvos.name
    for checker in _CHECKERS:
        try:
            checker_name = checker.__name__
            if checker_name.startswith('_'):
                checker_name = checker_name[1:]

            with allure.step(f"Running pre-checker: {checker_name}"):
                f = checker(engines=engines, devices=devices, sys_min_ver=min_ver, sys_max_ver=max_ver)
                try:
                    next(f)
                    checkers.append((checker_name, f))
                except Skipped as e:
                    logger.info(f"Skipping checker {checker_name} - {e.reason}")
        except Exception as e:
            logger.error(e)
            errors.append(Result(ok=False, operation=checker_name, error_message=str(e)))

    yield errors

    for checker_name, checker in checkers:
        try:
            with allure.step(f"Running checker: {checker_name}"):
                try:
                    next(checker)
                    logger.info(f"Checker {checker_name} finished")
                except StopIteration:
                    logger.info(f"Checker {checker_name} finished")
        except Exception as e:
            logger.error(e)
            errors.append(Result(ok=False, operation=checker_name, error_message=str(e)))

    yield errors


def _parse_nvos_version(nvos: str) -> float:
    """
        Convert nvos version to int.
        Example: 25.02.2200 -> 22200

        - Remove the product ID (the prefix 25)
        - convert that patch to float
        - convert the minor to int and multiply by 10,000
        - add the patch and the minor
        - as a result 25.02.2423-02 -> 2,002,423.02
    """
    nvos = nvos.replace('nvos-', '').replace('amd64-', '')
    minor, patch = re.search(r'.*?25\.(\d+)\.([^\.]+)', nvos).groups()  # 25.02.2200 -> 02, 2200
    ver = float(patch.replace('-', '.'))  # 2200 -> 22.0
    ver += (int(minor) * 1_000_000)  # 25.02.2200 -> 2,002,200.0
    return ver


def _is_valid_version(checker_minimal_version: Union[str, int], nvos_minimal_version: Union[str, int]) -> bool:
    """
        Check if the nvos version is greater or equal to the checker minimal version.

        Args:
            checker_minimal_version: The minimal version of the checker (that argument is supplied by the decorator).
            nvos_minimal_version: The minimal version of the nvos (the minimal version between the base and target nvos).

        Returns:
            True if the nvos version is greater or equal to the checker minimal version, False otherwise.
    """
    if isinstance(checker_minimal_version, str):
        checker_minimal_version = _parse_nvos_version(checker_minimal_version)
    if isinstance(nvos_minimal_version, str):
        nvos_minimal_version = _parse_nvos_version(nvos_minimal_version)

    return checker_minimal_version <= nvos_minimal_version


def _get_min_version(nvos_ver_1: Optional[Path], nvos_ver_2: Optional[Path]) -> Optional[str]:
    """
    Get the minimum version of two nvos versions.
    """
    if nvos_ver_1 is None:
        return nvos_ver_2.name
    if nvos_ver_2 is None:
        return nvos_ver_1.name

    if _parse_nvos_version(nvos_ver_1.name) <= _parse_nvos_version(nvos_ver_2.name):
        return nvos_ver_1.name
    return nvos_ver_2.name


def _requires_compatibility(*valid_devices: IbDevice, minimal_version: Union[str, int] = 0, maximal_version: Optional[Union[str, int]] = None):
    """
        Decorator to check if the checker is compatible with the devices and the minimal version.

        Args:
            *valid_devices: The valid devices for the checker.
            minimal_version: The minimal version for the checker.
            maximal_version: The maximal version for the checker.
    """
    def decorator(func: CheckerFn) -> CheckerFn:
        """ Wrapper to check if the checker is compatible with the devices and the minimal version. """
        @functools.wraps(func)
        def wrapper(engines: EnginesT, devices: DevicesT, sys_min_ver: str, sys_max_ver: str, *args, **kwargs):
            """ Wrapper to check if the checker is compatible with the devices and the minimal version. """
            valid_min_version = _is_valid_version(minimal_version, sys_min_ver)
            valid_max_version = True
            if maximal_version is not None:
                # if maximal_version is not None, the sys_max_ver is the maximum nvos version, while maximal_version is the checker maximal allowed version
                # We want to run the checker if the checker maximal allowed version is greater than the nvos version, otherwise we don't want to run the checker
                # for example:
                # checker_version(decorator maximal_version) "4100" nvos_version "2500" -> should run (4100 > 2500)
                # checker_version(decorator maximal_version) "4100" nvos_version "4300" -> should not run (4100 < 4300)
                valid_max_version = not _is_valid_version(maximal_version, sys_max_ver)
            valid_device = not valid_devices or isinstance(devices.dut, valid_devices)
            if valid_min_version and valid_device and valid_max_version:
                yield from func(*args, engines=engines, devices=devices, **kwargs)
            else:
                skip_reason = ""
                if not valid_device:
                    skip_reason += f'invalid DUT type {devices.dut} '
                if not valid_min_version:
                    skip_reason += f'minimal version {minimal_version} is not met '
                if not valid_max_version:
                    skip_reason += f'maximal version {maximal_version} is not met '
                raise Skipped(skip_reason)
        return wrapper
    return decorator

# ####################### Example Feature Checkers #######################


@_requires_compatibility(IbDevice.JulietAriel, IbDevice.JulietNonScaleoutSwitchGB300, minimal_version='25.02.2200', maximal_version='25.02.4200')
def _check_some_feature(engines: EnginesT, devices: DevicesT, **kwargs) -> Generator[None, None, None]:
    # XXX Example:
    """
    Checker Requirements:
    - Checker must be decorated with @_requires_compatibility
    - _requires_compatibility should have the valid devices for the feature
    - _requires_compatibility should have the minimal version for the feature
    - _requires_compatibility may have the maximal version for the feature (optional)
    - Checker must have yield statement
    - first part is the setup
    - second part is the test
    - using assert to verify the test is highly recommended
    - add the checker to the _CHECKERS list
    """
    ...  # setup the config actions for the rbac
    yield
    ...  # test rbac functionality
    assert ..., "RBAC test failed ..."

# #################### End of Example Feature Checkers ###################

# ####################### Feature Checkers #######################


@_requires_compatibility(IbDevice.JulietSwitch, minimal_version="25.02.2100", maximal_version="25.02.4100")
def _check_nmx_cert(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    if devices.dut.has_nmx:
        with allure.step("setup"):
            tmp_certs_dir, nmx_certs, encryption_mode = (
                setup_cluster_app_mngr_security_checker(engines)
            )
            certs: Dict[str, CertInfo] = {
                ClusterApps.NMX_CONTROLLER: nmx_certs[0],
                ClusterApps.NMX_TELEMETRY: nmx_certs[1],
            }

    yield  # upgrade to the target nvos

    try:
        if devices.dut.has_nmx:
            with allure.step("verify after upgrade"):
                for app_name in ClusterApps.ALL_APPS:
                    with allure.independent_step(app_name):
                        cert = certs[app_name]
                        with allure.independent_step("Verify values in show kept"):
                            verify_manager_show(
                                app_name,
                                expect_cert=cert.name,
                                expect_cacert=cert.cacert_name,
                                expect_encryption=encryption_mode,
                            )
                        with allure.independent_step(
                            f"verify client connection: client mode: {encryption_mode}. expect success: True"
                        ):
                            run_manager_hello_request(
                                app_name,
                                encryption_mode,
                                cert,
                                cert,
                                cert,
                                cert,
                                skip_etc_mapping=True,
                            ).verify_result()
    finally:
        cleanup_certs_for_tests(tmp_certs_dir, nmx_certs)


@_requires_compatibility(minimal_version="25.02.2100", maximal_version="25.02.4100")
def _check_api_mtls_old(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    with allure.step('setup'):
        tmp_certs_dir, server_cert, server_ca = setup_mtls_checker(engines)
        feature_resource = System().api
        installed_app_name = API_INSTALLED
        verify_connection_func = run_curl_and_verify
        non_matching_client_cert_should_work = True

    yield  # upgrade to the target nvos

    try:
        with allure.step('verify mtls after this factory reset'):
            with allure.independent_step('verify mtls is configured in show'):
                verify_ca_configuration(feature_resource, installed_app_name, server_ca.cacert_name)
            with allure.independent_step('verify mtls only connection'):
                verify_connection(TestFlowType.ALL_TYPES, engines.dut, UserInfo(engines.dut.username, engines.dut.password, 'admin'),
                                  True, server_cert, server_ca, non_matching_client_cert_should_work, verify_connection_func)
    finally:
        cleanup_mtls_test(tmp_certs_dir, [server_cert], [server_ca])


@_requires_compatibility(minimal_version="25.02.2100")
def _check_cert_mgmt(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    security = System().security

    with allure.step("setup"):
        tmp_certs_dir, cert, cas = setup_cert_mgmt_checker(engines)

    yield  # upgrade to the target nvos

    try:
        with allure.step("verify ca/certificates kept"):
            with allure.independent_step("verify cert exist in show"):
                out = OutputParsingTool.parse_json_str_to_dictionary(
                    security.certificate.show()
                ).get_returned_value()
                assert cert.name in out, (
                    f"cert {cert.name} expected to be in output but is not\n{out}"
                )
            with allure.independent_step("verify cas exist"):
                out = OutputParsingTool.parse_json_str_to_dictionary(
                    security.ca_certificate.show()
                ).get_returned_value()
                missing_cas = [
                    ca.ca_info.name for ca in cas if ca.ca_info.name not in out
                ]
                assert not missing_cas, (
                    f"{missing_cas} are missing from ca show output\n{out}"
                )
            with allure.independent_step("verify cert in certs locations"):
                verify_cert_in_expected_locations(cert.name, engines.dut)
            with allure.independent_step("verify cas in expected locations"):
                for ca in cas:
                    with allure.independent_step(ca.ca_info.name):
                        verify_ca_in_expected_locations(
                            ca.ca_info.name, ca.ca_info, engines.dut, ca.external
                        )
    finally:
        with allure.step("cleanup"):
            cleanup_certs_for_tests(tmp_certs_dir, [cert], [ca.ca_info for ca in cas])


@_requires_compatibility(minimal_version="25.02.4200")
def _check_rbac(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    system = System()

    test_class_name = "TestClass"
    test_role_name = "TestRole"
    interface_path = "/interface/"

    with allure.step("Create RBAC class"):
        system.aaa.class_rbac.set_new_class(
            test_class_name, RbacConsts.ALLOW, interface_path, permission="all"
        )

    with allure.step("Create RBAC role"):
        system.aaa.role.set_new_role(test_role_name, test_class_name, apply=True)

    with allure.step("Create user with new role"):
        test_user, test_password = create_new_user(role=test_role_name, apply=True)

    with allure.step("Save configuration"):
        NvueGeneralCli.save_config(engines.dut)

    yield  # upgrade to the target nvos

    with allure.step("Verify after upgrade"):
        with allure.step("Verify RBAC class in show"):
            class_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.aaa.class_rbac.show()
            ).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(
                class_output, test_class_name
            ).verify_result()

        with allure.step("Verify RBAC role in show"):
            role_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.aaa.role.show()
            ).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(
                role_output, test_role_name
            ).verify_result()

        verify_rbac_classes_in_role(system, test_role_name, [test_class_name])

        with allure.step("Verify user does exist or has default permissions"):
            user_output = OutputParsingTool.parse_json_str_to_dictionary(
                system.aaa.user.show()
            ).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(
                user_output, test_user
            ).verify_result()


@_requires_compatibility(minimal_version="25.02.2100")
def _check_sed_password(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    tpm_tool = TpmTool(engines.dut)

    yield  # upgrade to the target nvos

    devices.dut.verify_sed_password(tpm_tool)


@_requires_compatibility(minimal_version="25.02.4200")
def _check_gnmi_mtls_spiffe_id_and_crl(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    scp_player = get_scp_player(engines)
    hostname = get_dut_hostname(engines)
    cert_name_prefix = "gnmi"
    verify_gnmi_client_tools_installed()

    with allure.step("setup"):
        with allure.step("prepare certs, users, spiffes"):
            setup: TestSetup = setup_test(hostname, engines, scp_player, cert_name_prefix=cert_name_prefix)
            client_cert = setup.cert_spif_of_user1_1
            server_cert = setup.server_cert

        with allure.step("prepare mtls"):
            crl_validator = CrlValidator(
                app=GnmiCrlClient(host=hostname, ip=engines.dut.ip)
            )
            crl_validator.prepare_mtls(
                server_certs=[server_cert], client_cas=[client_cert]
            )
            time.sleep(15)  # Wait for gnmi server to be ready

        with allure.step("verify spiffe works before upgrade"):
            check_spiffe_positive_gnmi(engines, setup)

        with allure.step("prepare crl"):
            crl_dest = os.path.dirname(
                os.path.dirname(setup.cert_spif_of_user1_1.public)
            )
            crl_name = "test_crl_gnmi_upgrade"
            crl_path = crl_validator.revoke_cert(
                crl_name=crl_name,
                cert=setup.cert_spif_of_user1_1,
                dest=crl_dest,
                ca_dest=os.path.join(crl_dest, "ca"),
            )

        with allure.step("bind crl"):
            crl_validator.bind_crl(crl_path, crl_name)

        with allure.step("Make request via client application and see it fails"):
            crl_validator.run_client(
                setup.user1,
                expect_success=False,
                client_cert=setup.cert_spif_of_user1_1,
                client_cacert=server_cert,
            )

        with allure.step("save config"):
            NvueGeneralCli.save_config(engines.dut)

    yield  # upgrade to the target nvos

    try:
        with allure.step("Make request via client application and see it fails"):
            crl_validator.run_client(
                setup.user1,
                expect_success=False,
                client_cert=client_cert,
                client_cacert=server_cert,
            )

        crl_validator.unbind_crl()

        with allure.step("Make request via client application and see it succeeds"):
            crl_validator.run_client(
                setup.user1,
                expect_success=True,
                client_cert=client_cert,
                client_cacert=server_cert,
            )

        with allure.step("verify spiffe works after upgrade"):
            check_spiffe_positive_gnmi(engines, setup)
    finally:
        crl_validator.cleanup()


@_requires_compatibility(minimal_version="25.02.4200")
def _check_api_mtls_spiffe_id_and_crl(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    scp_player = get_scp_player(engines)
    hostname = get_dut_hostname(engines)

    with allure.step("setup"):
        with allure.step("prepare certs, users, spiffes"):
            setup: TestSetup = setup_test(hostname, engines, scp_player)
            client_cert = setup.cert_spif_of_user1_1
            server_cert = setup.server_cert

        with allure.step("prepare mtls"):
            crl_validator = CrlValidator(
                app=ApiCrlClient(host=hostname, ip=engines.dut.ip)
            )
            crl_validator.prepare_mtls(
                server_certs=[server_cert], client_cas=[client_cert]
            )

        with allure.step("verify spiffe works before upgrade"):
            with allure.step("take new revision number for testing admin permissions"):
                revision_num = get_tmp_revision_number_for_test_only(
                    CertInfo(
                        "",
                        "",
                        setup.cert_spif_of_user1_1.private,
                        setup.cert_spif_of_user1_1.public,
                        "",
                        "",
                        setup.cert_spif_of_user1_1.ip,
                        setup.cert_spif_of_user1_1.ip,
                        setup.server_cert.cacert,
                    )
                )
            check_spiffe_positive_api(engines, revision_num, setup)

        with allure.step("prepare crl"):
            crl_dest = os.path.dirname(
                os.path.dirname(setup.cert_spif_of_user1_1.public)
            )
            crl_name = "test_crl_api_upgrade"
            crl_path = crl_validator.revoke_cert(
                crl_name=crl_name,
                cert=setup.cert_spif_of_user1_1,
                dest=crl_dest,
                ca_dest=os.path.join(crl_dest, "ca"),
            )

        with allure.step("bind crl"):
            crl_validator.bind_crl(crl_path, crl_name)

        with allure.step("Make request via client application and see it fails"):
            crl_validator.run_client(
                setup.user1,
                expect_success=False,
                client_cert=setup.cert_spif_of_user1_1,
                client_cacert=server_cert,
            )

        with allure.step("save config"):
            NvueGeneralCli.save_config(engines.dut)

    yield  # upgrade to the target nvos

    try:
        with allure.step("Make request via client application and see it fails"):
            crl_validator.run_client(
                setup.user1,
                expect_success=False,
                client_cert=client_cert,
                client_cacert=server_cert,
            )

        crl_validator.unbind_crl()

        with allure.step("verify spiffe works after upgrade"):
            with allure.step("take new revision number for testing admin permissions"):
                revision_num = get_tmp_revision_number_for_test_only(
                    CertInfo(
                        "",
                        "",
                        setup.cert_spif_of_user1_1.private,
                        setup.cert_spif_of_user1_1.public,
                        "",
                        "",
                        setup.cert_spif_of_user1_1.ip,
                        setup.cert_spif_of_user1_1.ip,
                        setup.server_cert.cacert,
                    )
                )
            check_spiffe_positive_api(engines, revision_num, setup)

    finally:
        crl_validator.cleanup()


@_requires_compatibility(IbDevice.JulietSwitch, minimal_version="25.02.4200")
def _check_nmx_controller_rbac(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    """
    Verify RBAC upgrade works as expected
    Test flow:
        1. Enable cluster
        2. Prepare rbac for nmx controller
        3. Run app client with good user - Should succeed
        4. Run app client with bad user - Should fail
        5. Perform upgrade
        6. Run app client with good user - Should succeed
        7. Run app client with bad user - Should fail
        8. Restore rbac file
        9. Run app client with bad user - Should succeed
    """
    cluster = Cluster()
    dut_hostname = engines.dut.ip
    scp_player = get_scp_player(engines)
    verify_gnmi_client_tools_installed()

    with allure.step('enable cluster'):
        enable_cluster()

    with allure.step("prepare rbac"):
        cluster_app_nmx_c: ClusterApp = cluster.apps.app_name[ClusterConsts.NMX_CONTROLLER]
        rbac_tool_nmx_c = NmxRbacTool(cluster, engines.dut, cluster_app_nmx_c)
        rbac_file_name = "controller_rbac_upgrade"
        certs_location = get_test_certs_dir_location("controller_rbac_upgrade", dut_hostname)
        certs_location, certs = setup_certs_for_tests(
            certs_dirname_prefix=certs_location,
            certs_names=["client_nmx_c", "server_nmx_c"],
            engines=engines,
            dut_hostname=dut_hostname,
            scp_player=scp_player,
            dut_ip=engines.dut.ip,
            create_chain=False,
        )
        client_cert_nmx_c = certs[0]
        server_cert_nmx_c = certs[1]
        rbac_tool_nmx_c.prepare_nmx_certs([server_cert_nmx_c], [client_cert_nmx_c])

    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    try:
        rbac_tool_nmx_c.import_rbac_file(rbac_file_name, rbac_file_path)

        rbac_user = UserInfo("sasha", "sasha_rbac", "admin")
        bad_rbac_user = UserInfo("bad_user", "bad_password", "admin")

        rbac_tool_nmx_c.run_app_client(dut_hostname, rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)

        with allure.step("save config"):
            NvueGeneralCli.save_config(engines.dut)

        yield  # Do upgrade

        with allure.step("verify nmx controller mtls works after upgrade"):
            rbac_tool_nmx_c.run_app_client(dut_hostname, rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)
            rbac_tool_nmx_c.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)

        with allure.step("update rbac file and mode"):
            rbac_tool_nmx_c.update_rbac_file(rbac_file_name)
            rbac_tool_nmx_c.update_rbac_mode(RbacConsts.RBAC_MODE_USERNAME_PASSWORD)

        with allure.step("verify nmx controller mtls works after applying rbac file and mode"):
            rbac_tool_nmx_c.run_app_client(dut_hostname, rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=True)
            rbac_tool_nmx_c.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_c, server_cert_nmx_c, expect_success=False)

    finally:
        rbac_tool_nmx_c.restore_rbac_mode()
        rbac_tool_nmx_c.restore_rbac_file()


@_requires_compatibility(IbDevice.JulietSwitch, minimal_version="25.02.4200")
def _check_nmx_telemetry_rbac(
    engines: EnginesT, devices: DevicesT, **kwargs
) -> Generator[None, None, None]:
    """
    Verify RBAC upgrade works as expected
    Test flow:
        1. Enable cluster
        2. Prepare rbac for nmx telemetry
        3. Run app client with good user - Should succeed
        4. Run app client with bad user - Should fail
        5. Perform upgrade
        6. Run app client with good user - Should succeed
        7. Run app client with bad user - Should fail
        8. Restore rbac file
        9. Run app client with bad user - Should succeed
    """
    cluster = Cluster()
    dut_hostname = engines.dut.ip
    scp_player = get_scp_player(engines)
    verify_gnmi_client_tools_installed()

    with allure.step('enable cluster'):
        enable_cluster()

    with allure.step("prepare rbac"):
        cluster_app_nmx_t: ClusterApp = cluster.apps.app_name[ClusterConsts.NMX_TELEMETRY]
        rbac_tool_nmx_t = NmxRbacTool(cluster, engines.dut, cluster_app_nmx_t)
        rbac_file_name = "telemetry_rbac_upgrade"
        certs_location = get_test_certs_dir_location("telemetry_rbac_upgrade", dut_hostname)
        certs_location, certs = setup_certs_for_tests(
            certs_dirname_prefix=certs_location,
            certs_names=["client_nmx_t", "server_nmx_t"],
            engines=engines,
            dut_hostname=dut_hostname,
            scp_player=scp_player,
            dut_ip=engines.dut.ip,
            create_chain=False,
        )
        client_cert_nmx_t = certs[0]
        server_cert_nmx_t = certs[1]
        rbac_tool_nmx_t.prepare_nmx_certs([server_cert_nmx_t], [client_cert_nmx_t])

    rbac_file_path = RbacConsts.NMX_RBAC_FILE_USER_PATH
    try:
        rbac_tool_nmx_t.import_rbac_file(rbac_file_name, rbac_file_path)
        rbac_tool_nmx_t.update_rbac_file(rbac_file_name)
        rbac_tool_nmx_t.update_rbac_mode(RbacConsts.RBAC_MODE_USERNAME_PASSWORD)
        rbac_user = UserInfo("sasha", "sasha_rbac", "admin")
        bad_rbac_user = UserInfo("bad_user", "bad_password", "admin")

        rbac_tool_nmx_t.run_app_client(dut_hostname, rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)
        rbac_tool_nmx_t.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=False)

        with allure.step("save config"):
            NvueGeneralCli.save_config(engines.dut)

        yield  # Do upgrade

        with allure.step("verify rbac works after upgrade"):
            rbac_tool_nmx_t.run_app_client(dut_hostname, rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)
            rbac_tool_nmx_t.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=False)

        with allure.step("restore rbac mode and file"):
            rbac_tool_nmx_t.restore_rbac_mode()
            rbac_tool_nmx_t.restore_rbac_file()

        with allure.step("verify rbac works after restore"):
            rbac_tool_nmx_t.run_app_client(dut_hostname, rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)
            rbac_tool_nmx_t.run_app_client(dut_hostname, bad_rbac_user, client_cert_nmx_t, server_cert_nmx_t, expect_success=True)

    finally:
        rbac_tool_nmx_t.restore_rbac_mode()
        rbac_tool_nmx_t.restore_rbac_file()


@_requires_compatibility(minimal_version="25.02.2100")
def _check_tacacs_auth(engines: EnginesT, devices: DevicesT, **kwargs) -> Generator[None, None, None]:
    """
    Verify TACACS authentication upgrade works as expected.
    Test flow:
        1. Configure TACACS server
        2. Enable TACACS server
        3. Test TACACS auth through auth modes
        4. Save configuration
        5. Do upgrade
        6. Test TACACS auth through auth modes after upgrade
    """
    yield from _run_authentication_test(
        engines=engines,
        devices=devices,
        server_type="TACACS",
        server_config=TacacsDockerServer1.SERVER_BY_ADDRESSING_TYPE,
        auth_modes=AuthMode.ALL_TYPES,
        update_auth_mode_func=update_tacacs_server_auth_mode,
        aaa_obj=System().aaa.tacacs,
        remote_aaa_type=RemoteAaaType.TACACS,
    )


@_requires_compatibility(minimal_version="25.02.2100")
def _check_radius_auth(engines: EnginesT, devices: DevicesT, **kwargs) -> Generator[None, None, None]:
    """
    Verify RADIUS authentication upgrade works as expected.
    Test flow:
        1. Configure RADIUS server
        2. Enable RADIUS server
        3. Test RADIUS auth through auth modes
        4. Save configuration
        5. Do upgrade
        6. Test RADIUS auth through auth modes after upgrade
    """
    server_config = {
        AddressingType.IPV4: RadiusPhysicalServer.SERVER_IPV4,
        AddressingType.IPV6: RadiusVmServer.SERVER_IPV6,
        AddressingType.DN: RadiusVmServer.SERVER_DN,
    }
    yield from _run_authentication_test(
        engines=engines,
        devices=devices,
        server_type="RADIUS",
        server_config=server_config,
        auth_modes=RadiusConsts.AUTH_TYPES,
        update_auth_mode_func=update_radius_server_auth_type,
        aaa_obj=System().aaa.radius,
        remote_aaa_type=RemoteAaaType.RADIUS,
    )


@_requires_compatibility(minimal_version="25.02.2100")
def _check_ldap_auth(engines: EnginesT, devices: DevicesT, **kwargs) -> Generator[None, None, None]:
    """
    Verify LDAP authentication upgrade works as expected.
    Test flow:
        1. Configure LDAP server
        2. Enable LDAP server
        3. Test LDAP auth through auth modes
        4. Save configuration
        5. Do upgrade
        6. Test LDAP auth through auth modes after upgrade
    """
    yield from _run_authentication_test(
        engines=engines,
        devices=devices,
        server_type="LDAP",
        server_config=LdapServersP3.LDAP3_SERVERS,
        auth_modes=LdapEncryptionModes.ALL_MODES,
        update_auth_mode_func=update_ldap_encryption_mode,
        aaa_obj=System().aaa.ldap,
        remote_aaa_type=RemoteAaaType.LDAP,
        extra_setup_func=wait_for_ldap_nvued_restart_workaround,
    )


@_requires_compatibility(minimal_version="25.02.6000")
def _check_ssh_cert_auth(engines: EnginesT, devices: DevicesT, **kwargs) -> Generator[None, None, None]:
    """
    Verify SSH certificate authentication upgrade works as expected.
    Test flow:
        1. Generate SSH key pair and CA key pair
        2. Sign user certificate with CA
        3. Set principal and enable cert-auth for admin user
        4. Set trusted CA key on the system
        5. Verify user can login with certificate
        6. Save configuration
        7. Do upgrade
        8. Verify user can still login with certificate after upgrade
    """
    system = System()
    ssh_cert_auth_helper = SshCertAuthHelper()
    key_name = "upgrade_cert_test_key"
    key_type = get_random_key_type()
    principal = get_random_principal()
    admin_user = UserInfo(SystemConsts.DEFAULT_USER_ADMIN, SystemConsts.DEFAULT_USER_ADMIN, UserRole.ADMIN)
    hostname = engines.dut.ip

    try:
        with allure.step("Setup SSH certificate authentication"):
            ssh_cert_auth_helper.ensure_keys_directory()

            with allure.step("Generate keys and sign certificate"):
                ca_val, key_private_path = ssh_cert_auth_helper.generate_keys_and_sign_certificate(
                    key_name=key_name, key_type=key_type, principals=[principal]
                )

            with allure.step(f"Set cert-auth principal {principal} for admin"):
                set_cert_auth(system=system, user=admin_user, principal=principal, state="enabled", apply=False)

            with allure.step(f"Set trusted CA key {key_name}"):
                set_trusted_ca_key(system, key_name, key_type, ca_val, apply=True)

            with allure.step("Verify login with certificate before upgrade"):
                verify_user_login(admin_user, key_private_path, hostname, engines, expect_success=True)

            with allure.step("Save configuration"):
                NvueGeneralCli.save_config(engines.dut)

        yield  # Do upgrade

        with allure.step("Verify SSH cert auth after upgrade"):
            with allure.step("Verify login with certificate after upgrade"):
                verify_user_login(admin_user, key_private_path, hostname, engines, expect_success=True)

    finally:
        with allure.step("Cleanup SSH cert auth configuration"):
            try:
                system.ssh_server.trusted_ca_keys.unset()
                system.aaa.user.user_id[admin_user.username].ssh.cert_auth.unset(apply=True)
            except Exception as cleanup_err:
                logger.warning(f"Cleanup failed: {cleanup_err}")
            ssh_cert_auth_helper.cleanup_generated_keys(key_name)


# #################### End of Feature Checkers ###################


def _run_authentication_test(
    engines: EnginesT,
    devices: DevicesT,
    server_type: str,
    server_config: dict,
    auth_modes: List[str],
    update_auth_mode_func,
    aaa_obj,
    remote_aaa_type: str,
    extra_setup_func=None,
    extra_cleanup_func=None,
    **kwargs
) -> Generator[None, None, None]:
    """
    Generic authentication test function for TACACS, RADIUS and LDAP.

    Args:
        engines: The engines object
        devices: The devices object
        server_type: Type of authentication server (TACACS/RADIUS/LDAP)
        server_config: Server configuration dictionary
        auth_modes: List of authentication modes to test
        update_auth_mode_func: Function to update authentication mode
        aaa_obj: AAA object (tacacs_obj, radius_obj, ldap_obj)
        remote_aaa_type: Remote AAA type string
        extra_setup_func: Optional extra setup function to call
        extra_cleanup_func: Optional extra cleanup function to call
    """
    skip_auth_mediums = [AuthMedium.OPENAPI, AuthMedium.SCP]  # skip openapi and scp, as we have certificates configured
    test_flow = TestFlowType.GOOD_FLOW
    addressing_type = AddressingType.IPV4
    topology_obj = TestToolkit.topology_obj

    adminuser = _prepare_local_admin_user(engines, devices)
    server_active_conf = SimpleNamespace()

    try:
        with allure.step(f"Configure {remote_aaa_type} server"):
            server = server_config[addressing_type].copy()
            assert getattr(server, "users_per_auth_medium", None) is not None, (
                f'given server must have "users_per_auth_medium" attr\n'
                f"server: {server.hostname} - {server.port} - {server.docker_name}"
            )
            server_resource = aaa_obj.server.server_id[server.hostname]
            server.configure(engines)

        with allure.step(f"Enable {remote_aaa_type}"):
            aaa_obj.enable(apply=True, verify_res=False)
            update_active_aaa_server(server_active_conf, server)

            if extra_setup_func:
                extra_setup_func(server_active_conf)

        with allure.step(f"test {server_type.lower()} auth works before upgrade through auth modes: {auth_modes}"):
            for auth_mode in auth_modes:
                with allure.step(auth_mode):
                    with allure.step(f"Update test param: {auth_mode}"):
                        update_auth_mode_func(
                            engines, server_active_conf, server, server_resource, auth_mode
                        )
                        if extra_setup_func:
                            extra_setup_func(server_active_conf)
                    with allure.step("Test auth"):
                        verify_auth_mediums(
                            test_flow,
                            engines,
                            topology_obj,
                            True,
                            False,
                            server,
                            UserRole.ALL_ROLES,
                            [adminuser],
                            skip_auth_mediums=skip_auth_mediums,
                        )

        with allure.step("Save configuration"):
            NvueGeneralCli.save_config(engines.dut)

        yield  # Do upgrade

        with allure.step(f"test {server_type.lower()} auth through auth modes: {auth_modes} after upgrade"):
            for auth_mode in auth_modes:
                with allure.step(auth_mode):
                    with allure.step(f"Update test param: {auth_mode}"):
                        update_auth_mode_func(
                            engines, server_active_conf, server, server_resource, auth_mode
                        )
                    with allure.step("Test auth"):
                        verify_auth_mediums(
                            test_flow,
                            engines,
                            topology_obj,
                            True,
                            False,
                            server,
                            UserRole.ALL_ROLES,
                            [adminuser],
                            skip_auth_mediums=skip_auth_mediums,
                        )
    except Exception as e:
        logger.error(f"Authentication test failed for {server_type}: {e}")
        raise
    finally:
        if extra_cleanup_func:
            try:
                extra_cleanup_func(server_active_conf)
            except Exception as cleanup_error:
                logger.warning(f"Cleanup failed: {cleanup_error}")


def _prepare_local_admin_user(engines, devices) -> UserInfo:
    """
    Prepare a local admin user for authentication testing.

    Args:
        engines: The engines object
        devices: The devices object

    Returns:
        UserInfo: The created admin user

    Raises:
        RuntimeError: If user creation fails
    """
    try:
        adminrole = devices.dut.aaa_admin_role
        adminuser = UserInfo(
            username=AaaConsts.LOCALADMIN,
            password=generate_strong_password(),
            role=adminrole,
        )
        set_local_users(engines, [adminuser], apply=True)
        return adminuser
    except Exception as e:
        logger.error(f"Failed to create local admin user: {e}")
        raise RuntimeError(f"User creation failed: {e}")


@_requires_compatibility(minimal_version="25.02.2100")
def _check_speed_configuration(engines: EnginesT, devices: DevicesT, base: SystemPackage, target: SystemPackage, **kwargs) -> Generator[None, None, None]:
    """
    Verify that interface speed configuration is preserved across upgrade.

    Test flow:
        1. Configure speed on a random port (before upgrade)
        2. Perform upgrade
        3. Verify speed configuration preserved after upgrade
        4. Cleanup speed testing configuration

    Note: This replaces the speed testing from the deprecated test_downgrade_upgrade
    in test_system_image.py
    """
    speed_info = None

    with allure.step("Configure and test interface speeds"):
        try:
            speed_info = InterfaceConfigurationTool.choose_random_port_and_test_speed_configuration(engines, devices)

            if speed_info:
                logger.info(f"Speed testing configured successfully on port: {speed_info[0].name}")
        except Exception as e:
            logger.warning(f"Speed testing setup failed, will skip this checker: {e}")
            raise Skipped(f"Speed testing setup failed: {e}")

    yield  # Perform upgrade

    # Verify and cleanup after upgrade
    with allure.step("Verify speed configuration preserved and cleanup"):
        if speed_info:
            NvosInstallationSteps.cleanup_speed_testing_if_performed(speed_info, devices.dut)


# the checker must be called e.g. test_rbac
_CHECKERS: List[CheckerFn] = [
    _check_nmx_cert,
    _check_api_mtls_old,
    _check_cert_mgmt,
    _check_rbac,
    _check_sed_password,
    _check_gnmi_mtls_spiffe_id_and_crl,
    _check_api_mtls_spiffe_id_and_crl,
    _check_nmx_controller_rbac,
    _check_nmx_telemetry_rbac,
    _check_speed_configuration,
    _check_ssh_cert_auth,
]

_CHECKERS.append(random.choice([_check_tacacs_auth, _check_radius_auth, _check_ldap_auth]))  # This is intended to be random, as two AAA checkers can't run together
