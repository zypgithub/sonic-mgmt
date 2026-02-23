"""
EngineAdapterTool - Utility for running commands across SSH and serial engines.
"""

import re
import logging

logger = logging.getLogger(__name__)


class EngineAdapterTool:

    @staticmethod
    def run_cmd(engine, cmd, validate=False, timeout=30):
        """
        Run command on any engine type (SSH or serial) and return cleaned output.

        Args:
            engine: SSH or serial engine instance
            cmd: Command to execute
            validate: Validate success (SSH only)
            timeout: Command timeout

        Returns:
            Cleaned command output string
        """
        is_serial = hasattr(engine, 'serial_engine') or hasattr(engine, 'rcon_command')

        if is_serial:
            result = engine.run_cmd(cmd, timeout=timeout)
            output = result[0] if isinstance(result, tuple) else result
            # Clean: remove echoed command, carriage returns, prompt lines
            output = output.replace(cmd, '', 1).replace('\r', '')
            lines = [line for line in output.split('\n')
                     if line.strip() and not EngineAdapterTool._is_prompt(line)]
            return '\n'.join(lines)
        else:
            try:
                return engine.run_cmd(cmd, validate=validate, timeout=timeout)
            except TypeError:
                return engine.run_cmd(cmd, timeout=timeout)

    @staticmethod
    def _is_prompt(line):
        """Check if line is a shell prompt."""
        s = line.strip()
        return s.endswith('$') or s.endswith('#') or re.match(r'^\w+@[\w\-]+:[/~]', s)
