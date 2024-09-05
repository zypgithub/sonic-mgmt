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
