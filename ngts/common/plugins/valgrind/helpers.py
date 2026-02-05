from __future__ import annotations

from datetime import datetime, timezone
from allure import attachment_type
from pathlib import Path
from typing import Any
import dataclasses
import tempfile
import logging
import shlex
import json

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tools.test_utils import allure_utils as allure
from ngts.ngts_types import EnginesT, TopologyT

from .analyzer import DecisionConfig, IgnoreRegistry, ValgrindAnalyzer, ValgrindLeakEntry, ValgrindSummary
from . import bug_handler

logger = logging.getLogger(__name__)

VALGRIND_DIR = '/var/log/valgrind'


@dataclasses.dataclass(frozen=True)
class ValgrindBugHandlerContext:
    """Context for the Valgrind bug handler."""

    setup_name: str = ""
    topology_obj: TopologyT | None = None
    engines: EnginesT | None = None
    cli_type: str | None = None
    mode: str = "create"
    session_id: str | None = None
    skip_actions: bool = False
    version: str | None = None


@dataclasses.dataclass(frozen=True)
class ValgrindBugHandlerRequest:
    """Strongly-typed representation of the kwargs passed to run_valgrind_bug_handler."""

    tarball: Path
    members: tuple[str, ...]
    summary: ValgrindSummary
    setup_name: str
    topology_obj: TopologyT
    engines: EnginesT
    cli_type: str | None
    mode: str
    session_id: str | None
    version: str | None = None
    decision_config: DecisionConfig | None = None

    def to_kwargs(self) -> dict[str, Any]:
        """Convert the request to a dictionary of keyword arguments."""
        return {
            "tarball": self.tarball,
            "members": self.members,
            "summary": self.summary,
            "decision_config": self.decision_config,
            "setup_name": self.setup_name,
            "topology_obj": self.topology_obj,
            "engines": self.engines,
            "cli_type": self.cli_type,
            "mode": self.mode,
            "session_id": self.session_id,
            "version": self.version,
        }


@dataclasses.dataclass
class ValgrindAnalysisResult:
    """Container for analyzer output plus deferred exceptions."""

    leak_entries: list[ValgrindLeakEntry]
    error: Exception | None = None

    def raise_if_failed(self) -> None:
        """Raise the exception if the analysis failed."""
        if self.error:
            raise self.error from self.error


class ValgrindBugHandlerDispatcher:
    """Encapsulates the orchestration for bug handler dispatch."""

    def __init__(self, ctx: ValgrindBugHandlerContext | None):
        """
        Initialize the dispatcher.
        :param ctx: The context for the bug handler.
        :return: None
        """
        self._ctx = ctx

    def dispatch(
        self,
        *,
        leak_results: list[ValgrindLeakEntry],
        tar_path: str,
        diff: dict[str, dict[str, int]],
        decision_config: DecisionConfig | None = None,
    ) -> None:
        """
        Dispatch the bug handler.

        :param leak_results: The list of leak entries.
        :param tar_path: The path to the tarball.
        :param diff: The diff of the valgrind output.
        :param decision_config: The decision configuration.
        :return: None
        """
        if not leak_results:
            logger.info("No leaks found in Valgrind results")
            return

        if self._ctx is None:
            logger.info("Bug handler context not provided; skipping bug creation")
            return

        if self._ctx.skip_actions:
            logger.info("Bug handler actions are disabled (skip flag set); skipping bug creation")
            return

        logger.debug("Valgrind diff context includes %d file(s)", len(diff or {}))

        bug_handler_responses: list[dict[str, Any]] = []
        for idx, entry in enumerate(leak_results, start=1):
            if not (request := _build_bug_handler_request(entry, tar_path, self._ctx, decision_config=decision_config)):
                logger.debug(f"Skipping leak entry {idx} - missing mandatory bug handler metadata")
                continue

            members_for_log = tuple(request.members)
            logger.info(
                "Invoking Valgrind bug handler for service=%s sub_service=%s members=%s mode=%s",
                entry.service,
                entry.subservice,
                members_for_log,
                request.mode,
            )

            with allure.step(f"Run Valgrind bug handler - {idx}"):
                response = bug_handler.run_valgrind_bug_handler(**request.to_kwargs())

                data = json.dumps(response, indent=2, default=_json_fallback)
                allure.attach("Valgrind bug handler response", data, attachment_type.JSON, log=False)

                # Freeze the response for the aggregated results attachment.
                # Some mocked bug-handler paths may return a shared mutable dict (or mutate in-place),
                # which would make earlier entries appear as the last response. Storing a JSON snapshot
                # avoids that class of confusion.
                response_snapshot = json.loads(data)
                bug_handler_responses.append({
                    "service": entry.service,
                    "subservice": entry.subservice,
                    "members": members_for_log,
                    "mode": request.mode,
                    "response": response_snapshot,
                })

        if bug_handler_responses:
            data = json.dumps(bug_handler_responses, indent=2, default=_json_fallback)
            allure.attach("Valgrind bug handler results", data, attachment_type.JSON, log=False)
        else:
            logger.info("No eligible Valgrind entries required bug creation")


def _build_bug_handler_request(
    entry: ValgrindLeakEntry,
    fallback_tarball: str,
    ctx: ValgrindBugHandlerContext,
    *,
    decision_config: DecisionConfig | None = None,
) -> ValgrindBugHandlerRequest | None:
    """
    Convert a leak entry into a structured request for run_valgrind_bug_handler.
    """
    if ctx.topology_obj is None or ctx.engines is None:
        return None
    if not entry.members:
        return None

    return ValgrindBugHandlerRequest(
        tarball=Path(fallback_tarball),
        members=entry.members,
        summary=entry.summary,
        decision_config=decision_config,
        setup_name=ctx.setup_name,
        topology_obj=ctx.topology_obj,
        engines=ctx.engines,
        cli_type=ctx.cli_type,
        mode=ctx.mode,
        session_id=ctx.session_id,
        version=ctx.version,
    )


def _json_fallback(obj):
    ''' JSON fallback for the bug handler request. '''
    if isinstance(obj, Path):
        return str(obj)
    if dataclasses.is_dataclass(obj):
        return {field.name: _json_fallback(getattr(obj, field.name)) for field in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple, set)):
        return [_json_fallback(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _json_fallback(v) for k, v in obj.items()}
    return str(obj)


def _collect_valgrind_leaks(
    tar_path: str,
    diff: dict[str, dict[str, int]],
    valgrind_config: DecisionConfig,
    leak_entries: list[ValgrindLeakEntry],
    *,
    ignore_registry: IgnoreRegistry | None = None,
):
    '''
    Collect the valgrind leaks.
    :param tar_path: The path to the tarball.
    :param diff: The diff of the valgrind output.
    :param valgrind_config: The decision configuration.
    :param leak_entries: The list of leak entries.
    :param ignore_registry: The ignore registry.
    :return: None
    '''
    try:
        results: list[ValgrindLeakEntry] = []
        with allure.step(f"Analyze valgrind diff files: {tar_path}"):
            with ValgrindAnalyzer(tar_path, diff, valgrind_config, ignore_registry=ignore_registry) as analyzer:
                results = analyzer.analyze()
                allure.attach("leaks_count.txt", f"Leaks count: {len(results)}", log=False)
    finally:
        leak_entries.clear()
        leak_entries.extend(results.copy())
        allure.attach("leaks_count.txt", f"Leaks count: {len(leak_entries)}", log=False)


def _run_valgrind_analysis(
    tar_path: str,
    diff: dict[str, dict[str, int]],
    valgrind_config: DecisionConfig,
    *,
    ignore_registry: IgnoreRegistry | None = None,
) -> ValgrindAnalysisResult:
    '''
    Run the valgrind analysis.
    :param tar_path: The path to the tarball.
    :param diff: The diff of the valgrind output.
    :param valgrind_config: The decision configuration.
    :param ignore_registry: The ignore registry.
    :return: The analysis result.
    '''
    leak_entries: list[ValgrindLeakEntry] = []
    analysis_error: Exception | None = None
    try:
        _collect_valgrind_leaks(tar_path, diff, valgrind_config, leak_entries, ignore_registry=ignore_registry)
    except Exception as exc:
        analysis_error = exc

    return ValgrindAnalysisResult(leak_entries=leak_entries, error=analysis_error)


def valgrind_analyze(
    diff: dict[str, dict[str, int]],
    tar_path: str,
    valgrind_config: DecisionConfig,
    bug_handler_ctx: ValgrindBugHandlerContext | None = None,
    ignore_registry: IgnoreRegistry | None = None,
) -> None:
    """
    Run the valgrind analysis and dispatch the bug handler.

    :param diff: The diff of the valgrind output.
    :param tar_path: The path to the tarball.
    :param valgrind_config: The decision configuration.
    :param bug_handler_ctx: The context for the bug handler.
    :param ignore_registry: The ignore registry.
    :return: None
    """
    analysis = _run_valgrind_analysis(tar_path, diff, valgrind_config, ignore_registry=ignore_registry)
    with allure.step("Run Valgrind bug handler"):
        dispatcher = ValgrindBugHandlerDispatcher(ctx=bug_handler_ctx)
        dispatcher.dispatch(
            leak_results=analysis.leak_entries,
            tar_path=tar_path,
            diff=diff,
            decision_config=valgrind_config,
        )
    analysis.raise_if_failed()


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
