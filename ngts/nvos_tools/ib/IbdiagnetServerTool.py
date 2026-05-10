import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

DEFAULT_OUTPUT_PATH = '/tmp/ibdiagnet_output'
IBDIAGNET_CMD = 'ibdiagnet'
IBDIAGNET_LOG_FILE = 'ibdiagnet2.log'
IBDIAGNET_DB_CSV_FILE = 'ibdiagnet2.db_csv'


@dataclass
class IbdiagnetStageSummary:
    """A single row from the ibdiagnet summary table (stage name, warning count, error count)."""
    stage: str
    warnings: int
    errors: int
    comment: str = ''


@dataclass
class IbdiagnetResult:
    """Parsed result of an ibdiagnet run.

    Attributes:
        stdout: Raw ibdiagnet stdout output.
        output_path: Directory where output files were written.
        summary: Parsed summary table rows.
        error_lines: Messages from -E- lines (prefix stripped).
        warning_lines: Messages from -W- lines (prefix stripped).
    """
    stdout: str
    output_path: str
    summary: List[IbdiagnetStageSummary] = field(default_factory=list)
    error_lines: List[str] = field(default_factory=list)
    warning_lines: List[str] = field(default_factory=list)

    @property
    def total_warnings(self) -> int:
        return sum(s.warnings for s in self.summary)

    @property
    def total_errors(self) -> int:
        return sum(s.errors for s in self.summary)


class IbdiagnetServerTool:
    """Runs ibdiagnet from an external server (hfnm engine) and parses the results.

    Unlike the DUT-side Ibdiagnet class which uses NVUE CLI commands, this tool
    runs ibdiagnet directly as a Linux command on the hfnm host.
    """

    _SUMMARY_LINE_RE = re.compile(
        r'^-I-\s+(.+?)\s{2,}(\d+)\s+(\d+)\s*(.*)?$'
    )
    _ERROR_LINE_RE = re.compile(r'^-E-\s+(.*)')
    _WARNING_LINE_RE = re.compile(r'^-W-\s+(.*)')

    @staticmethod
    def build_command(get_phy_info=True, enabled_regs=None,
                      output_path=DEFAULT_OUTPUT_PATH,
                      long_run_iteration=None, long_run_timeout=None,
                      extra_args='') -> str:
        """Build the ibdiagnet command string.

        Args:
            get_phy_info: Include --get_phy_info flag.
            enabled_regs: Comma-separated register names (e.g. 'pemi,pddr').
            output_path: Directory for output files. Ignored when long_run_iteration is set.
            long_run_iteration: Number of iterations. When set, ibdiagnet writes to stdout only.
            long_run_timeout: Long-run timeout in milliseconds.
            extra_args: Additional raw arguments to append.
        """
        parts = [IBDIAGNET_CMD]
        if get_phy_info:
            parts.append('--get_phy_info')
        if enabled_regs:
            parts.append(f'--enabled_regs {enabled_regs}')
        if output_path and not long_run_iteration:
            parts.append(f'-o {output_path}')
        if long_run_iteration:
            parts.append(f'--long_run_iteration {long_run_iteration}')
        if long_run_timeout:
            parts.append(f'--long_run_timeout {long_run_timeout}')
        if extra_args:
            parts.append(extra_args)
        return ' '.join(parts)

    @staticmethod
    def run(engine, output_path=DEFAULT_OUTPUT_PATH, timeout=300, **cmd_kwargs) -> IbdiagnetResult:
        """Run ibdiagnet on the given engine and return parsed results.

        Args:
            engine: SSH engine for the hfnm host.
            output_path: Directory for output files.
            timeout: Command timeout in seconds.
            **cmd_kwargs: Passed to build_command().
        """
        cmd_kwargs.setdefault('output_path', output_path)

        if not cmd_kwargs.get('long_run_iteration'):
            with allure.step('Prepare ibdiagnet output directory'):
                engine.run_cmd(f'rm -rf {output_path} && mkdir -p {output_path}')

        cmd = IbdiagnetServerTool.build_command(**cmd_kwargs)

        with allure.step(f'Run ibdiagnet on server: {cmd}'):
            logger.info(f'Running ibdiagnet command: {cmd}')
            stdout = engine.run_cmd(cmd, timeout=timeout)

        lines = stdout.splitlines()
        result = IbdiagnetResult(stdout=stdout, output_path=output_path)
        result.summary = IbdiagnetServerTool._parse_summary(lines)
        result.error_lines = IbdiagnetServerTool._extract_lines(lines, IbdiagnetServerTool._ERROR_LINE_RE)
        result.warning_lines = IbdiagnetServerTool._extract_lines(lines, IbdiagnetServerTool._WARNING_LINE_RE)

        logger.info(f'ibdiagnet result: {result.total_errors} errors, '
                    f'{result.total_warnings} warnings across {len(result.summary)} stages')
        return result

    @staticmethod
    def get_log_content(engine, output_path=DEFAULT_OUTPUT_PATH) -> str:
        """Read the ibdiagnet2.log file from the output directory."""
        return engine.run_cmd(f'cat {output_path}/{IBDIAGNET_LOG_FILE}')

    @staticmethod
    def get_output_files(engine, output_path=DEFAULT_OUTPUT_PATH) -> List[str]:
        """List files in the ibdiagnet output directory."""
        return engine.run_cmd(f'ls {output_path}').split()

    @staticmethod
    def cleanup(engine, output_path=DEFAULT_OUTPUT_PATH):
        """Remove the ibdiagnet output directory."""
        engine.run_cmd(f'rm -rf {output_path}')

    # ---- Parsing ----

    @staticmethod
    def _parse_summary(lines: List[str]) -> List[IbdiagnetStageSummary]:
        """Parse the Summary table from ibdiagnet output lines.

        Expects the format:
            Summary
            -I- Stage                               Warnings   Errors     Comment
            -I- Discovery                           0          2
            ...
        """
        summary = []
        in_summary = False

        for line in lines:
            if line.strip() == 'Summary':
                in_summary = True
                continue

            if in_summary:
                match = IbdiagnetServerTool._SUMMARY_LINE_RE.match(line)
                if match:
                    stage_name = match.group(1).strip()
                    if stage_name == 'Stage':
                        continue
                    summary.append(IbdiagnetStageSummary(
                        stage=stage_name,
                        warnings=int(match.group(2)),
                        errors=int(match.group(3)),
                        comment=match.group(4).strip() if match.group(4) else '',
                    ))
                elif summary and not line.startswith('-I-'):
                    break

        return summary

    @staticmethod
    def _extract_lines(lines: List[str], pattern: re.Pattern) -> List[str]:
        """Extract the message portion (capture group 1) from lines matching the pattern.

        For example, with the -E- pattern, '-E- some error' returns 'some error'.
        """
        return [match.group(1) for line in lines if (match := pattern.match(line))]
