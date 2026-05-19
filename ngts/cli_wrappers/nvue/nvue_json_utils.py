"""Helpers for parsing NVUE ``-o json`` CLI output."""

import json
from json.decoder import JSONDecodeError


def parse_nvue_json_cli_output(text):
    """Decode the first JSON object from NVUE CLI stdout.

    SSH sessions may prepend kernel ``wall``/MOTD lines (e.g. ``Broadcast message from
    root@...``) before ``nv show ... -o json`` output. ``json.loads`` on the full string
    then fails with ``JSONDecodeError``.

    Args:
        text: Raw command output (str or bytes).

    Returns:
        Parsed JSON as dict/list/primitive.

    Raises:
        json.decoder.JSONDecodeError: If no JSON object is found or it is invalid.
    """
    if text is None:
        raise JSONDecodeError("Expecting value", str(text), 0)
    stripped = str(text).lstrip()
    start = stripped.find("{")
    if start == -1:
        raise JSONDecodeError("Expecting value", stripped, 0)
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(stripped, start)
    return obj
