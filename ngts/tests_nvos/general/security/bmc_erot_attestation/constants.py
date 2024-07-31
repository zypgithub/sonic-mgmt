from typing import Dict

from ngts.nvos_tools.system.Spdm import SPDMComponents, SpdmComponentFields

VALID_NONCE_LEN = 64

NONE = 'None'
UNKNOWN = 'unknown'
NA = 'N/A'
NOT_EMPTY = -1


class SpdmConsts:
    SPDM = 'spdm'
    components = fields = SPDMComponents.ALL_SUPPORTED_COMPONENTS

    class Component:
        fields = SpdmComponentFields.ALL_FIELDS

        class Certificate:
            CERT_STRING = 'CertificateString'
            CERT_TYPE = 'CertificateType'
            CERT_USAGE_TYPES = 'CertificateUsageTypes'
            ID = 'Id'
            NAME = 'Name'
            SPDM = 'SPDM'
            fields = [CERT_STRING, CERT_TYPE, CERT_USAGE_TYPES, ID, NAME, SPDM]
            na_values: Dict[str, str] = {f: NA for f in fields}

        class Measurements:
            HASHING_ALGO = 'HashingAlgorithm'
            SIGNED_MEASUREMENTS = 'SignedMeasurements'
            SIGNING_ALGO = 'SigningAlgorithm'
            VERSION = 'Version'
            fields = [HASHING_ALGO, SIGNED_MEASUREMENTS, SIGNING_ALGO, VERSION]
            initial_values: Dict[str, str] = {
                HASHING_ALGO: NONE,
                SIGNED_MEASUREMENTS: '',
                SIGNING_ALGO: NONE,
                VERSION: UNKNOWN,
            }
            na_values: Dict[str, str] = {f: NA for f in fields}
