import os
from typing import List

import OpenSSL
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.client_verification.utils import printtt, \
    CLIENT_VERIFICATION_DIR

CERT_START = "-----BEGIN CERTIFICATE-----"
CERT_END = "-----END CERTIFICATE-----"

CERT_CHAIN_VALIDATION_ERR = 'certificate chain validation failed'


def printt(msg):
    printtt(msg, 'CERTS')


class CertChainTool:
    def __init__(self, cert_chain=None, path_to_save_splitted_certs: str = ''):
        self.cert_chain_list: List[str] = None
        if isinstance(cert_chain, list):
            self.cert_chain_list = cert_chain
        elif isinstance(cert_chain, str):
            self.cert_chain_list = self.split_cert_chain_str_to_list(cert_chain, path_to_save_splitted_certs)
        printt('created cert chain tool instance')

    def get_cert_chain_content_str_from_file(self, cert_chain_file) -> str:
        printt('read cert chain file')
        with open(cert_chain_file, "r") as chain_file:
            chain_str = chain_file.read()
        printt('OK')
        printt('short validate to the format')
        clean_content = chain_str.strip()
        assert (clean_content.startswith(CERT_START) and clean_content.endswith(
            CERT_END)), f'{CERT_CHAIN_VALIDATION_ERR}: cert chain file has wrong format - must start with {CERT_START} and end with {CERT_END}\nfile path: {cert_chain_file}\ncontent:\n{clean_content}'
        printt('OK')
        return chain_str

    def split_cert_chain_str_to_list(self, chain_str: str, path_to_save_certs: str = '') -> List[str]:
        printt('split cert chain into list of cert strings')
        chain_str = chain_str.replace("\n", "")
        result = chain_str.split(CERT_START)
        final_result = [item.split(CERT_END) for item in result]

        flattened_result = [item for sublist in final_result for item in sublist]
        result_content = [item.strip() for item in flattened_result if item.strip()]
        final_result = []
        for cert in result_content:
            final_result.append(CERT_START + "\n" + cert + "\n" + CERT_END + "\n")
        printt('OK')

        self.cert_chain_list = final_result

        if path_to_save_certs:
            printt(f'save splitted certs into {path_to_save_certs}')
            os.makedirs(path_to_save_certs, exist_ok=True)
            for i, cert in enumerate(final_result):
                cert_filename = f'cert-{i}.pem'
                printt(f'save cert #{i} in: {cert_filename}')
                cert_file_path = os.path.join(path_to_save_certs, cert_filename)
                with open(cert_file_path, 'w') as file:
                    file.write(cert)
                printt('OK')

        return final_result

    def are_issuers_and_signatures_valid(self, cert_chain: List[str] = None) -> bool:
        cert_chain = cert_chain or self.cert_chain_list
        assert cert_chain, f'{CERT_CHAIN_VALIDATION_ERR}: there is no cert chain list provided'

        if len(cert_chain) < 2:
            printt(f"{CERT_CHAIN_VALIDATION_ERR}: Certificate chain must contain at least two certificates")
            return False

        printt('load certificates into list')
        certs = []
        for cert_pem in cert_chain:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            certs.append(cert)
        printt('OK')

        for i in range(len(certs) - 1):
            issuer_cert = certs[i]
            subject_cert = certs[i + 1]

            printt(f'verify cert #{i + 1} issued by cert #{i}')
            if issuer_cert.subject != subject_cert.issuer:
                printt(f"Certificate at index {i + 1} is not issued by certificate at index {i}")
                return False
            printt(f'OK')

            try:
                printt(f'verify signature of cert #{i + 1}')
                issuer_public_key = issuer_cert.public_key()
                issuer_public_key.verify(
                    subject_cert.signature,
                    subject_cert.tbs_certificate_bytes,
                    ec.ECDSA(subject_cert.signature_hash_algorithm),
                    # padding.PKCS1v15(),
                    # subject_cert.signature_hash_algorithm
                )
                printt(f'OK')
            except InvalidSignature:
                printt(f"Invalid signature for certificate at index {i + 1}")
                return False

        printt("Certificate chain verification successful")
        return True

    def validate_cert_chain(self, cert_chain: List[str] = None):
        cert_chain = cert_chain or self.cert_chain_list
        assert cert_chain, f'{CERT_CHAIN_VALIDATION_ERR}: there is no cert chain list provided'

        assert len(
            cert_chain) >= 2, f'{CERT_CHAIN_VALIDATION_ERR}: provided cert chain must have at least 2 certificates'

        try:
            printt('Step: load certificates of the chain')
            loaded_certs = []
            for i, cert_str in enumerate(cert_chain):
                printt(f'load cert #{i}')
                loaded_certs.append(OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert_str))
                printt('OK')

            printt('Step: validate the chain - add to store only after verifying trusted cert')
            printt('creating trusted store')
            trusted_store = OpenSSL.crypto.X509Store()
            printt('OK')
            printt('add cert #0 (root) to the trusted store')
            trusted_store.add_cert(loaded_certs[0])
            printt('OK')
            for i in range(1, len(loaded_certs)):
                cert_str = loaded_certs[i]
                printt(f'create context for verifying cert #{i}')
                store_ctx = OpenSSL.crypto.X509StoreContext(trusted_store, cert_str)
                printt('OK')
                printt(f'verify cert #{i} is trusted')
                printt(store_ctx.verify_certificate())
                printt('OK')
                printt(f'add cert #{i} to trusted store')
                trusted_store.add_cert(cert_str)
                printt('OK')

            return True
        except Exception as e:
            raise ValueError(f'{CERT_CHAIN_VALIDATION_ERR}: {e}')


def main():
    TEST_ID = 2
    chain_filename = 'bmc_nvue_cert_chain.pem'
    # chain_filename = 'good_chain.pem'

    chain = CertChainTool()
    printt('\n\n')
    chain_str = chain.get_cert_chain_content_str_from_file(os.path.join(CLIENT_VERIFICATION_DIR, chain_filename))
    printt('\n\n')
    chain_list = chain.split_cert_chain_str_to_list(chain_str, os.path.join(CLIENT_VERIFICATION_DIR, f'test-{TEST_ID}'))

    # perform checks
    printt('\n\n')
    try:
        chain.validate_cert_chain()
        check_1_res = True
    except Exception:
        check_1_res = False
    printt('\n\n')

    try:
        chain.validate_cert_chain()
        check_2_res = True
    except Exception:
        check_2_res = False

    # print results
    printt('\n\n')
    printt(f'check1: {check_1_res}')
    printt(f'check2: {check_2_res}')


if __name__ == '__main__':
    main()
