from ngts.nvos_constants.constants_nvos import ApiType

MAX_SPIFFE_LEN = 10
INVALID_SPIFFE_ERR = 'Spiffe id must be in format spiffe://trust-domain/path'
INCOMPLETE_ERR = 'Incomplete Command'
URL_NOT_FOUND_ERR = 'The requested URL was not found on the server'
SPIFFE_UNIQUENESS_ERR = '{} is mapped to more than 1 user'

INCOMPLETE_ERR_PER_API = {
    ApiType.NVUE: INCOMPLETE_ERR,
    ApiType.OPENAPI: URL_NOT_FOUND_ERR
}


class SecurityMode:
    UNSECURED = 'unsecured'
    TLS = 'tls'
    MTLS = 'mtls'
    ALL_MODES = [UNSECURED, TLS, MTLS]


BAD_RESPONSE_KEYWORDS = ['Authorization Required', "You don't have the permission to access the requested resource",
                         'Forbidden', 'The server could not verify that you are authorized to access the URL requested',
                         'Unauthorized', 'Bad Request', 'No required SSL certificate was sent']
