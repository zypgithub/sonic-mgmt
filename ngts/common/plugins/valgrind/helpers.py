from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import logging
import shlex

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tools.test_utils import allure_utils as allure

from .analyzer import DecisionConfig

logger = logging.getLogger(__name__)

VALGRIND_DIR = '/var/log/valgrind'


def valgrind_analyze(
    diff: dict[str, dict[str, int]],
    tar_path: str,
    valgrind_config: DecisionConfig,
) -> None:
    raise NotImplementedError("valgrind_analyze is not implemented")


def zip_valgrind_diff_files(engine: LinuxSshEngine, nodeid: str, changed_files: list[str]) -> str:
    """Create a tarball of changed Valgrind files on the DUT and fetch it locally.

    Args:
        engine: SSH engine used to run commands and transfer files.
        nodeid: Pytest node id used to namespace temp files.
        changed_files: File paths (relative to VALGRIND_DIR) to include.

    Returns:
        Path to the created tarball on the local host.

    Raises:
        ValueError: If no changed files were provided.
    """
    if not changed_files:
        raise ValueError("No changed files to tar")

    with allure.step("Zip valgrind diff files"):
        # Build unique tar/list file names for this test node.
        now = datetime.now(timezone.utc)
        tar_path = f'/tmp/vg.{nodeid}.{now:%Y%m%dT%H%M%S}Z.tar.gz'
        logger.info("Valgrind tarball: nodeid=%s changed_files=%d tar_path=%s", nodeid, len(changed_files), tar_path)

        remote_list_path = f"/tmp/vg.{nodeid}.{now:%Y%m%dT%H%M%S}Z.files.txt"
        logger.debug("Valgrind tarball file list: remote_list_path=%s", remote_list_path)

        with tempfile.NamedTemporaryFile(mode="w", prefix=f"vg.{nodeid}.{now:%Y%m%dT%H%M%S}Z.", suffix=".files.txt", encoding="utf-8") as tmp:
            tmp.write("\n".join(changed_files))
            logger.debug("Valgrind tarball local file list created: %s", tmp.name)
            tmp.flush()

            engine.copy_file(
                source_file=Path(tmp.name),
                dest_file=remote_list_path,
                file_system="/",
                direction="put",
                overwrite_file=True,
                verify_file=False,
            )
            logger.info("Valgrind tarball file list uploaded: %s", remote_list_path)

            cmd = f"tar -czf {shlex.quote(tar_path)} -C {shlex.quote(VALGRIND_DIR)} -T {shlex.quote(remote_list_path)}"
            allure.attach("Valgrind tar command", cmd, log=False)
            logger.info("Valgrind tarball command: %s", cmd)
            if tar_output := engine.run_cmd(cmd, validate=True):
                logger.debug("Valgrind tarball command output (trimmed): %s", tar_output.strip()[:500])

        # Fetch the tarball back to the local host.
        engine.copy_file(
            source_file=tar_path,
            dest_file=tar_path,
            file_system='/',
            direction='get',
            overwrite_file=True,
            verify_file=False,
        )

        return tar_path
