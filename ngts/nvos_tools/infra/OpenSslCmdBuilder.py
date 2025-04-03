import shlex
from typing import List, Optional, Union


class OpenSslCmdBuilder:
    """
    A builder class for constructing OpenSSL commands
    """

    def __init__(self):
        self._command: List[str] = ["openssl"]
        self._subcommand: Optional[str] = None

    def subcommand(self, name: str) -> 'OpenSslCmdBuilder':
        """Sets the main subcommand (e.g., 'req', 'x509')."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = name
        self._command.append(name)
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'OpenSslCmdBuilder':
        """Adds a generic option flag or key-value option. Prefer specific methods where available."""
        self._command.append(f"-{key}")
        if value is not None:
            self._command.append(str(value))
        return self

    def subject(self, C: Optional[str] = None, ST: Optional[str] = None, L: Optional[str] = None,
                O: Optional[str] = None, OU: Optional[str] = None, CN: Optional[str] = None) -> 'OpenSslCmdBuilder':
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

    def positional_arg(self, value: Union[str, int]) -> 'OpenSslCmdBuilder':
        """Adds a positional argument to the command."""
        self._command.append(str(value))
        return self

    # --- Specific Option Methods ---

    def passout(self, method: str, arg: str) -> 'OpenSslCmdBuilder':
        """Adds the '-passout' option (e.g., 'pass:password')."""
        return self.option("passout", f"{method}:{arg}")

    def newkey(self, spec: str) -> 'OpenSslCmdBuilder':
        return self.option("newkey", spec)

    def nodes(self) -> 'OpenSslCmdBuilder':
        return self.option("nodes")

    def keyout(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("keyout", path)

    def out(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("out", path)

    def new(self) -> 'OpenSslCmdBuilder':
        return self.option("new")

    def x509(self) -> 'OpenSslCmdBuilder':  # As an option, not subcommand
        return self.option("x509")

    def days(self, num_days: Union[str, int]) -> 'OpenSslCmdBuilder':
        return self.option("days", num_days)

    def key(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("key", path)

    def req(self) -> 'OpenSslCmdBuilder':  # As an option, not subcommand
        return self.option("req")

    def in_file(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("in", path)

    def CA(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("CA", path)

    def CAkey(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("CAkey", path)

    def CAcreateserial(self) -> 'OpenSslCmdBuilder':
        return self.option("CAcreateserial")

    def extfile(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("extfile", path)

    def extensions(self, name: str) -> 'OpenSslCmdBuilder':
        return self.option("extensions", name)

    def outform(self, format: str) -> 'OpenSslCmdBuilder':
        return self.option("outform", format)

    def export(self) -> 'OpenSslCmdBuilder':
        return self.option("export")

    def inkey(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("inkey", path)

    def CAfile(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("CAfile", path)

    def revoke(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("revoke", path)

    def keyfile(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("keyfile", path)

    def cert(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("cert", path)

    def create_serial(self) -> 'OpenSslCmdBuilder':
        return self.option("create_serial")

    def config(self, path: str) -> 'OpenSslCmdBuilder':
        return self.option("config", path)

    def gencrl(self) -> 'OpenSslCmdBuilder':
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
