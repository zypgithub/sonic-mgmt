"""
VaultClient.py

Vault client for fetching secrets and exporting to environment.
Uses vault agent CLI with AppRole authentication from shared NVOS_INFRA directory.
Uses the same approach as NGCI vault scripts.
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class VaultClient:
    """
    Vault client for fetching secrets and exporting to environment.
    Uses vault agent CLI with AppRole authentication.
    """

    VAULT_ADDR = "https://prod.vault.nvidia.com"
    VAULT_NAMESPACE = "nbu-system-sw-sonic"
    VAULT_CREDS_DIR = "/auto/sw_system_project/NVOS_INFRA/vault"
    SECRETS_TEMPLATE_PATH = "/auto/sw_regression/system/SONIC/MARS/conf/secret_code_export.tmpl"

    EXPORT_PREFIX = "export "
    EXPORT_PREFIX_LEN = len(EXPORT_PREFIX)

    VAULT_AGENT_LOG_LEVEL = "warn"
    VAULT_AGENT_TIMEOUT = 60

    CONFIG_FILE_PERMS = 0o600
    OUTPUT_FILE_PERMS = "600"

    VAULT_DOWNLOAD_URL = (
        "https://urm.nvidia.com/artifactory/sw-kaizen-data-generic/com/nvidia/vault/vault-agent/2.4.1/nvault_agent_v2.4.1_linux_amd64.zip"
    )
    VAULT_INSTALL_DIR = "/bin"

    @classmethod
    def _read_credential(cls, filename: str) -> str:
        path = os.path.join(cls.VAULT_CREDS_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Vault credential not found: {path}")
        with open(path) as f:
            return f.read().strip()

    @classmethod
    def _create_agent_config(cls, config_file: str, output_file: str, template_path: str, pid_file: str) -> None:
        role_id = cls._read_credential("role_id")
        secret_id = cls._read_credential("secret_id")

        config_content = f'''pid_file = "{pid_file}"

exit_after_auth = true

vault {{
  address = "{cls.VAULT_ADDR}"
  namespace = "{cls.VAULT_NAMESPACE}"
}}

auto_auth {{
  method {{
    type = "approle"

    config = {{
      role_id = "{role_id}"
      secret_id = "{secret_id}"
    }}
  }}
}}

log_level = "{cls.VAULT_AGENT_LOG_LEVEL}"

template {{
  source = "{template_path}"
  destination = "{output_file}"
  perms = "{cls.OUTPUT_FILE_PERMS}"
  error_on_missing_key = true
}}
'''
        with open(config_file, "w") as f:
            f.write(config_content)
        os.chmod(config_file, cls.CONFIG_FILE_PERMS)

    @classmethod
    def fetch_and_export_secrets(cls, template_path: str | None = None) -> None:
        """
        Main entry point: use vault agent to fetch all secrets and export to os.environ.
        Fails fast if Vault is unavailable.

        Args:
            template_path: Optional path to secrets template file. Uses default if not specified.

        Raises:
            FileNotFoundError: If template or credentials file not found.
            RuntimeError: If Vault authentication or secret fetching fails.
        """
        if template_path is None:
            template_path = cls.SECRETS_TEMPLATE_PATH

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Secrets template not found: {template_path}")

        with (
            tempfile.NamedTemporaryFile(mode="w", suffix=".hcl", delete=False) as config_file,
            tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as output_file,
        ):
            config_path = config_file.name
            output_path = output_file.name

        # User-specific PID file to avoid collisions across concurrent runs
        pid_path = f"/tmp/vault-agent-nvos-{os.getuid()}.pid"

        try:
            cls._create_agent_config(config_path, output_path, template_path, pid_path)

            logger.info("Running vault agent to fetch secrets...")
            try:
                result = subprocess.run(
                    ["vault", "agent", "-config", config_path],
                    capture_output=True,
                    text=True,
                    timeout=cls.VAULT_AGENT_TIMEOUT,
                )
            except FileNotFoundError as e:
                logger.error(
                    "vault CLI not found. Install instructions:\n"
                    f"  wget {cls.VAULT_DOWNLOAD_URL}\n"
                    f"  sudo unzip nvault_agent_v2.4.1_linux_amd64.zip -d {cls.VAULT_INSTALL_DIR}\n"
                    "  vault --version  # Test installation"
                )
                raise RuntimeError("vault CLI not found in PATH") from e

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                if "403" in error_msg or "permission denied" in error_msg.lower():
                    logger.error(
                        f"Vault authentication failed (403 Forbidden). Admin needs to refresh secret_id in {cls.VAULT_CREDS_DIR}/secret_id"
                    )
                    raise RuntimeError("Vault authentication failed: permission denied")
                # Don't log full error message as it may contain sensitive data
                logger.error("Vault agent failed. Check vault connectivity and credentials.")
                raise RuntimeError(f"Vault agent failed with exit code {result.returncode}")

            logger.debug("Vault agent completed successfully")

            secrets_loaded = 0
            with open(output_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(cls.EXPORT_PREFIX):
                        export_stmt = line[cls.EXPORT_PREFIX_LEN:]
                        if "=" in export_stmt:
                            var_name, var_value = export_stmt.split("=", 1)
                            var_value = var_value.strip()
                            if var_value.startswith('"') and var_value.endswith('"') and len(var_value) >= 2:
                                var_value = var_value[1:-1]
                            os.environ[var_name] = var_value
                            secrets_loaded += 1
                            logger.debug(f"Exported {var_name}")

            if secrets_loaded == 0:
                logger.warning(f"No secrets were loaded from Vault. Template may be empty or misconfigured: {template_path}")

            logger.info(f"Vault secrets loaded successfully: {secrets_loaded} variables exported")

        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Vault agent timed out after {cls.VAULT_AGENT_TIMEOUT} seconds") from e
        finally:
            for path in [config_path, output_path, pid_path]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temporary file {path}: {e}")
