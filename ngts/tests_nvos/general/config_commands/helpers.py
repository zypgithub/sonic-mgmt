import logging
import re

from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()
default_values_dict = {
    "set": {
        "platform": {
            "firmware": {
                "ASIC": {
                    "auto-update": "enabled",
                    "fw-source": "default"
                }
            }
        },
        "system": {
            "aaa": {
                "user": {
                    "admin": {
                        "full-name": "System Administrator",
                        "hashed-password": "*",
                        "password": "*",
                        "role": "admin",
                        "state": "enabled"
                    }
                }
            }
        }
    }
}


def verify_new_config_output(output):
    expected_pattern = r"created \[rev_id: \d+\]"
    assert re.search(expected_pattern, output), f"Failed to perform config operation - output '{output}' does not match expected pattern '{expected_pattern}'"


class RevisionStatus:
    CREATED = "created"
    APPLIED = "applied"
    ATTACHED = "attached"
    DETACHED = "detached"
    INVALID = "invalid"
    SAVED = "saved"
    DELETED = "deleted"
