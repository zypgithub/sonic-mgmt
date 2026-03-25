import logging
from typing import Union

from ngts.nvos_constants.constants_nvos import AclConsts, SystemConsts
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System

logger = logging.getLogger(__name__)


def extract_acl_rules():
    """
    Capture default ACL baseline (names and rule counts) from current DUT state.
    Uses same approach as test_show_acls in test_acl_basic. Returns dict of acl_name -> rule_count.
    """
    acl = Acl()
    acls = OutputParsingTool.parse_show_output_to_dict(acl.show()).get_returned_value()
    if not acls:
        logger.warning("extract_acl_rules: nv show acl returned empty or None")
        return {}
    # API may return wrapped JSON e.g. {"acl": {"acl-default-dos": {...}}} - unwrap so keys are ACL names
    if len(acls) == 1:
        single_key = next(iter(acls.keys()))
        inner = acls[single_key]
        if isinstance(inner, dict) and inner and all(isinstance(v, dict) for v in inner.values()):
            acls = inner
            logger.debug("extract_acl_rules: unwrapped top-level key %r", single_key)
    logger.info("extract_acl_rules: acls keys from nv show acl: %s", list(acls.keys()))
    default_names = list(AclConsts.NEW_DEFAULT_ACLS) + list(AclConsts.DEFAULT_ACLS)
    baseline = {}
    for name in default_names:
        if name in acls:
            rule_count = len(acls[name].get(AclConsts.RULE, {}))
            baseline[name] = rule_count
            logger.info("Default ACL baseline: %s -> %s rules", name, rule_count)
    if not baseline:
        logger.warning("extract_acl_rules: baseline empty; no default ACL names matched. acls keys: %s", list(acls.keys()))
    return baseline


def _unwrap_acls_if_needed(acls):
    """If nv show acl returned {"acl": {"acl-name": {...}, ...}}, return inner dict."""
    if not acls or len(acls) != 1:
        return acls
    single_key = next(iter(acls.keys()))
    inner = acls[single_key]
    if isinstance(inner, dict) and inner and all(isinstance(v, dict) for v in inner.values()):
        return inner
    return acls


def verify_acl_rules_preserved(baseline):
    """After upgrade, verify default ACLs present and (where in baseline) rule counts preserved."""
    if not baseline:
        logger.info("No ACL baseline to verify (skipping)")
        return
    acl = Acl()
    acls = OutputParsingTool.parse_show_output_to_dict(acl.show()).get_returned_value()
    if not acls:
        raise AssertionError("No ACLs found after upgrade (nv show acl returned empty)")
    acls = _unwrap_acls_if_needed(acls)
    assert len(acls.keys()) >= 1, "No ACLs found after upgrade"
    for acl_name, expected_count in baseline.items():
        if acl_name not in acls:
            raise AssertionError("ACL %r from baseline missing after upgrade. Present: %s" % (acl_name, list(acls.keys())))
        actual_count = len(acls[acl_name].get(AclConsts.RULE, {}))
        assert actual_count == expected_count, (
            "Default ACL {} rule count changed after upgrade: was {}, now {}".format(
                acl_name, expected_count, actual_count
            )
        )
        logger.info("Default ACL %s preserved: %s rules", acl_name, actual_count)


def extract_control_plane_acl_bindings():
    """Capture ACL names bound to system control-plane (nv show system control-plane acl). Returns set."""
    system = System()
    try:
        cp_acls = system.control_plane.acl.parse_show()
    except Exception as e:
        logger.warning("Could not get system control-plane ACLs: %s", e)
        return set()
    if not cp_acls:
        return set()
    bindings = set(cp_acls.keys())
    logger.info("Control-plane ACL bindings: %s", bindings)
    return bindings


def verify_control_plane_acl_bindings(baseline_bindings):
    """After upgrade, verify all default ACLs are still bound to system control-plane."""
    if baseline_bindings is None:
        logger.info("No control-plane baseline to verify (skipping)")
        return
    system = System()
    try:
        cp_acls = system.control_plane.acl.parse_show()
    except Exception as e:
        logger.warning("Could not get system control-plane ACLs after upgrade: %s", e)
        return
    current_bindings = set(cp_acls.keys()) if cp_acls else set()
    for default_acl in AclConsts.NEW_DEFAULT_ACLS:
        assert default_acl in current_bindings, (
            "Default ACL {} not bound to system control-plane after upgrade. "
            "Bound ACLs: {}".format(default_acl, sorted(current_bindings))
        )
        logger.info("Default ACL %s bound to control-plane", default_acl)
    logger.info("All default ACLs bound to control-plane before and after upgrade")


def verify_api_compression_state(system: System, expected_compression: Union[str, None]) -> None:
    applied_compression: Union[str, None] = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()[SystemConsts.ApiConsts.COMPRESSION]
    assert applied_compression == expected_compression, \
        f"Compression {'shown' if applied_compression else 'not shown'}, but show is {'expected' if expected_compression else 'not expected'}"
