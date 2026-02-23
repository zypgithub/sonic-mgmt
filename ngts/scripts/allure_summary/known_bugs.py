"""
Known Bugs Analyzer for Test Failure Correlation.

This module fetches known bugs from Confluence and correlates them with test failures
to identify:
- Test failures that match known bugs
- Tests with assigned team members
- Bug status (Fixed, Assigned, Bug, Test Issue)

Data source: https://confluence.nvidia.com/pages/viewpage.action?pageId=4503208989
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()

# Confluence page with known bugs
KNOWN_BUGS_PAGE_URL = "https://confluence.nvidia.com/pages/viewpage.action?pageId=4503208989"


@dataclass
class KnownBug:
    """Represents a known bug."""
    bug_id: str  # e.g., "4463449" or "5721616"
    bug_type: str  # "nvbugs" or "sw"
    description: str
    url: str

    @property
    def full_id(self) -> str:
        if self.bug_type == "nvbugs":
            return f"nvbugs/{self.bug_id}"
        return f"Bug SW #{self.bug_id}"


@dataclass
class TestBugMapping:
    """Mapping between a test and known bug/status."""
    test_name: str
    setup_name: str = ""
    bug: Optional[KnownBug] = None
    assigned_to: str = ""
    status: str = ""  # Bug, Fixed, Assigned, Test Issue, WIP
    notes: str = ""
    priority: str = ""


@dataclass
class KnownBugsDatabase:
    """Database of known bugs and test mappings."""
    bugs: List[KnownBug] = field(default_factory=list)
    test_mappings: List[TestBugMapping] = field(default_factory=list)
    last_updated: Optional[datetime] = None

    def find_bug_for_test(self, test_name: str) -> Optional[TestBugMapping]:
        """Find if a test has a known bug/assignment."""
        test_name_lower = test_name.lower()
        for mapping in self.test_mappings:
            # Match test name (can be partial match or with parameters)
            mapping_name = mapping.test_name.lower()
            if mapping_name in test_name_lower or test_name_lower in mapping_name:
                return mapping
            # Handle parameterized tests like test_foo[OpenApi]
            base_name = re.sub(r'\[.*\]$', '', test_name_lower)
            if mapping_name in base_name or base_name in mapping_name:
                return mapping
        return None

    def find_bugs_by_pattern(self, error_message: str) -> List[KnownBug]:
        """Find bugs that might match an error pattern."""
        matching = []
        error_lower = error_message.lower()
        for bug in self.bugs:
            desc_lower = bug.description.lower()
            # Check for keyword matches
            keywords = re.findall(r'\b\w{4,}\b', desc_lower)
            matches = sum(1 for kw in keywords if kw in error_lower)
            if matches >= 2:
                matching.append(bug)
        return matching


def parse_bugs_from_content(content: List[str]) -> KnownBugsDatabase:
    """
    Parse known bugs and test mappings from Confluence page content.

    Args:
        content: List of content lines from Confluence page

    Returns:
        KnownBugsDatabase with parsed bugs and mappings
    """
    db = KnownBugsDatabase()
    db.last_updated = datetime.now()

    current_setup = ""

    for line in content:
        line = line.strip()

        # Parse standalone bugs
        # Pattern: [NVOS - Design] Bug SW #4463449: description
        sw_bug_match = re.search(r'Bug SW #(\d+)[:\s]+(.+?)(?:\||$)', line)
        if sw_bug_match:
            bug = KnownBug(
                bug_id=sw_bug_match.group(1),
                bug_type="sw",
                description=sw_bug_match.group(2).strip(),
                url=f"https://nvbugs/{sw_bug_match.group(1)}"
            )
            if bug not in db.bugs:
                db.bugs.append(bug)

        # Pattern: https://nvbugs/5721616 description
        nvbugs_match = re.search(r'https://nvbugs/(\d+)\s+(.+?)(?:\||$)', line)
        if nvbugs_match:
            bug = KnownBug(
                bug_id=nvbugs_match.group(1),
                bug_type="nvbugs",
                description=nvbugs_match.group(2).strip(),
                url=f"https://nvbugs/{nvbugs_match.group(1)}"
            )
            if bug not in db.bugs:
                db.bugs.append(bug)

        # Parse test mappings from CSV-like rows
        # Pattern: setup_name,test_name,Assigned team member,Status,priority,Notes,Link
        if ',' in line and not line.startswith('#'):
            parts = line.split(',')
            if len(parts) >= 4:
                setup = parts[0].strip()
                test_name = parts[1].strip()
                assigned = parts[2].strip() if len(parts) > 2 else ""
                status = parts[3].strip() if len(parts) > 3 else ""
                priority = parts[4].strip() if len(parts) > 4 else ""
                notes = parts[5].strip() if len(parts) > 5 else ""

                # Skip header rows
                if test_name and test_name.lower() not in ['test name', 'test_name', 'notes']:
                    # Handle multiple tests in same cell (test_foo\ntest_bar)
                    for t in re.split(r'(?:test_)', test_name):
                        t = t.strip()
                        if t and not t.startswith('name'):
                            t_name = f"test_{t}" if not t.startswith('test_') else t

                            # Extract bug ID from notes if present
                            bug = None
                            bug_match = re.search(r'(?:Bug|#)\s*(\d{7})', notes) or \
                                re.search(r'nvbugs/(\d+)', notes)
                            if bug_match:
                                bug = KnownBug(
                                    bug_id=bug_match.group(1),
                                    bug_type="nvbugs",
                                    description=notes[:100],
                                    url=f"https://nvbugs/{bug_match.group(1)}"
                                )

                            mapping = TestBugMapping(
                                test_name=t_name,
                                setup_name=setup or current_setup,
                                bug=bug,
                                assigned_to=assigned,
                                status=status,
                                notes=notes,
                                priority=priority
                            )
                            db.test_mappings.append(mapping)

                if setup:
                    current_setup = setup

    logger.info(f"Parsed {len(db.bugs)} known bugs and {len(db.test_mappings)} test mappings")
    return db


def fetch_known_bugs_from_confluence() -> Optional[KnownBugsDatabase]:
    """
    Fetch known bugs from Confluence using MCP.

    Note: This requires MCP Confluence access. If not available,
    returns None and the feature is disabled.
    """
    try:
        import requests
        # This would use MCP in practice, but for now we'll use cached data
        # from the page content that was already fetched
        logger.info("Known bugs database should be fetched via MCP Confluence")
        return None
    except Exception as e:
        logger.debug(f"Could not fetch known bugs: {e}")
        return None


# Hardcoded known bugs from the Confluence page (for offline/fallback use)
KNOWN_BUGS_CACHE = [
    KnownBug("4463449", "sw", "log_analyzer ERR kernel ima: No suitable TPM algorithm", "https://nvbugs/4463449"),
    KnownBug("4669456", "sw", "health-statsd ServiceChecker KeyError('state')", "https://nvbugs/4669456"),
    KnownBug("5721616", "nvbugs", "OpenAPI reboot action fails with Close client sessions failed", "https://nvbugs/5721616"),
    KnownBug("4518617", "sw", "ntpd leapsecond file expired", "https://nvbugs/4518617"),
    KnownBug("4643626", "sw", "orchagent validatePortConfig missing mandatory field speed", "https://nvbugs/4643626"),
    KnownBug("5724996", "nvbugs", "bad output for non-existing event number", "https://nvbugs/5724996"),
    KnownBug("5727482", "nvbugs", "gnmic mode once subscription terminates degradation", "https://nvbugs/5727482"),
    KnownBug("4784602", "sw", "BIOS Auto-Update Operation Time Degradation", "https://nvbugs/4784602"),
    KnownBug("4549426", "sw", "unexpected logs found during idle", "https://nvbugs/4549426"),
    KnownBug("4572303", "sw", "Failed to upload file: No response from server", "https://nvbugs/4572303"),
    KnownBug("4790028", "sw", "gnmi socket unavailable after docker restart", "https://nvbugs/4790028"),
    KnownBug("5740109", "nvbugs", "Transceiver Detection Mismatch", "https://nvbugs/5740109"),
    KnownBug("4792430", "sw", "port connected via loop cable has raw-ber errors", "https://nvbugs/4792430"),
    KnownBug("4792689", "sw", "portsyncmgrd Logging Flood on Port State Change", "https://nvbugs/4792689"),
    KnownBug("5740401", "nvbugs", "During CPLD installation no reboot msg in output", "https://nvbugs/5740401"),
    KnownBug("5768072", "nvbugs", "Unable to split port a second time", "https://nvbugs/5768072"),
    KnownBug("4816792", "sw", "SSD part number missing in nv show platform firmware", "https://nvbugs/4816792"),
    KnownBug("4831276", "sw", "OpenAPI action status field not updated on success", "https://nvbugs/4831276"),
    KnownBug("4303918", "sw", "missing dump file hdparm for XDR systems", "https://nvbugs/4303918"),
    KnownBug("5785278", "nvbugs", "nv-umf service refuses gNMI socket connections", "https://nvbugs/5785278"),
    KnownBug("4819789", "sw", "temperature is too hot on multiple PSUs", "https://nvbugs/4819789"),
]

# Test-to-bug mappings from Confluence
TEST_BUG_MAPPINGS_CACHE = [
    TestBugMapping("test_upload_log_files", bug=KnownBug("4572303", "sw", "Failed to upload file", "https://nvbugs/4572303"), status="Bug"),
    TestBugMapping("test_log_idle", bug=KnownBug("4549426", "sw", "unexpected logs during idle", "https://nvbugs/4549426"), status="Bug"),
    TestBugMapping("test_bios_auto_update_enabled", bug=KnownBug("4784602", "sw", "BIOS Auto-Update Time Degradation", "https://nvbugs/4784602"), status="Bug"),
    TestBugMapping("test_gnmi_basic_flow_once", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_gnmi_basic_flow_stream", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_simulate_gnmi_server_failure", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_simulate_gnmi_client_failure", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_updates_on_gnmi_stream_mode", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_gnmi_bad_flow", bug=KnownBug("4790028", "sw", "gNMI not receiving updates", "https://nvbugs/4790028"), status="Bug"),
    TestBugMapping("test_transceivers_and_ports", status="Bug", notes="Missing per device ports"),
    TestBugMapping("test_no_logging_flood_on_port_state_change", bug=KnownBug("4792689", "sw", "Logging Flood on Port State Change", "https://nvbugs/4792689"), status="Bug"),
    TestBugMapping("test_ssd_cleanup_reboot_with_high_ssd_usage", status="Fixed", notes="Fix needs cherry-pick from 0300"),
    TestBugMapping("test_system_mgmt_unsolicited_enabled", status="Bug"),
    TestBugMapping("test_system_mgmt_unsolicited_shutdown_enabled", status="Fixed"),
    TestBugMapping("test_system_mgmt_unsolicited_shutdown_disabled", status="Fixed"),
    TestBugMapping("test_simulate_health_problem_with_docker_stop", status="Assigned"),
    TestBugMapping("test_certificate_commands", status="Test Issue", notes="Test code fix needed"),
    TestBugMapping("test_ca_certificate_commands", status="Test Issue", notes="Test code fix needed"),
    TestBugMapping("test_aggregated_port_config_op_vls", notes="Timeout >900s"),
    TestBugMapping("test_aggregated_port_config_mtu", notes="Timeout >900s"),
    TestBugMapping("test_fae_invalid_commands", notes="LinkMgmt has no counters attribute"),
    TestBugMapping("test_interface_aggregated_port_split", notes="mtu value mismatch"),
    TestBugMapping("test_reboot_mode", status="Assigned", notes="Reboot reason mismatch"),
    TestBugMapping("test_set_system_message_post_logout", status="Assigned"),
    TestBugMapping("test_unset_system_message", status="Assigned"),
    TestBugMapping("test_system_reload_for_system_message", status="Assigned"),
    TestBugMapping("test_syslog_rate_limit_burst", status="Fixed", notes="Gerrit 321854"),
    TestBugMapping("test_syslog_logging_during_system_reboot", status="Fixed", notes="Gerrit 321854"),
    TestBugMapping("test_replace_removes_existing_config", status="Bug", bug=KnownBug("5650127", "nvbugs", "Replace operation ACL handling", "https://nvbugs/5650127")),
    TestBugMapping("test_variable_expansion_inconsistency_bug", status="Fixed", notes="Gerrit 321854"),
    TestBugMapping("test_device_disk", notes="disk test issue"),
    TestBugMapping("test_sensor_errors", notes="sensor errors", status="Assigned"),
    TestBugMapping("test_reset_transceiver_firmware_positive", notes="carrier-down-count counter issue"),
    TestBugMapping("test_install_transceiver_firmware_positive", notes="carrier-down-count counter issue"),
    TestBugMapping("test_interface_eth0_show_after_reboot", notes="KeyError: 'address'"),
    TestBugMapping("test_ib_split_port_default_values", notes="split port issue"),
    TestBugMapping("test_interface_ib0_autoconfig_disabled_sm", notes="autoconf value issue"),
]


def get_known_bugs_database() -> KnownBugsDatabase:
    """
    Get the known bugs database.

    First tries to fetch from Confluence, falls back to cached data.
    """
    # Try to fetch from Confluence
    db = fetch_known_bugs_from_confluence()
    if db:
        return db

    # Use cached data
    logger.info("Using cached known bugs database")
    db = KnownBugsDatabase()
    db.bugs = KNOWN_BUGS_CACHE.copy()
    db.test_mappings = TEST_BUG_MAPPINGS_CACHE.copy()
    db.last_updated = datetime.now()
    return db


def enrich_test_with_known_bugs(
    test_name: str,
    error_message: str,
    db: Optional[KnownBugsDatabase] = None
) -> Dict:
    """
    Enrich a test failure with known bug information.

    Args:
        test_name: Name of the failing test
        error_message: Error message from the test
        db: Known bugs database (optional, will fetch if not provided)

    Returns:
        Dict with:
        - has_known_bug: bool
        - bug: KnownBug or None
        - assigned_to: str
        - status: str
        - notes: str
    """
    if db is None:
        db = get_known_bugs_database()

    result = {
        "has_known_bug": False,
        "bug": None,
        "assigned_to": "",
        "status": "",
        "notes": ""
    }

    # First check direct test mapping
    mapping = db.find_bug_for_test(test_name)
    if mapping:
        result["has_known_bug"] = mapping.bug is not None
        result["bug"] = mapping.bug
        result["assigned_to"] = mapping.assigned_to
        result["status"] = mapping.status
        result["notes"] = mapping.notes
        return result

    # Try to match by error message patterns
    matching_bugs = db.find_bugs_by_pattern(error_message)
    if matching_bugs:
        result["has_known_bug"] = True
        result["bug"] = matching_bugs[0]  # Take first match

    return result
