"""
Constants for TCG Platform Certificate Profile tests.
"""
from enum import Enum


class UploadProtocol(Enum):
    """Supported protocols for certificate upload."""
    SCP = 'scp'
    SFTP = 'sftp'
    HTTPS = 'https'


# Remote path for certificate uploads
REMOTE_PATH = '/tmp'
# Generic URL template - protocol is a parameter
REMOTE_URL_TEMPLATE = '{protocol}://{username}:{password}@{host}' + REMOTE_PATH + '/{filename}'
REMOTE_PATH_HTTPS = 'https://nbu-mtr-nfs.nvidia.com/auto/sw_system_project/NVOS_INFRA/verification_files/platform_certificate/'

# Platform certificate filename
PLATFORM_CERT_FILENAME = 'platform_certificate.pem'

# Expected strings in certificate output
CERT_FIELD_SERIAL_NUMBER = 'Serial Number'
CERT_FIELD_ISSUER = 'Issuer'
CERT_FIELD_VALIDITY = 'Validity'
CERT_FIELD_NOT_BEFORE = 'Not Before'
CERT_FIELD_NOT_AFTER = 'Not After'
CERT_FIELD_SUBJECT = 'Subject'
CERT_FIELD_CERTIFICATE = 'Certificate'
CERT_FIELD_SIGNATURE_ALGORITHM = 'Signature Algorithm'

# Required fields that should be present in platform certificate
REQUIRED_CERT_FIELDS = [
    CERT_FIELD_CERTIFICATE,
    CERT_FIELD_SERIAL_NUMBER,
    CERT_FIELD_ISSUER,
    CERT_FIELD_VALIDITY,
    CERT_FIELD_SUBJECT,
]

# Upload success message
UPLOAD_SUCCESS_MSG = 'successfully'
