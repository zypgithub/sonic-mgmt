import re

PID_PREFIX_RE = re.compile(r"^==[^=]+==\s*")
ERR_SUM_RE = re.compile(r"ERROR SUMMARY:\s+(\d+)\s+errors")
INV_FD_RE = re.compile(r"^Warning:\s+invalid file descriptor\s+(\d+)\s+in syscall\s+(\w+)\(\)")
BYTES_RE = re.compile(r"([\d,]+)\s+bytes")
ADDR_NOISE_RE = re.compile(r'(0x[0-9A-Fa-f]+|\+\d+|:\d+)')  # hex addrs, +offs, :lineno
T_SPACE = 25
TRACE_ID_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{8,64}$")
LEAK_RECORD_RE = re.compile(
    r'^\s*'                                  # leading spaces
    r'([0-9,]+)'                             # 1: total bytes (with commas)
    r'(?:\s*\([^)]*\))?'                     # skip "(D direct, I indirect)" if present
    r'\s+bytes\s+in\s+([\d,]+)\s+blocks\s+are\s+'   # 2: blocks
    r'(definitely|indirectly|possibly)\s+lost\b',   # 3: kind
)


def strip_pid_prefix(s: str) -> str:
    # Fast path: most lines are not prefixed
    if not s.startswith('=='):
        return s
    # Find the closing '=='
    if (j := s.find('==', 2)) == -1:
        return s

    return s[j + 2:].lstrip()


def to_readable(bytes: int) -> str:
    suffixes = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']
    for i in range(len(suffixes)):
        if bytes < 1024:
            return f"{bytes:.2f} {suffixes[i]}B"
        bytes /= 1024
    return f"{bytes:.2f} {suffixes[-1]}B"
