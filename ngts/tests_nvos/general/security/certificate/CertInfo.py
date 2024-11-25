""" Class to describe info about certificate in test environment """


class CertInfo:
    def __init__(self, name, info, private, public, p12_bundle, p12_password, dn, ip, cacert):
        self.name: str = name
        self.info: str = info
        self.private: str = private
        self.public: str = public
        self.p12_bundle: str = p12_bundle
        self.p12_password: str = p12_password
        self.dn: str = dn
        self.ip: str = ip
        self.cacert: str = cacert

    def copy(self, new_name: str = '') -> 'CertInfo':
        return CertInfo(new_name or self.name, self.info, self.private, self.public, self.p12_bundle, self.p12_password, self.dn, self.ip, self.cacert)

    @property
    def private_filename(self) -> str:
        return None if not self.private else self.private.split('/')[-1]

    @property
    def public_filename(self) -> str:
        return None if not self.public else self.public.split('/')[-1]

    @property
    def bundle_filename(self) -> str:
        return None if not self.p12_bundle else self.p12_bundle.split('/')[-1]

    @property
    def cacert_filename(self) -> str:
        return None if not self.cacert else self.cacert.split('/')[-1]

    @property
    def cacert_name(self) -> str:
        return f'cacert-of-{self.name}'

    def get_cert_content_str(self) -> str:
        with open(self.public, 'r') as cert_file:
            cert_content = cert_file.read().strip()

        with open(self.private, 'r') as key_file:
            key_content = key_file.read().strip()

        combined_content = f"{cert_content}\n{key_content}"
        return combined_content

    def get_ca_content_str(self) -> str:
        with open(self.cacert, 'r') as key_file:
            content = key_file.read().strip()
        return content
