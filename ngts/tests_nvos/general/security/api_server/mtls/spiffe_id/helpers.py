import random

from ngts.tests_nvos.general.security.api_server.mtls.spiffe_id.constants import MAX_SPIFFE_LEN
from ngts.tests_nvos.helpers.general_helpers import generate_rand_str


def generate_rand_spiffe_id(domain_len=None, path_len=None) -> str:
    domain_len = domain_len or random.randint(1, MAX_SPIFFE_LEN)
    path_len = path_len or random.randint(1, MAX_SPIFFE_LEN)
    rand_domain = generate_rand_str(domain_len)
    rand_path = generate_rand_str(path_len)
    rand_spiffe = f'spiffe://{rand_domain}/{rand_path}'
    return rand_spiffe
