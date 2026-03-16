import logging
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple, Union

from ngts.nvos_tools.infra.OpenSslCmdBuilder import OpenSslSClientBuilder

logger = logging.getLogger(__name__)


@dataclass
class SClientVerifyResult:
    """Result of s_client connection verification."""

    success: bool
    return_code: Optional[int] = None
    return_code_message: Optional[str] = None
    alpn_protocol: Optional[str] = None
    tls_version: Optional[str] = None
    cipher: Optional[str] = None
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""

    def __bool__(self) -> bool:
        return self.success


class SClientOutputParser:
    """Parser for OpenSSL s_client output."""

    VERIFY_RETURN_CODE_PATTERN = re.compile(
        r"Verify return code:\s*(\d+)\s*\(([^)]+)\)"
    )
    ALPN_PROTOCOL_PATTERN = re.compile(r"ALPN protocol:\s*(\S+)")
    TLS_VERSION_PATTERN = re.compile(r"Protocol\s*:\s*(TLSv[\d.]+)")
    CIPHER_PATTERN = re.compile(r"Cipher\s*:\s*(\S+)")

    CERT_ERROR_PATTERNS = [
        re.compile(r"certificate verify failed", re.IGNORECASE),
        re.compile(r"unable to get local issuer certificate", re.IGNORECASE),
        re.compile(r"self[- ]signed certificate", re.IGNORECASE),
        re.compile(r"certificate has expired", re.IGNORECASE),
        re.compile(r"unable to verify the first certificate", re.IGNORECASE),
        re.compile(r"certificate chain too long", re.IGNORECASE),
        re.compile(r"unable to get issuer certificate", re.IGNORECASE),
        re.compile(r"certificate not trusted", re.IGNORECASE),
        re.compile(r"SSL_CTX_use_certificate", re.IGNORECASE),
        re.compile(r"SSL_CTX_use_PrivateKey", re.IGNORECASE),
        re.compile(r"no certificate or key specified", re.IGNORECASE),
        re.compile(r"error loading", re.IGNORECASE),
    ]

    CONNECTION_ERROR_PATTERNS = [
        re.compile(r"connect:errno=", re.IGNORECASE),
        re.compile(r"Connection refused", re.IGNORECASE),
        re.compile(r"Connection timed out", re.IGNORECASE),
        re.compile(r"no peer certificate available", re.IGNORECASE),
        re.compile(r"handshake failure", re.IGNORECASE),
        re.compile(r"ssl handshake failure", re.IGNORECASE),
        re.compile(r"SSL\s*alert", re.IGNORECASE),
        re.compile(r"tlsv\d+\s*alert", re.IGNORECASE),
    ]

    @classmethod
    def parse(cls, stdout: str, stderr: str) -> SClientVerifyResult:
        """
        Parse s_client output and return verification result.

        Args:
            stdout: Standard output from s_client.
            stderr: Standard error from s_client.

        Returns:
            SClientVerifyResult with parsed information.
        """
        combined = stdout + "\n" + stderr
        result = SClientVerifyResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
        )

        verify_match = cls.VERIFY_RETURN_CODE_PATTERN.search(combined)
        if verify_match:
            result.return_code = int(verify_match.group(1))
            result.return_code_message = verify_match.group(2)
            result.success = result.return_code == 0

        alpn_match = cls.ALPN_PROTOCOL_PATTERN.search(combined)
        if alpn_match:
            result.alpn_protocol = alpn_match.group(1)

        tls_match = cls.TLS_VERSION_PATTERN.search(combined)
        if tls_match:
            result.tls_version = tls_match.group(1)

        cipher_match = cls.CIPHER_PATTERN.search(combined)
        if cipher_match:
            result.cipher = cipher_match.group(1)

        if result.success and cls.has_connection_error(stdout, stderr):
            result.success = False

        if not result.success:
            result.error_message = cls._find_error(combined)

        return result

    @classmethod
    def _find_error(cls, output: str) -> Optional[str]:
        """Find error message in output."""
        for pattern in cls.CERT_ERROR_PATTERNS + cls.CONNECTION_ERROR_PATTERNS:
            match = pattern.search(output)
            if match:
                line_start = output.rfind("\n", 0, match.start()) + 1
                line_end = output.find("\n", match.end())
                if line_end == -1:
                    line_end = len(output)
                return output[line_start:line_end].strip()
        return None

    @classmethod
    def has_cert_error(cls, stdout: str, stderr: str) -> bool:
        """Check if output contains certificate-related errors."""
        combined = stdout + "\n" + stderr
        return any(p.search(combined) for p in cls.CERT_ERROR_PATTERNS)

    @classmethod
    def has_connection_error(cls, stdout: str, stderr: str) -> bool:
        """Check if output contains connection errors."""
        combined = stdout + "\n" + stderr
        return any(p.search(combined) for p in cls.CONNECTION_ERROR_PATTERNS)

    @classmethod
    def get_verify_return_code(cls, stdout: str, stderr: str) -> Optional[int]:
        """Extract verify return code from output."""
        combined = stdout + "\n" + stderr
        match = cls.VERIFY_RETURN_CODE_PATTERN.search(combined)
        return int(match.group(1)) if match else None

    @classmethod
    def get_alpn_protocol(cls, stdout: str, stderr: str) -> Optional[str]:
        """Extract negotiated ALPN protocol from output."""
        combined = stdout + "\n" + stderr
        match = cls.ALPN_PROTOCOL_PATTERN.search(combined)
        return match.group(1) if match else None


class OpenSslSClient:
    """
    Client for running OpenSSL s_client connections.

    Uses CmdRunner to manage subprocess lifecycle with support for:
    - Establishing TLS connections
    - Keeping connections alive for interactive use
    - Sending data to the server
    - Reading responses
    - Graceful connection termination

    Example usage:
        client = OpenSslSClient("example.com", 443)
        client.connect(
            ca_file="/path/to/ca.crt",
            cert="/path/to/client.crt",
            key="/path/to/client.key",
            alpn="h2"
        )
        output, err = client.close()
    """

    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        host: str,
        port: Union[str, int],
        default_timeout: int = DEFAULT_TIMEOUT,
        print_outputs: bool = True,
    ):
        """
        Initialize OpenSSL s_client wrapper.

        Args:
            host: Target hostname or IP address.
            port: Target port number.
            default_timeout: Default timeout for commands in seconds.
            print_outputs: Whether to print command outputs to log.
        """
        self.host = host
        self.port = port
        self._default_timeout = default_timeout
        self._print_outputs = print_outputs
        self._process: Optional[subprocess.Popen] = None

    def __del__(self):
        if self._process and self._process.poll() is None:
            self._log("cleaning up: closing connection")
            self._terminate_process()

    def connect(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        alpn: Optional[str] = None,
        servername: Optional[str] = None,
        verify_depth: Optional[int] = None,
        verify_return_error: bool = False,
        tls_version: Optional[str] = None,
        quiet: bool = False,
        brief: bool = False,
        showcerts: bool = False,
        extra_options: Optional[str] = None,
        keep_alive: bool = True,
        timeout: Optional[int] = None,
    ) -> Tuple[str, str]:
        """
        Establish an s_client connection.

        Args:
            ca_file: Path to CA certificate file.
            cert: Path to client certificate file.
            key: Path to client private key file.
            alpn: ALPN protocol (e.g., "h2", "http/1.1").
            servername: Server name for SNI.
            verify_depth: Certificate verification depth.
            verify_return_error: Fail on certificate verification error.
            tls_version: TLS version ("1.2" or "1.3").
            quiet: Suppress session/certificate output.
            brief: Brief output mode.
            showcerts: Show full certificate chain.
            extra_options: Additional raw options to append.
            keep_alive: Keep the connection alive for interaction.
            timeout: Command timeout in seconds (if not keep_alive).

        Returns:
            Tuple of (output, error) if not keep_alive, else ("", "").

        Raises:
            RuntimeError: If a connection is already active.
        """
        if self._process and self._process.poll() is None:
            raise RuntimeError("Connection already active. Close it first.")

        cmd = self._build_command(
            ca_file=ca_file,
            cert=cert,
            key=key,
            alpn=alpn,
            servername=servername,
            verify_depth=verify_depth,
            verify_return_error=verify_return_error,
            tls_version=tls_version,
            quiet=quiet,
            brief=brief,
            showcerts=showcerts,
            extra_options=extra_options,
        )

        self._log(f"connecting: {cmd}")

        self._process = subprocess.Popen(
            cmd,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        if keep_alive:
            self._log("connection established, keeping alive")
            return "", ""

        return self._wait_or_timeout(timeout or self._default_timeout)

    def _build_command(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        alpn: Optional[str] = None,
        servername: Optional[str] = None,
        verify_depth: Optional[int] = None,
        verify_return_error: bool = False,
        tls_version: Optional[str] = None,
        quiet: bool = False,
        brief: bool = False,
        showcerts: bool = False,
        extra_options: Optional[str] = None,
    ) -> str:
        """Build the s_client command string."""
        builder = OpenSslSClientBuilder(self.host, self.port)

        if ca_file:
            builder.CAfile(ca_file)
        if cert:
            builder.cert(cert)
        if key:
            builder.key(key)
        if alpn:
            builder.alpn(alpn)
        if servername:
            builder.servername(servername)
        if verify_depth is not None:
            builder.verify(verify_depth)
        if verify_return_error:
            builder.verify_return_error()
        if tls_version == "1.2":
            builder.tls1_2()
        elif tls_version == "1.3":
            builder.tls1_3()
        if quiet:
            builder.quiet()
        if brief:
            builder.brief()
        if showcerts:
            builder.showcerts()

        cmd = builder.get_command_string()

        if extra_options:
            cmd = f"{cmd} {extra_options}"

        return cmd

    def send(self, data: str, newline: bool = True) -> None:
        """
        Send data to the connected server.

        Args:
            data: Data to send.
            newline: Whether to append newline to data.

        Raises:
            RuntimeError: If no active connection.
        """
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("No active connection.")

        if newline and not data.endswith("\n"):
            data += "\n"

        self._log(f"sending: {data.strip()}")
        self._process.stdin.write(data.encode("utf-8"))
        self._process.stdin.flush()

    def send_quit(self) -> None:
        """Send 'Q' command to gracefully quit s_client."""
        self.send("Q")

    def close(self, timeout: Optional[int] = None) -> Tuple[str, str]:
        """
        Close the connection and get output.

        Args:
            timeout: Seconds to wait before forcefully terminating.

        Returns:
            Tuple of (stdout, stderr) from the process.
        """
        if not self._process:
            self._log("no active connection to close")
            return "", ""

        timeout = timeout or self._default_timeout
        return self._wait_or_timeout(timeout)

    def close_gracefully(self, timeout: Optional[int] = None) -> Tuple[str, str]:
        """
        Send quit command and close the connection.

        Args:
            timeout: Seconds to wait before forcefully terminating.

        Returns:
            Tuple of (stdout, stderr) from the process.
        """
        if self._process and self._process.poll() is None:
            try:
                self.send_quit()
            except (BrokenPipeError, OSError):
                self._log("connection already closed by server")
        return self.close(timeout)

    def is_connected(self) -> bool:
        """Check if connection is still active."""
        return self._process is not None and self._process.poll() is None

    def get_process(self) -> Optional[subprocess.Popen]:
        """Get the underlying subprocess for advanced usage."""
        return self._process

    def _wait_or_timeout(self, timeout: int) -> Tuple[str, str]:
        """Wait for process to finish or kill after timeout."""
        if not self._process:
            return "", ""

        self._log(f"waiting up to {timeout}s for process to finish")
        try:
            self._process.wait(timeout=timeout)
            self._log("process finished normally")
        except subprocess.TimeoutExpired:
            self._log(f"timeout after {timeout}s, terminating process")
            self._terminate_process()

        return self._get_output()

    def _terminate_process(self) -> None:
        """Terminate the process group."""
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

    def _get_output(self) -> Tuple[str, str]:
        """Get stdout and stderr from process."""
        if not self._process:
            return "", ""

        try:
            stdout, stderr = self._process.communicate(timeout=5)
            stdout = stdout.decode("utf-8") if stdout else ""
            stderr = stderr.decode("utf-8") if stderr else ""
        except subprocess.TimeoutExpired:
            self._log("communicate timeout, killing process")
            self._process.kill()
            stdout, stderr = self._process.communicate()
            stdout = stdout.decode("utf-8") if stdout else ""
            stderr = stderr.decode("utf-8") if stderr else ""

        if self._print_outputs:
            self._log(f"stdout: {stdout}")
            self._log(f"stderr: {stderr}")

        self._process = None
        return stdout, stderr

    def _log(self, message: str) -> None:
        """Log a message with class prefix."""
        logger.info(f"[OpenSslSClient] {message}")

    # --- Verification Methods ---

    def connect_and_verify(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        alpn: Optional[str] = None,
        servername: Optional[str] = None,
        verify_depth: Optional[int] = None,
        tls_version: Optional[str] = None,
        timeout: Optional[int] = None,
        extra_options: Optional[str] = None,
    ) -> SClientVerifyResult:
        """
        Connect and return parsed verification result.

        Args:
            ca_file: Path to CA certificate file.
            cert: Path to client certificate file.
            key: Path to client private key file.
            alpn: ALPN protocol to request.
            servername: Server name for SNI.
            verify_depth: Certificate verification depth.
            tls_version: TLS version ("1.2" or "1.3").
            timeout: Command timeout in seconds.
            extra_options: Additional raw options.

        Returns:
            SClientVerifyResult with connection details.
        """
        stdout, stderr = self.connect(
            ca_file=ca_file,
            cert=cert,
            key=key,
            alpn=alpn,
            servername=servername,
            verify_depth=verify_depth,
            verify_return_error=True,
            tls_version=tls_version,
            extra_options=extra_options,
            keep_alive=False,
            timeout=timeout,
        )
        return SClientOutputParser.parse(stdout, stderr)

    def verify_successful_handshake(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        alpn: Optional[str] = None,
        servername: Optional[str] = None,
        tls_version: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> SClientVerifyResult:
        """
        Verify that TLS handshake completes successfully.

        Asserts that:
        - Verify return code is 0 (ok)
        - If ALPN provided, it was negotiated

        Args:
            ca_file: Path to CA certificate file.
            cert: Path to client certificate file.
            key: Path to client private key file.
            alpn: Expected ALPN protocol (verified if provided).
            servername: Server name for SNI.
            tls_version: TLS version ("1.2" or "1.3").
            timeout: Command timeout in seconds.

        Returns:
            SClientVerifyResult with connection details.

        Raises:
            AssertionError: If handshake fails or ALPN mismatch.
        """
        result = self.connect_and_verify(
            ca_file=ca_file,
            cert=cert,
            key=key,
            alpn=alpn,
            servername=servername,
            tls_version=tls_version,
            timeout=timeout,
        )

        assert result.success, (
            f"TLS handshake failed. "
            f"Return code: {result.return_code} ({result.return_code_message}). "
            f"Error: {result.error_message}"
        )

        if alpn:
            assert result.alpn_protocol == alpn, (
                f"ALPN mismatch. Expected: {alpn}, "
                f"Got: {result.alpn_protocol}"
            )

        self._log(
            f"handshake verified: return_code={result.return_code}, "
            f"alpn={result.alpn_protocol}, tls={result.tls_version}"
        )
        return result

    def verify_handshake_fails(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        alpn: Optional[str] = None,
        servername: Optional[str] = None,
        tls_version: Optional[str] = None,
        timeout: Optional[int] = None,
        expected_error: Optional[str] = None,
        expected_return_code: Optional[int] = None,
    ) -> SClientVerifyResult:
        """
        Verify that TLS handshake fails as expected.

        Use this to test error scenarios like:
        - Missing or invalid CA certificate
        - Missing or invalid client certificate
        - Certificate verification failures

        Args:
            ca_file: Path to CA certificate file.
            cert: Path to client certificate file.
            key: Path to client private key file.
            alpn: ALPN protocol to request.
            servername: Server name for SNI.
            tls_version: TLS version ("1.2" or "1.3").
            timeout: Command timeout in seconds.
            expected_error: Regex pattern to match in error output.
            expected_return_code: Expected verify return code (non-zero).

        Returns:
            SClientVerifyResult with connection details.

        Raises:
            AssertionError: If handshake succeeds or error doesn't match.
        """
        result = self.connect_and_verify(
            ca_file=ca_file,
            cert=cert,
            key=key,
            alpn=alpn,
            servername=servername,
            tls_version=tls_version,
            timeout=timeout,
        )

        assert not result.success, (
            f"Expected handshake to fail, but it succeeded. "
            f"Return code: {result.return_code} ({result.return_code_message})"
        )

        if expected_return_code is not None:
            assert result.return_code == expected_return_code, (
                f"Return code mismatch. Expected: {expected_return_code}, "
                f"Got: {result.return_code} ({result.return_code_message})"
            )

        if expected_error:
            combined = result.stdout + "\n" + result.stderr
            assert re.search(expected_error, combined, re.IGNORECASE), (
                f"Expected error pattern '{expected_error}' not found. "
                f"Actual error: {result.error_message}"
            )

        self._log(
            f"handshake failure verified: return_code={result.return_code}, "
            f"error={result.error_message}"
        )
        return result

    def verify_cert_error(
        self,
        ca_file: Optional[str] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> SClientVerifyResult:
        """
        Verify that connection fails with a certificate error.

        Args:
            ca_file: Path to CA certificate file (may be wrong/missing).
            cert: Path to client certificate file (may be wrong/missing).
            key: Path to client private key file (may be wrong/missing).
            timeout: Command timeout in seconds.

        Returns:
            SClientVerifyResult with connection details.

        Raises:
            AssertionError: If no certificate error detected.
        """
        result = self.connect_and_verify(
            ca_file=ca_file,
            cert=cert,
            key=key,
            timeout=timeout,
        )

        has_cert_error = SClientOutputParser.has_cert_error(
            result.stdout, result.stderr
        )
        assert not result.success or has_cert_error, (
            f"Expected certificate error, but connection succeeded or "
            f"no cert error found. Return code: {result.return_code}"
        )

        self._log(f"certificate error verified: {result.error_message}")
        return result


def run_s_client_once(
    host: str,
    port: Union[str, int],
    ca_file: Optional[str] = None,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    alpn: Optional[str] = None,
    timeout: int = 10,
    print_outputs: bool = True,
) -> Tuple[str, str]:
    """
    Convenience function to run a single s_client connection.

    Args:
        host: Target hostname or IP address.
        port: Target port number.
        ca_file: Path to CA certificate file.
        cert: Path to client certificate file.
        key: Path to client private key file.
        alpn: ALPN protocol.
        timeout: Command timeout in seconds.
        print_outputs: Whether to print outputs to log.

    Returns:
        Tuple of (stdout, stderr).
    """
    client = OpenSslSClient(host, port, timeout, print_outputs)
    return client.connect(
        ca_file=ca_file,
        cert=cert,
        key=key,
        alpn=alpn,
        keep_alive=False,
        timeout=timeout,
    )


def verify_tls_connection(
    host: str,
    port: Union[str, int],
    ca_file: Optional[str] = None,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    alpn: Optional[str] = None,
    tls_version: Optional[str] = None,
    timeout: int = 10,
    print_outputs: bool = True,
) -> SClientVerifyResult:
    """
    Convenience function to verify a TLS connection.

    Args:
        host: Target hostname or IP address.
        port: Target port number.
        ca_file: Path to CA certificate file.
        cert: Path to client certificate file.
        key: Path to client private key file.
        alpn: ALPN protocol.
        tls_version: TLS version ("1.2" or "1.3").
        timeout: Command timeout in seconds.
        print_outputs: Whether to print outputs to log.

    Returns:
        SClientVerifyResult with parsed verification details.
    """
    client = OpenSslSClient(host, port, timeout, print_outputs)
    return client.connect_and_verify(
        ca_file=ca_file,
        cert=cert,
        key=key,
        alpn=alpn,
        tls_version=tls_version,
        timeout=timeout,
    )


def assert_tls_handshake_succeeds(
    host: str,
    port: Union[str, int],
    ca_file: Optional[str] = None,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    alpn: Optional[str] = None,
    tls_version: Optional[str] = None,
    timeout: int = 10,
    print_outputs: bool = True,
) -> SClientVerifyResult:
    """
    Assert that TLS handshake succeeds with return code 0.

    Args:
        host: Target hostname or IP address.
        port: Target port number.
        ca_file: Path to CA certificate file.
        cert: Path to client certificate file.
        key: Path to client private key file.
        alpn: Expected ALPN protocol (verified if provided).
        tls_version: TLS version ("1.2" or "1.3").
        timeout: Command timeout in seconds.
        print_outputs: Whether to print outputs to log.

    Returns:
        SClientVerifyResult with parsed verification details.

    Raises:
        AssertionError: If handshake fails or ALPN doesn't match.
    """
    client = OpenSslSClient(host, port, timeout, print_outputs)
    return client.verify_successful_handshake(
        ca_file=ca_file,
        cert=cert,
        key=key,
        alpn=alpn,
        tls_version=tls_version,
        timeout=timeout,
    )


def assert_tls_handshake_fails(
    host: str,
    port: Union[str, int],
    ca_file: Optional[str] = None,
    cert: Optional[str] = None,
    key: Optional[str] = None,
    expected_error: Optional[str] = None,
    expected_return_code: Optional[int] = None,
    timeout: int = 10,
    print_outputs: bool = True,
) -> SClientVerifyResult:
    """
    Assert that TLS handshake fails as expected.

    Args:
        host: Target hostname or IP address.
        port: Target port number.
        ca_file: Path to CA certificate file (may be wrong/missing).
        cert: Path to client certificate file (may be wrong/missing).
        key: Path to client private key file (may be wrong/missing).
        expected_error: Regex pattern to match in error output.
        expected_return_code: Expected verify return code (non-zero).
        timeout: Command timeout in seconds.
        print_outputs: Whether to print outputs to log.

    Returns:
        SClientVerifyResult with parsed verification details.

    Raises:
        AssertionError: If handshake succeeds or error doesn't match.
    """
    client = OpenSslSClient(host, port, timeout, print_outputs)
    return client.verify_handshake_fails(
        ca_file=ca_file,
        cert=cert,
        key=key,
        expected_error=expected_error,
        expected_return_code=expected_return_code,
        timeout=timeout,
    )
