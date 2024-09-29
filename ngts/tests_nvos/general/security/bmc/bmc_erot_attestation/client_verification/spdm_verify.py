import hashlib
import os.path

import ecdsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import load_pem_x509_certificate

from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.client_verification.spdm_measurements import \
    SPDMMeasurements
from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.client_verification.utils import printtt, \
    CLIENT_VERIFICATION_DIR

CLIENT_VERIFICATION_ERR = 'client verification failed'


def printt(msg):
    printtt(msg, 'VERIFIER')


def load_measurements(filename, output=False):
    meas = SPDMMeasurements(filename)

    no_leftovers = meas.parse()

    if (output):
        if no_leftovers:
            printt("OK: All data consumed. This is expected.")
        else:
            printt(
                "WARNING: Leftover data detected! You have provided more than just signed measurements. Check your input!")
        meas.show_manifest()
        meas.show_req_nonce()
        meas.show_resp_nonce()

    return meas


def measurements_sig_verify(measurements, public_key):
    message = measurements.get_signed_content()
    sig = measurements.get_signature()

    verifier = ecdsa.VerifyingKey.from_string(public_key, curve=ecdsa.curves.NIST384p)

    verifier.verify(sig, message, hashlib.sha384)
    # try:
    #     verifier.verify(sig, message, hashlib.sha384)
    #     return True
    # except ecdsa.BadSignatureError:
    #     return False
    # return False


def load_pubkey(filename):
    # This is a manually extracted pubkey from the BMC measurements, I used it to figure out how to extract a key from the cert.
    # pubkey_test = "0406515db1deb97236302e79aa76fcce3964d4b27c8492e7f3fcca4fb01059d274b9e759af4599fcc6993dcc85ba8b608074297d6e4f0de47e25d1be18f64144c207a9f1bcd6252d9440ec7ebdb473ca63872affc05ea578267d7261f326b00a07"
    # pubkey_test = bytes.fromhex(pubkey_test)

    with open(filename, "rb") as cert_file:
        cert_str = cert_file.read()
    cert_obj = load_pem_x509_certificate(cert_str, default_backend())
    public_key = cert_obj.public_key()
    public_key_bytes = public_key.public_bytes(encoding=serialization.Encoding.DER,
                                               format=serialization.PublicFormat.SubjectPublicKeyInfo)
    # This is a bit of black magic: The extracted, DER encoded key has a prefix before the actual public key bytes. Experimentally, this is the first 23 bytes, and then the key bytes follow.
    pubkey = public_key_bytes[23:]
    # printt(pubkey)
    return pubkey


def load_nonce(filename):
    with open(filename, "r") as cert_file:
        nonce = cert_file.read()
    return nonce


def validate_request_nonce_against_expected(meas, nonce_file):
    expected_nonce = load_nonce(nonce_file).strip()
    req_nonce = meas.get_req_nonce().hex().strip()
    printt(
        f'\n\n==================\nexpected nonce:\t{expected_nonce}\nactual nonce:\t{req_nonce}\n==================\n\n')
    if req_nonce != expected_nonce:
        printt(
            f'{CLIENT_VERIFICATION_ERR}: request nonce is not as expected.\nexpected: {expected_nonce}\nactual: {req_nonce}')
        raise ValueError(
            f'{CLIENT_VERIFICATION_ERR}: request nonce is not as expected.\nexpected: {expected_nonce}\nactual: {req_nonce}')
    else:
        printt('request nonce is OK')


# Currently doesn't do a nonce comparison, so nonce_file is not used.
def verify(meas_file, key_file, nonce_file=None, output=False):
    if (output):
        printt("Verifying measurements from file: " + meas_file)
        printt("Using key from file: " + key_file)
    meas = load_measurements(meas_file, output)
    pubkey = load_pubkey(key_file)

    if nonce_file:
        validate_request_nonce_against_expected(meas, nonce_file)

    # if (output):
    #    # Print raw data
    #    meas.show_data()
    #    # Print signed content
    #    meas.show_signed_content()
    #    # Print signature bytes
    #    meas.show_signature()

    measurements_sig_verify(meas, pubkey)


def run_spdm_measurements_verification(measurements_json_file, leaf_cert_file, nonce_file, expect_success: bool):
    err = ''
    try:
        verify(measurements_json_file, leaf_cert_file, nonce_file)
        success = True
    except Exception as e:
        success = False
        err = e

    if success == expect_success:
        printt("\n[PASS!] Signature Verification of Signature Successful.\n\n")
    else:
        printt("\n[FAIL!] Signature Verification of Signature Failed.\n\n")
        if success:
            printt(f'{CLIENT_VERIFICATION_ERR}: spdm measurements verification passed but expected to fail')
            raise ValueError(f'{CLIENT_VERIFICATION_ERR}: spdm measurements verification passed but expected to fail')
        else:
            printt(f'{CLIENT_VERIFICATION_ERR}: spdm measurements verification failed but expected to pass: {err}')
            raise ValueError(
                f'{CLIENT_VERIFICATION_ERR}: spdm measurements verification failed but expected to pass: {err}')


if __name__ == '__main__':
    os.path.join(CLIENT_VERIFICATION_DIR, 'bmc_nvue_meas.json')
    meas_file = os.path.join(CLIENT_VERIFICATION_DIR, 'bmc_nvue_meas.json')
    key_file = os.path.join(CLIENT_VERIFICATION_DIR, 'bmc_nvue_leaf_cert.pem')
    nonce_file = None

    # Start praying here! Verifying signature!
    run_spdm_measurements_verification(meas_file, key_file, nonce_file, True)

    # Load Bad Measurements JSON output file
    meas_file = os.path.join(CLIENT_VERIFICATION_DIR, 'bmc_nvue_meas_bad_sig.json')
    key_file = os.path.join(CLIENT_VERIFICATION_DIR, 'bmc_nvue_leaf_cert.pem')
    nonce_file = None

    # Keep praying here! Verifying signature!
    run_spdm_measurements_verification(meas_file, key_file, nonce_file, True)
