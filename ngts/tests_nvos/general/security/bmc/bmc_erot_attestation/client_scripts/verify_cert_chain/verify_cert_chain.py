import logging
import os
import sys
import traceback
from contextlib import contextmanager
from typing import List

from OpenSSL import crypto

LOG_PREFIX = 'VerifyCertChainScript'
BEGIN_CERT = "-----BEGIN CERTIFICATE-----"


def log(msg):
    msg = f'[{LOG_PREFIX}] {msg}'
    if 'pytest' in sys.modules:
        logging.info(msg)
    else:
        print(msg)


@contextmanager
def step(name: str):
    # print(f"Starting step: {name}")
    try:
        yield
        log(f"Step '{name}': OK")
    except Exception as e:
        log(f"Step '{name}': FAIL")
        raise


def parse_certs_str(chain_str: str) -> List[crypto.X509]:
    """
    parse a certificate chain, given as string, to list of certificate crypto.X509 objects
    """
    certs: List[crypto.X509] = []
    for cert_pem in chain_str.split(BEGIN_CERT)[1:]:
        cert_data = BEGIN_CERT + cert_pem
        cert: crypto.X509 = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)
        certs.append(cert)
    return certs


def parse_certs_file(chain_path: str) -> List[crypto.X509]:
    """
    parse a certificate chain, given as path to PEM file, to list of certificate crypto.X509 objects
    """
    certs: List[crypto.X509] = []
    with open(chain_path, "r") as f:
        for cert_pem in f.read().split(BEGIN_CERT)[1:]:
            cert_data = BEGIN_CERT + cert_pem
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_data)
            certs.append(cert)
    return certs


def order_certs(certs: List[crypto.X509]) -> List[crypto.X509]:
    """
    order the given certificates list, such that leaf is first, and root is last
    """
    if not certs:
        raise ValueError("order_certs: No certificates provided")

    cert_dict = {cert.get_subject().der(): cert for cert in certs}

    # Find leaf certificate
    leaf: crypto.X509 = find_leaf_cert(certs)

    ordered_certs = [leaf]
    current_cert = leaf

    while len(ordered_certs) < len(certs):
        issuer_der = current_cert.get_issuer().der()
        if issuer_der in cert_dict:
            current_cert = cert_dict[issuer_der]
            ordered_certs.append(current_cert)
        else:
            raise ValueError("order_certs: Unable to complete certificate chain")

    return ordered_certs


def find_leaf_cert(certs: List[crypto.X509]) -> crypto.X509:
    """
    Find the leaf certificate in the chain.
    The leaf certificate is the one whose subject is not an issuer of any other cert.
    """
    all_issuers = set(cert.get_issuer().der() for cert in certs)

    for cert in certs:
        if cert.get_subject().der() not in all_issuers:
            return cert

    raise ValueError("find_leaf_cert: Unable to find leaf certificate")


def save_ordered_chain(ordered_certs: List[crypto.X509], output_path: str):
    """
    store the given certificate list as a certificate chain PEM file, in the required destination path
    """
    with open(output_path, "w") as f:
        for cert in ordered_certs:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode())


def validate_certs_and_verify_chain(ordered_certs: List[crypto.X509]):
    """
    verify the given certificate chain and validate the certificates integrity
    """
    store = crypto.X509Store()
    for cert in ordered_certs[1:]:  # Add all but the leaf cert to the store
        store.add_cert(cert)

    # Create a context using the store
    store_ctx = crypto.X509StoreContext(store, ordered_certs[0])

    try:
        # Verify the certificate
        store_ctx.verify_certificate()
    except crypto.X509StoreContextError as e:
        raise ValueError(f"validate_certs_and_verify_chain: Certificate chain validation failed: {str(e)}")


def validate_certs_chain(chain_str: str = None, chain_path: str = None, output_leaf_path: str = '', output_chain_path: str = ''):
    assert len([param for param in [chain_str, chain_path] if
                param is not None]) == 1, f'validate_certs_chain: must give exactly one param of [chain_str, chain_path]'

    try:
        with step('Parse the certs out of the chain'):
            certs: List[crypto.X509] = parse_certs_str(chain_str) if chain_str else parse_certs_file(chain_path)

        with step('Construct an ordered chain'):
            ordered_certs = order_certs(certs)

        if output_leaf_path:
            with step('Save the leaf cert into a file'):
                save_ordered_chain([ordered_certs[0]], output_leaf_path)

        if output_chain_path:
            with step('Save the ordered chain into a file'):
                save_ordered_chain(ordered_certs, output_chain_path)

        with step('Validate and verify the integrity of the chain'):
            validate_certs_and_verify_chain(ordered_certs)

        log("SUCCESS: Certificate chain processed, ordered, and verified successfully")
        return True

    except Exception as e:
        log(f"ERROR: {str(e)}\n{traceback.format_exc()}")
        raise


def main():
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_files_dir = os.path.join(os.path.dirname(cur_dir), 'tmp_files')

    output_ordered_chain_path = os.path.join(tmp_files_dir, 'ordered_chain.pem')
    output_leaf_path = os.path.join(tmp_files_dir, 'leaf.pem')
    input_chain_file = os.path.join(tmp_files_dir, 'chain-ERoT_BMC_0.pem')

    validate_certs_chain(chain_path=input_chain_file, output_leaf_path=output_leaf_path, output_chain_path=output_ordered_chain_path)


if __name__ == '__main__':
    main()
