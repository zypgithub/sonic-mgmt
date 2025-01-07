import logging

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


class RevisionStatus:
    CREATED = "created"
    APPLIED = "applied"
    ATTACHED = "attached"
    DETACHED = "detached"
    INVALID = "invalid"
    SAVED = "saved"
    DELETED = "deleted"
