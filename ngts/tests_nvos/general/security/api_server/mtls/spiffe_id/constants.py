MAX_SPIFFE_LEN = 10
INVALID_SPIFFE_ERR = 'Spiffe id must be in format spiffe://trust-domain/path'
INCOMPLETE_ERR = 'Incomplete Command'
SPIFFE_UNIQUENESS_ERR = '{} is mapped to more than 1 user'


class SecurityMode:
    UNSECURED = 'unsecured'
    TLS = 'tls'
    MTLS = 'mtls'
    ALL_MODES = [UNSECURED, TLS, MTLS]


BAD_RESPONSE_KEYWORDS = ['401 Authorization Required', "You don't have the permission to access the requested resource",
                         '403', 'Forbidden', 'The server could not verify that you are authorized to access the URL requested',
                         '401', 'Unauthorized']
