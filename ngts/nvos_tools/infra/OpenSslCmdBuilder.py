import shlex
from typing import List, Optional, Union


class OpenSslCmdBuilder:
    """
    A builder class for constructing OpenSSL commands
    """

    def __init__(self):
        self._command: List[str] = ["openssl"]
        self._subcommand: Optional[str] = None

    def subcommand(self, name: str) -> "OpenSslCmdBuilder":
        """Sets the main subcommand (e.g., 'req', 'x509')."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = name
        self._command.append(name)
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> "OpenSslCmdBuilder":
        """Adds a generic option flag or key-value option. Prefer specific methods where available."""
        self._command.append(f"-{key}")
        if value is not None:
            self._command.append(str(value))
        return self

    def subject(
        self,
        C: Optional[str] = None,
        ST: Optional[str] = None,
        L: Optional[str] = None,
        O: Optional[str] = None,
        OU: Optional[str] = None,
        CN: Optional[str] = None,
    ) -> "OpenSslCmdBuilder":
        """
        Adds the '-subj' option with the specified components.
        Example: /C=CN/ST=GD/L=SZ-Inc/CN=MyCN
        """
        subj_parts = []
        if C:
            subj_parts.append(f"C={C}")
        if ST:
            subj_parts.append(f"ST={ST}")
        if L:
            subj_parts.append(f"L={L}")
        if O:
            subj_parts.append(f"O={O}")
        if OU:
            subj_parts.append(f"OU={OU}")
        if CN:
            subj_parts.append(f"CN={CN}")

        if not subj_parts:
            raise ValueError("Subject cannot be empty when specified.")

        subj_string = "/" + "/".join(subj_parts)
        return self.option("subj", subj_string)

    def positional_arg(self, value: Union[str, int]) -> "OpenSslCmdBuilder":
        """Adds a positional argument to the command."""
        self._command.append(str(value))
        return self

    # --- Specific Option Methods ---

    def passout(self, method: str, arg: str) -> "OpenSslCmdBuilder":
        """Adds the '-passout' option (e.g., 'pass:password')."""
        return self.option("passout", f"{method}:{arg}")

    def keypbe(self, encryption: str) -> "OpenSslCmdBuilder":
        return self.option("keypbe", encryption)

    def certpbe(self, encryption: str) -> "OpenSslCmdBuilder":
        return self.option("certpbe", encryption)

    def newkey(self, spec: str) -> "OpenSslCmdBuilder":
        return self.option("newkey", spec)

    def nodes(self) -> "OpenSslCmdBuilder":
        return self.option("nodes")

    def keyout(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("keyout", path)

    def out(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("out", path)

    def new(self) -> "OpenSslCmdBuilder":
        return self.option("new")

    def x509(self) -> "OpenSslCmdBuilder":  # As an option, not subcommand
        return self.option("x509")

    def days(self, num_days: Union[str, int]) -> "OpenSslCmdBuilder":
        return self.option("days", num_days)

    def key(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("key", path)

    def req(self) -> "OpenSslCmdBuilder":  # As an option, not subcommand
        return self.option("req")

    def in_file(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("in", path)

    def CA(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("CA", path)

    def CAkey(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("CAkey", path)

    def CAcreateserial(self) -> "OpenSslCmdBuilder":
        return self.option("CAcreateserial")

    def extfile(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("extfile", path)

    def extensions(self, name: str) -> "OpenSslCmdBuilder":
        return self.option("extensions", name)

    def outform(self, format: str) -> "OpenSslCmdBuilder":
        return self.option("outform", format)

    def export(self) -> "OpenSslCmdBuilder":
        return self.option("export")

    def inkey(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("inkey", path)

    def CAfile(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("CAfile", path)

    def revoke(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("revoke", path)

    def keyfile(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("keyfile", path)

    def cert(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("cert", path)

    def create_serial(self) -> "OpenSslCmdBuilder":
        return self.option("create_serial")

    def config(self, path: str) -> "OpenSslCmdBuilder":
        return self.option("config", path)

    def gencrl(self) -> "OpenSslCmdBuilder":
        return self.option("gencrl")

    def build(self, as_string: bool = True) -> Union[str, List[str]]:
        """
        Constructs the final command.

        Args:
            as_string: If True (default), returns the command as a single, shell-quoted string.
                       If False, returns a list of command parts.

        Returns:
            The constructed command string or list.
        """
        if not self._subcommand:
            raise ValueError("OpenSSL subcommand must be set before building.")

        if as_string:
            return " ".join(shlex.quote(part) for part in self._command)
        else:
            return self._command

    def get_command_list(self) -> List[str]:
        """Builds the command and returns it as a list of arguments."""
        return self.build(as_string=False)  # type: ignore

    def get_command_string(self) -> str:
        """Builds the command and returns it as a shell-quoted string."""
        return self.build(as_string=True)  # type: ignore


class OpenSslSClientBuilder(OpenSslCmdBuilder):
    """
    Builder specifically for OpenSSL s_client commands.

    Example usage:
        cmd = (
            OpenSslSClientBuilder("example.com", 443)
            .CAfile("/path/to/ca.crt")
            .cert("/path/to/client.crt")
            .key("/path/to/client.key")
            .alpn("h2")
            .build()
        )
    """

    def __init__(self, host: str, port: Union[str, int]):
        """
        Initialize s_client builder with connection target.

        Args:
            host: Target hostname or IP address.
            port: Target port number.
        """
        super().__init__()
        self.subcommand("s_client")
        self.connect(host, port)

    def connect(self, host: str, port: Union[str, int]) -> "OpenSslSClientBuilder":
        """Adds the '-connect host:port' option."""
        return self.option("connect", f"{host}:{port}")

    def alpn(self, protocol: str) -> "OpenSslSClientBuilder":
        """Adds the '-alpn' option for ALPN protocol negotiation."""
        return self.option("alpn", protocol)

    def servername(self, name: str) -> "OpenSslSClientBuilder":
        """Adds the '-servername' option for SNI (Server Name Indication)."""
        return self.option("servername", name)

    def verify(self, depth: Union[str, int]) -> "OpenSslSClientBuilder":
        """Adds the '-verify depth' option."""
        return self.option("verify", depth)

    def verify_return_error(self) -> "OpenSslSClientBuilder":
        """Adds '-verify_return_error' to return error on verification failure."""
        return self.option("verify_return_error")

    def quiet(self) -> "OpenSslSClientBuilder":
        """Adds '-quiet' to suppress session and certificate output."""
        return self.option("quiet")

    def brief(self) -> "OpenSslSClientBuilder":
        """Adds '-brief' for brief output."""
        return self.option("brief")

    def tls1_2(self) -> "OpenSslSClientBuilder":
        """Forces TLS 1.2 protocol."""
        return self.option("tls1_2")

    def tls1_3(self) -> "OpenSslSClientBuilder":
        """Forces TLS 1.3 protocol."""
        return self.option("tls1_3")

    def no_ssl3(self) -> "OpenSslSClientBuilder":
        """Disables SSL3."""
        return self.option("no_ssl3")

    def no_tls1(self) -> "OpenSslSClientBuilder":
        """Disables TLS 1.0."""
        return self.option("no_tls1")

    def no_tls1_1(self) -> "OpenSslSClientBuilder":
        """Disables TLS 1.1."""
        return self.option("no_tls1_1")

    def showcerts(self) -> "OpenSslSClientBuilder":
        """Adds '-showcerts' to show full certificate chain."""
        return self.option("showcerts")

    def status(self) -> "OpenSslSClientBuilder":
        """Adds '-status' to request OCSP stapling."""
        return self.option("status")

    def CAfile(self, path: str) -> "OpenSslSClientBuilder":
        """Adds the '-CAfile' option for CA certificate."""
        return self.option("CAfile", path)

    def cert(self, path: str) -> "OpenSslSClientBuilder":
        """Adds the '-cert' option for client certificate."""
        return self.option("cert", path)

    def key(self, path: str) -> "OpenSslSClientBuilder":
        """Adds the '-key' option for client private key."""
        return self.option("key", path)
