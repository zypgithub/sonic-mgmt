import logging
import re
from typing import List, Optional, Set

from ngts.nvos_tools.ib.IbdiagnetServerTool import IbdiagnetResult
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

IBDIAGNET_EXPECTED_OUTPUT_FILES = [
    'ibdiagnet2.log', 'ibdiagnet2.db_csv', 'ibdiagnet2.lst',
    'ibdiagnet2.net_dump', 'ibdiagnet2.pm', 'ibdiagnet2.nodes_info',
]

# Speed-check errors on multiplanar smi2 self-loopback links are not real fabric
# issues: smi2 exposes 4 SMI sub-ports per HCA port, and ibdiagnet reports the
# virtual links between sub-ports of the same HCA (same GUID both ends) as if they
# were physical. Their advertised enable_speed lists can include placeholder
# entries (e.g. "10") and the resolved "speed" has no physical meaning. The
# regex matches: "Sc<guid>/...HCA...p<N>s<M><-->Sc<guid>/...HCA...p<N>s<M>" — i.e.
# both endpoints carrying the same node GUID.
_SMI_SELF_LOOPBACK_RE = re.compile(
    r'Link:\s*S(?P<guid>[0-9a-fA-F]+)/[^<]*<-->S(?P=guid)/'
)


def _is_smi_self_loopback_speed_error(line: str) -> bool:
    """Match speed-check errors on smi2 SMI self-loopback (same-GUID both ends)."""
    return ('Unexpected actual link speed' in line and
            bool(_SMI_SELF_LOOPBACK_RE.search(line)))


def verify_opensm_running(engines):
    """Verify OpenSM is running on the hfnm host. Start it if not running."""
    with allure.step('Verify OpenSM is running on hfnm'):
        is_running, _ = OpenSmTool.is_sm_running_on_server(engines)
        if is_running:
            logger.info('OpenSM is already running on hfnm')
            return

        logger.info('OpenSM is not running, starting it...')
        result = OpenSmTool.start_open_sm(engines)
        result.verify_result()


def verify_ibdiagnet_no_errors(result: IbdiagnetResult,
                               ignored_warning_stages: Optional[Set[str]] = None,
                               ignored_error_patterns: Optional[List[str]] = None) -> ResultObj:
    """Verify ibdiagnet results have no errors or warnings.

    Args:
        result: Parsed IbdiagnetResult from a run.
        ignored_warning_stages: Stage names whose warnings to ignore. Empty by default.
        ignored_error_patterns: Error message substrings to ignore. Empty by default.
            Speed-check errors on multiplanar smi2 self-loopback links (same GUID
            on both ends) are always ignored on multiplanar setups regardless of
            this argument — see `_is_smi_self_loopback_speed_error`.

    Returns:
        ResultObj with pass/fail and a formatted report as info.
    """
    if ignored_warning_stages is None:
        ignored_warning_stages = set()
    if ignored_error_patterns is None:
        ignored_error_patterns = []

    with allure.step('Analyze ibdiagnet results for errors and warnings'):
        # Classify warnings by stage
        real_warnings = []
        ignored_warnings = []
        for stage in result.summary:
            if stage.warnings > 0:
                if stage.stage in ignored_warning_stages:
                    ignored_warnings.append(stage)
                else:
                    real_warnings.append(stage)

        # Classify error lines by pattern.
        # On multiplanar setups, speed-check errors on smi2 SMI self-loopback
        # links are virtual-link artifacts, not real fabric issues - drop them.
        real_error_lines = []
        ignored_error_lines = []
        suppress_smi_loopback = OpenSmTool.MULTI_PLANAR
        for line in result.error_lines:
            if ignored_error_patterns and any(p in line for p in ignored_error_patterns):
                ignored_error_lines.append(line)
            elif suppress_smi_loopback and _is_smi_self_loopback_speed_error(line):
                ignored_error_lines.append(line)
            else:
                real_error_lines.append(line)

        # Filter warning lines to only show those from non-ignored stages
        ignored_stage_names = {s.stage for s in ignored_warnings}
        real_warning_lines = [line for line in result.warning_lines
                              if not any(stage in line for stage in ignored_stage_names)]

        passed = len(real_error_lines) == 0 and len(real_warnings) == 0
        info = _format_report(result, real_error_lines, real_warning_lines,
                              real_warnings, ignored_error_lines, ignored_warnings, passed)
        logger.info(f'ibdiagnet analysis:\n{info}')
        return ResultObj(passed, info)


def _format_report(result, real_error_lines, real_warning_lines,
                   real_warnings, ignored_error_lines, ignored_warnings, passed):
    """Format the ibdiagnet analysis into a readable report."""
    sections = []

    # Summary table
    sections.append('ibdiagnet Summary:')
    sections.append(f'  {"Stage":<35} {"Warnings":>10} {"Errors":>10}')
    sections.append(f'  {"-" * 57}')
    for stage in result.summary:
        marker = '> ' if stage.errors > 0 or stage.warnings > 0 else '  '
        sections.append(f'{marker}{stage.stage:<35} {stage.warnings:>10} {stage.errors:>10}')

    # Errors detail
    if real_error_lines:
        sections.append('')
        sections.append('Errors:')
        for line in real_error_lines:
            sections.append(f'  -E- {line}')

    # Warnings detail
    if real_warnings:
        sections.append('')
        sections.append('Warnings:')
        for line in real_warning_lines:
            sections.append(f'  -W- {line}')
        for stage in real_warnings:
            sections.append(f'  {stage.stage}: {stage.warnings} warning(s) total')

    # Ignored (for visibility)
    if ignored_error_lines or ignored_warnings:
        sections.append('')
        sections.append('Ignored:')
        for line in ignored_error_lines:
            sections.append(f'  -E- {line}')
        for stage in ignored_warnings:
            sections.append(f'  {stage.stage}: {stage.warnings} warning(s)')

    # Result
    sections.append('')
    if passed:
        sections.append('Result: PASSED')
    else:
        sections.append(f'Result: FAILED ({len(real_error_lines)} error(s), '
                        f'{sum(s.warnings for s in real_warnings)} warning(s))')

    return '\n'.join(sections)
