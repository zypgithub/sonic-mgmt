import logging
import os
import subprocess
import tempfile
from typing import Union

YEAR = 365
DEFAULT_DN = 'NVOS'
CA_CN = 'NVOS-CA'


class CertificateGenerator:

    @classmethod
    def generate_cert(cls, cert_location: str, cert_name: str, ip: str = '', dn: str = '',
                      new_ca_path: str = '', new_ca_name: str = '', p12_pass: str = '', existing_ca_public: str = '',
                      existing_ca_private: str = '', expiration_years: int = 10, stdout_func=logging.info):
        """
        create new x509 ca/cert with given properties

        manual steps:
        -------------
        CA_FILENAME="ca"
        CA_CN="NVOS-CA"
        CERT_DN="juliet-126"
        CERT_IP="10.7.148.126"
        CERT_FILENAME="cert"
        P12_PASS="mypass"
        EXP=3650

        openssl genrsa -out $CA_FILENAME.key 2048
        openssl req -new -x509 -days $EXP -key $CA_FILENAME.key -subj /C=CN/ST=GD/L=SZ-Inc/CN=$CA_CN -out $CA_FILENAME.crt
        openssl req -newkey rsa:2048 -nodes -keyout $CERT_FILENAME.key -subj /C=CN/ST=GD/L=SZ-Inc/CN=$CERT_DN -out $CERT_FILENAME.csr
        openssl x509 -req -in $CERT_FILENAME.csr -CA $CA_FILENAME.crt -CAkey $CA_FILENAME.key -CAcreateserial -out $CERT_FILENAME.crt -days $EXP -extfile <(printf "subjectAltName=DNS:$CERT_DN,IP:$CERT_IP")
        openssl x509 -in $CERT_FILENAME.crt -out $CERT_FILENAME.pem -outform PEM
        openssl pkcs12 -export -out $CERT_FILENAME.p12 -in $CERT_FILENAME.pem -inkey $CERT_FILENAME.key -passout pass:$P12_PASS

        chmod +r ./*
        -------------

        @param ca_path: if ca_path does not exist - raise.
            if it is file, use it as existing ca (just create new cert issued by this ca).
            if dir - create and use new ca saved in this location.
        """

        stdout_func('validate parameters')
        assert os.path.exists(cert_location), f"given location for cert doesn't exist: {cert_location}"
        target_device_props = [ip, dn]
        assert len(
            [prop for prop in target_device_props if prop]) > 0, "none of [ip, dn] given. at least one must be given"
        assert cert_name, "empty string as cert name not allowed"
        assert expiration_years > 0, f"given certificate expiration not allowed: {expiration_years}. must give positive number"

        existing_ca_props = [existing_ca_public, existing_ca_private]
        existing_ca_props = [prop for prop in existing_ca_props if prop]
        new_ca_props = [new_ca_path, new_ca_name]
        new_ca_props = [prop for prop in new_ca_props if prop]
        assert (new_ca_props and not existing_ca_props) or (existing_ca_props and not new_ca_props), \
            f"must give info for new OR existing CA (but not both)"

        expiration = expiration_years * YEAR

        ######################

        # Prepare CA
        ca_private_path, ca_public_path = cls.__prepare_ca(existing_ca_private, existing_ca_public, expiration,
                                                           new_ca_name, new_ca_path, new_ca_props, stdout_func)
        stdout_func('verify CA with itself')
        cls.__openssl_verify_cert_with_ca(ca_public_path, ca_public_path, stdout_func)

        # Generate and sign cert using CA
        cert_csr_path, cert_private_path = cls.__gen_cert_csr_and_private_key(cert_location, cert_name, dn, stdout_func)
        cert_crt_public_path = cls.__issue_and_sign_public_cert(ca_private_path, ca_public_path, cert_csr_path,
                                                                cert_location, cert_name, dn, expiration, ip,
                                                                stdout_func)
        stdout_func('verify generated cert crt with CA')
        cls.__openssl_verify_cert_with_ca(ca_public_path, cert_crt_public_path, stdout_func)

        # Convert public cert to PEM format
        cert_public_pem_path = cls.__convert_crt_to_pem(cert_crt_public_path, cert_location, cert_name, stdout_func)
        stdout_func('verify generated cert pem with CA')
        cls.__openssl_verify_cert_with_ca(ca_public_path, cert_public_pem_path, stdout_func)

        # Create p12 bundle of the cert
        cls.__create_cert_p12_bundle(cert_location, cert_name, cert_private_path, cert_public_pem_path, p12_pass,
                                     stdout_func)

    @classmethod
    def generate_ca(cls, new_ca_dir, new_ca_name, expiration, stdout_func=logging.info):
        cls.__verify_file(new_ca_dir, 'new CA', True)
        assert new_ca_name, "empty string as CA name not allowed"

        stdout_func('generate new CA')
        ca_private_filename = f'{new_ca_name}.key'
        ca_private_path = os.path.join(new_ca_dir, ca_private_filename)
        ca_public_filename = f'{new_ca_name}.crt'
        ca_public_path = os.path.join(new_ca_dir, ca_public_filename)
        gen_new_ca_private_key_cmd = f'openssl genrsa -out {ca_private_path} 2048'
        cls.__run_cmd_popen(gen_new_ca_private_key_cmd, stdout_func)
        cls.__chmod_for_reading(ca_private_path, stdout_func)
        gen_new_ca_public_key = f'openssl req -new -x509 -days {expiration} -key {ca_private_path} -subj /C=CN/ST=GD/L=SZ-Inc/CN={CA_CN} -out {ca_public_path}'
        cls.__run_cmd_popen(gen_new_ca_public_key, stdout_func)
        cls.__chmod_for_reading(ca_private_path, stdout_func)

        stdout_func('verify CA with itself')
        cls.__openssl_verify_cert_with_ca(ca_public_path, ca_public_path, stdout_func)

        return ca_private_path, ca_public_path

    @classmethod
    def __prepare_ca(cls, existing_ca_private, existing_ca_public, expiration, new_ca_name, new_ca_path, new_ca_props,
                     stdout_func):
        stdout_func('prepare CA')
        if new_ca_props:
            ca_private_path, ca_public_path = cls.generate_ca(new_ca_path, new_ca_name, expiration, stdout_func)
        else:
            stdout_func('use given existing CA')
            ca_private_path, ca_public_path = existing_ca_private, existing_ca_public

        stdout_func('verify CA files exist')
        cls.__verify_file(ca_public_path, 'existing CA public key')
        cls.__verify_file(ca_private_path, 'existing CA private key')
        return ca_private_path, ca_public_path

    @classmethod
    def __gen_cert_csr_and_private_key(cls, cert_location, cert_name, dn, stdout_func):
        stdout_func('generate certificate csr and private key')
        cert_csr_filename = f'{cert_name}.csr'
        cert_csr_path = os.path.join(cert_location, cert_csr_filename)
        cert_private_filename = f'{cert_name}.key'
        cert_private_path = os.path.join(cert_location, cert_private_filename)
        cn = dn or DEFAULT_DN
        gen_cert_key_cmd = f'openssl req -newkey rsa:2048 -nodes -keyout {cert_private_path} -subj /C=CN/ST=GD/L=SZ-Inc/CN={cn} -out {cert_csr_path}'
        cls.__run_cmd_popen(gen_cert_key_cmd, stdout_func, ignore_stderr=True)
        cls.__verify_file(cert_csr_path, 'generated certificate csr')
        cls.__verify_file(cert_private_path, 'generated certificate key')
        cls.__chmod_for_reading(cert_csr_path, stdout_func)
        cls.__chmod_for_reading(cert_private_path, stdout_func)
        return cert_csr_path, cert_private_path

    @classmethod
    def __issue_and_sign_public_cert(cls, ca_private_path, ca_public_path, cert_csr_path, cert_location, cert_name, dn,
                                     expiration, ip, stdout_func):
        stdout_func('generate and sign/issue the public certificate')
        cert_public_filename = f'{cert_name}.crt'
        cert_public_path = os.path.join(cert_location, cert_public_filename)
        target_device_props = {'DNS': dn, 'IP': ip}
        target_device_props = {k: v for k, v in target_device_props.items() if v}
        subject_alt_name = ','.join([f'{k}:{v}' for k, v in target_device_props.items()])
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write(f'subjectAltName={subject_alt_name}')
            tmp_file.flush()
            gen_and_issue_cert_public_cmd = f'openssl x509 -req -in {cert_csr_path} -CA {ca_public_path} -CAkey {ca_private_path} -CAcreateserial -out {cert_public_path} -days {expiration} -extfile {tmp_file.name}'
        cls.__run_cmd_popen(gen_and_issue_cert_public_cmd, stdout_func, ignore_stderr=True)
        cls.__verify_file(cert_public_path, 'generated certificate crt')
        cls.__chmod_for_reading(cert_public_path, stdout_func)
        return cert_public_path

    @classmethod
    def __convert_crt_to_pem(cls, cert_crt_public_path, cert_location, cert_name, stdout_func):
        stdout_func('convert public crt to PEM')
        cert_public_pem_filename = f'{cert_name}.pem'
        cert_public_pem_path = os.path.join(cert_location, cert_public_pem_filename)
        convert_crt_to_pem_cmd = f'openssl x509 -in {cert_crt_public_path} -out {cert_public_pem_path} -outform PEM'
        cls.__run_cmd_popen(convert_crt_to_pem_cmd, stdout_func, ignore_stderr=True)
        cls.__verify_file(cert_public_pem_path, 'generated certificate crt')
        cls.__chmod_for_reading(cert_public_pem_path, stdout_func)
        return cert_public_pem_path

    @classmethod
    def __create_cert_p12_bundle(cls, cert_location, cert_name, cert_private_path, cert_public_pem_path, p12_pass,
                                 stdout_func):
        stdout_func('create p12 bundle of the generated certificate')
        p12_bundle_filename = f'{cert_name}.p12'
        p12_bundle_path = os.path.join(cert_location, p12_bundle_filename)
        create_p12_bundle_cmd = f'openssl pkcs12 -export -out {p12_bundle_path} -in {cert_public_pem_path} -inkey {cert_private_path} -passout pass:{p12_pass}'
        cls.__run_cmd_popen(create_p12_bundle_cmd, stdout_func, ignore_stderr=True)
        cls.__verify_file(p12_bundle_path, 'generated certificate crt')
        cls.__chmod_for_reading(p12_bundle_path, stdout_func)

    @classmethod
    def __openssl_verify_cert_with_ca(cls, ca_file, cert_file, stdout_func):
        verify_cmd = f'openssl verify -CAfile {ca_file} {cert_file}'
        cls.__run_cmd_popen(verify_cmd, stdout_func, 'OK')

    @classmethod
    def __verify_file(cls, file, purpose, is_dir=False):
        assert os.path.exists(file), f"given {purpose} path doesn't exist: {file}"
        if is_dir:
            assert os.path.isdir(file), f"given {purpose} path isn't a directory: {file}"
        else:
            assert os.path.isfile(file), f"{purpose} isn't a file: {file}"

    @classmethod
    def __chmod_for_reading(cls, file, stdout_func):
        chmod_cmd = f'chmod +r {file}'
        cls.__run_cmd_popen(chmod_cmd, stdout_func)

    @classmethod
    def __run_cmd_popen(cls, cmd: Union[str, list], stdout_func, expect='.*', ignore_stderr=False):
        cmd_str, cmd_list = (cmd, cmd.split(' ')) if isinstance(cmd, str) else (
            ' '.join([str(item) for item in cmd]), cmd)

        stdout_func(f'run: {cmd_str}')
        # Run the bash script
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=10)

        # Print the output
        stdout_func(result.stdout)

        # Print any error messages
        if ignore_stderr:
            if result.stderr:
                assert 'error' not in result.stderr, f'error has occurred\nout: {result.stdout}\nerr: {result.stderr}'
        elif result.returncode != 0:
            stdout_func("Returned code is not 0. Errors:")
            stdout_func(result.stderr)
            raise ValueError(f'error has occurred\nout: {result.stdout}\nerr: {result.stderr}')


def __try_generator():
    # TODO: configure as desired
    cert_location: str = '/auto/sw_system_project/NVOS_INFRA/security/verification/certs/test_certs/cert4/cert'
    cert_name: str = 'cert'
    ip: str = '10.7.148.126'
    dn: str = 'juliet-126'
    expiration_years: int = 10
    new_ca_path: str = '/auto/sw_system_project/NVOS_INFRA/security/verification/certs/test_certs/cert4/ca'
    new_ca_name: str = 'ca'
    existing_ca_public: str = ''
    existing_ca_private: str = ''
    p12_pass: str = 'secret'

    CertificateGenerator.generate_cert(cert_location, cert_name, ip, dn, new_ca_path, new_ca_name, p12_pass,
                                       existing_ca_public, existing_ca_private, expiration_years, print)


if __name__ == '__main__':
    __try_generator()
