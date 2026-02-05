from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
import dataclasses
import contextlib
import logging
import tarfile
import copy

from ngts.tools.test_utils import allure_utils as allure

from .summary import ValgrindSummary, DecisionConfig, RecordPolicy
from .trace_id import TraceIdComputer
from .ignores import IgnoreRegistry
from .enums import BugHandlerScope

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ValgrindLeakEntry:
    """
    Represents a single Valgrind memory leak entry.

    Attributes:
        service (str): The service of the leak entry.
        subservice (str | None): The subservice of the leak entry.
        members (tuple[str, ...]): The members of the leak entry.
        summary (ValgrindSummary): The summary of the leak entry.
        scope (BugHandlerScope): The scope of the leak entry.
    """

    service: str
    subservice: str | None
    members: tuple[str, ...]
    summary: ValgrindSummary
    scope: BugHandlerScope


class AnalysisError(AssertionError):
    """
    Exception raised when Valgrind analysis detects issues that exceed configured thresholds.

    Attributes:
        summary (ValgrindSummary): The summary of leak findings that triggered the error.
    """

    def __init__(self, summary: ValgrindSummary):
        if summary.subservice:
            super().__init__(f"{summary.service} {summary.subservice} has issues above thresholds")
        else:
            super().__init__(f"{summary.service} has issues above thresholds")
        self.summary = summary


class ValgrindAnalyzer:
    """
    ValgrindAnalyzer orchestrates the analysis of Valgrind memory leak reports.

    It processes a tar.gz archive produced by Valgrind, applies configurable bug threshold
    policies, calculates differences across test runs, tracks ignored issues,
    and aggregates findings into ValgrindSummary and ValgrindLeakEntry objects.
    The analyzer supports integration with an ignore registry and trace ID computation logic.
    It is designed to be used as a context manager for safe resource management and reporting.
    """

    _sep = "=" * 60

    def __init__(
        self,
        report_path: str,
        diff: dict[str, dict[str, int]],
        config: DecisionConfig,
        *,
        ignore_registry: IgnoreRegistry | None = None,
        trace_id_computer: TraceIdComputer | None = None,
    ):
        self._log = logger.getChild(self.__class__.__name__)
        self._report_path = report_path
        self._config = config
        self._diff = diff
        self._test_services_and_sub_services = self._diff_to_services_and_sub_services(diff)

        self._ignore_registry = ignore_registry
        if trace_id_computer is not None:
            self._trace_id_computer = trace_id_computer
        elif ignore_registry is not None:
            self._trace_id_computer = ignore_registry.trace_id_computer
        else:
            self._trace_id_computer = TraceIdComputer()

        self._tar: tarfile.TarFile | None = None
        # Track "attach-worthy" files (any findings or ignored findings) for reporting/visibility.
        self._attached_files_count: int = 0
        self._attached_by_service: dict[str, int] = {}
        self._leak_entries: list[ValgrindLeakEntry] = []

    def __enter__(self):
        self._tar = tarfile.open(str(self._report_path), mode='r:gz')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._tar:
            self._tar.close()

    def _read_member_text(self, member: tarfile.TarInfo, *, old_size: int = 0) -> TextIOWrapper:
        '''
        Read the member text and optionally skip a byte baseline (pre-test content).

        :param member: The member to read.
        :param old_size: The old size of the member.
        :return: The text of the member.

        Notes:
            - `old_size` comes from `st_size` snapshotting on the DUT, so it is a byte offset.
        '''
        if not (extracted := self._tar.extractfile(member)):
            raise ValueError(f"Failed to extract member: {member.name}")

        if old_size and old_size > 0:
            try:
                if hasattr(extracted, "seekable") and extracted.seekable():  # type: ignore[attr-defined]
                    extracted.seek(old_size)
                else:
                    remaining = old_size
                    while remaining > 0:
                        chunk = extracted.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
            except Exception:  # noqa: BLE001
                # Best-effort; if we can't skip reliably, fall back to analyzing from current position.
                pass

        return TextIOWrapper(extracted, encoding="utf-8", errors="replace")

    def _analyze_member(
        self,
        service: str,
        subservice: str | None,
        member: tarfile.TarInfo,
    ) -> ValgrindSummary | None:
        '''
        Analyze a member and return the summary of the member.

        :param service: The service of the member.
        :param subservice: The subservice of the member.
        :param member: The member to analyze.
        :return: The summary of the member.
        '''
        ignore_ids: set[str] = set()
        if self._ignore_registry is not None:
            ignore_ids = self._ignore_registry.get_ignore_ids(service=service, subservice=subservice)

        diff_entry = self._diff.get(member.name, {}) or {}
        old_size = int(diff_entry.get("old", 0)) if isinstance(diff_entry, dict) else 0
        member_text = self._read_member_text(member, old_size=old_size)

        summary = ValgrindSummary.parse_from_io(
            service,
            subservice,
            member_text,
            policy=RecordPolicy(ignore_ids=ignore_ids),
            trace_id_computer=self._trace_id_computer,
        )
        has_any_findings = summary.has_issues(DecisionConfig(fail_on_warnings=True))
        has_any_ignored = summary.counters.ignored_definitely_lost > 0 or \
            summary.counters.ignored_indirectly_lost > 0 or \
            summary.counters.ignored_possibly_lost > 0 or \
            summary.counters.ignored_still_reachable > 0
        should_attach = has_any_findings or has_any_ignored

        if not should_attach:
            return None

        with allure.independent_step(f"Analyze file: {member.name}"):
            self._log.warning(f'{member.name} has issues {summary!r}')
            summary_text = f'{summary}\n{self._sep}\n'
            if not self._config.is_default_config:
                summary_text += f'{self._config}\n{self._sep}\n'
            summary_text += summary.capped_summary

            allure.attach(f'{member.name}-summary.txt', summary_text)
            self._attached_files_count += 1
            self._attached_by_service[service] = self._attached_by_service.get(service, 0) + 1
            if summary.has_issues(self._config):
                self._log.error(f'{member.name} has issues {summary!r}')
                # the file has issues and exceeded the thresholds,
                # so we raise an error, to make the allure step fail
                self._record_leak_entry(
                    scope=BugHandlerScope.FILE,
                    service=service,
                    subservice=subservice,
                    members=(member.name,),
                    summary=summary,
                )
                raise AnalysisError(summary)
        return summary

    def _analyze_members(
        self,
        service: str,
        subservice: str | None,
        members: list[tarfile.TarInfo],
    ) -> tuple[ValgrindSummary, ValgrindSummary, tuple[str, ...]]:
        '''
        Analyze a list of members and return:

        - Aggregate summary of members that had any findings (for reporting/attachments).
        - Aggregate summary of members that exceeded configured thresholds (for bug handler dispatch).
        - Tuple of member names that exceeded configured thresholds (so BH doesn't process clean files).
        '''
        members_summary = ValgrindSummary(service=service, subservice=subservice)
        failed_summary = ValgrindSummary(service=service, subservice=subservice)
        failed_member_names: list[str] = []

        for member in members:
            # NOTE: We don't need to catch AnalysisError here, since we are using the independent_step
            # The code will continue even if one of the files has issues and exceeded the thresholds.
            if summary := self._analyze_member(service, subservice, member):
                is_failed = summary.has_issues(self._config)
                self._log.debug(
                    "Member analyzed: service=%s subservice=%s member=%s failed=%s summary=%r",
                    service,
                    subservice,
                    member.name,
                    is_failed,
                    str(summary)[:100],
                )
                members_summary += summary
                if is_failed:
                    failed_summary += summary
                    failed_member_names.append(member.name)

        self._log.debug(
            "Member summary: service=%s subservice=%s has_issues=%s summary=%r",
            service,
            subservice,
            members_summary.has_issues(self._config),
            str(members_summary)[:100],
        )
        return members_summary, failed_summary, tuple(failed_member_names)

    @staticmethod
    def _extract_service_and_subservice(item: str) -> tuple[str, str | None]:
        '''
        Extract the service and subservice from the item.

        :param item: The item to extract the service and subservice from.
        :return: The service and subservice.
        '''
        if not item.endswith(".out"):
            return
        name = Path(item)
        service_name = name.parent.name
        parts = name.name.split('.')
        if len(parts) >= 2:
            sub_service = parts[1]
            # If sub-service equals service name, treat as no sub-service
            if sub_service == service_name:
                sub_service = None
        else:
            sub_service = None

        return service_name, sub_service

    @staticmethod
    def _diff_to_services_and_sub_services(diff: dict[str, dict[str, int]]) -> dict[str, set[str | None]]:
        ''' Convert the diff to a dictionary of services and sub_services. '''
        buckets: dict[str, set[str | None]] = {}
        for item in diff:
            if not (result := ValgrindAnalyzer._extract_service_and_subservice(item)):
                continue
            service_name, sub_service = result
            buckets.setdefault(service_name, set()).add(sub_service)

        allure.attach('diff-buckets.txt', buckets, log=False)
        return buckets

    def _iter_services(self) -> dict[str, dict[str | None, list[tarfile.TarInfo]]]:
        '''
        Group *.out files by their immediate parent directory (service).
        Files are expected to be named like: vg[.<subservice>].<pid>.out
        Sub-service is inferred when present; otherwise set to service name.
        '''
        buckets: dict[str, dict[str | None, list[tarfile.TarInfo]]] = {}
        for member in (members := self._tar.getmembers()):
            if not member.isfile():
                continue
            if not (result := ValgrindAnalyzer._extract_service_and_subservice(member.name)):
                continue
            service_name, sub_service = result
            buckets.setdefault(service_name, {}).setdefault(sub_service, []).append(member)

        allure.attach(f'{self._tar.name}-members.txt', '\n'.join(m.name for m in members), log=False)
        return buckets

    def analyze(self) -> list[ValgrindLeakEntry]:
        """
        Analyze the valgrind report and return the list of leak entries.

        NOTE: This method is using allure independent steps which means it must be wrapped in allure.step
        """
        grouped = self._iter_services()
        collect_test_scope = self._config.bug_handler_scope is BugHandlerScope.TEST
        test_summary = ValgrindSummary(service="valgrind")
        test_member_names: list[str] = []

        self._log.debug("Analyze tar: %s", self._tar.name)
        for service, sub_services in grouped.items():
            if service not in self._test_services_and_sub_services:
                self._log.debug("Skipping service=%s (not in diff buckets)", service)
                continue
            service_summary = ValgrindSummary(service=service)
            # Aggregate only the members that exceed configured thresholds, so SERVICE/TEST scopes do not
            # silently drop failures that occur under sub-services.
            service_failed_summary = ValgrindSummary(service=service)
            service_member_names: list[str] = []
            with allure.independent_step(f"Analyze service: {service}"):
                for sub_service, members in sub_services.items():
                    if sub_service not in self._test_services_and_sub_services[service]:
                        self._log.debug(
                            "Skipping subservice=%s for service=%s (not in diff buckets)",
                            sub_service,
                            service,
                        )
                        continue
                    ctx = contextlib.nullcontext()
                    sub_service_summary = None
                    if sub_service:
                        sub_service_summary = ValgrindSummary(service=service, subservice=sub_service)
                        ctx = allure.independent_step(f"Analyze sub-service: {sub_service}")

                    with ctx:
                        members_summary, failed_summary, failed_member_names = self._analyze_members(service, sub_service, members)
                        if members_summary:
                            self._record_leak_entry(
                                scope=BugHandlerScope.SUB_SERVICE,
                                service=service,
                                subservice=sub_service,
                                members=failed_member_names,
                                summary=failed_summary,
                            )
                            service_member_names.extend(failed_member_names)
                            if failed_member_names:
                                service_failed_summary += failed_summary

                            if sub_service_summary is not None:
                                sub_service_summary += members_summary
                                if sub_service_summary:
                                    sub_service_text = str(sub_service_summary)
                                    if not self._config.is_default_config:
                                        sub_service_text += f'\n{self._sep}\n{self._config}'
                                    allure.attach(f'{sub_service}-summary.txt', sub_service_text)
                            else:
                                service_summary += members_summary

                if service_summary:
                    service_text = str(service_summary)
                    if not self._config.is_default_config:
                        service_text += f'\n{self._sep}\n{self._config}'
                    allure.attach(f'{service}-summary.txt', service_text)

                # Record SERVICE-scope entry (if configured) even when all findings are under sub-services.
                self._record_leak_entry(
                    scope=BugHandlerScope.SERVICE,
                    service=service,
                    subservice=None,
                    members=tuple(service_member_names),
                    summary=service_failed_summary,
                )

                if collect_test_scope and service_member_names:
                    test_summary += copy.deepcopy(service_failed_summary)
                    test_member_names.extend(service_member_names)

        if collect_test_scope and test_member_names:
            self._record_leak_entry(
                scope=BugHandlerScope.TEST,
                service="all-services",
                subservice=None,
                members=tuple(test_member_names),
                summary=test_summary,
            )

        return self._leak_entries

    def _record_leak_entry(
        self,
        *,
        scope: BugHandlerScope,
        service: str,
        subservice: str | None,
        members: tuple[str, ...],
        summary: ValgrindSummary,
    ) -> None:
        """
        Record a leak entry.

        :param scope: The scope of the leak entry.
        :param service: The service of the leak entry.
        :param subservice: The subservice of the leak entry.
        :param members: The members of the leak entry.
        :param summary: The summary of the leak entry.
        """
        if not summary.has_issues(self._config):
            return
        if self._config.bug_handler_scope is not scope:
            return
        if not summary or not members:
            return

        snapshot = copy.deepcopy(summary)
        self._leak_entries.append(
            ValgrindLeakEntry(
                service=service,
                subservice=subservice,
                members=members,
                summary=snapshot,
                scope=scope,
            )
        )
