#!/usr/bin/env python3

from argparse import ArgumentParser, Namespace
from pathlib import Path
import json


def _scan(root: Path) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for path in root.glob('**/vg.*'):
        try:
            st = path.stat()
        except OSError:
            # File might disappear between walk and stat; ignore
            continue
        rel_path = path.relative_to(root)
        snapshot[str(rel_path)] = st.st_size
    return snapshot


class Args(Namespace):
    root: Path
    output: Path | None


def _parse_args() -> Args:
    parser = ArgumentParser(
        description="Scan Valgrind log directory and output file sizes as JSON."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default="/var/log/valgrind",
        help="Root directory to scan (default: /var/log/valgrind)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file (default: stdout)",
    )
    return parser.parse_args(namespace=Args())


def main() -> None:
    args = _parse_args()
    snapshot = _scan(args.root)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        print(f"Snapshot saved to: {args.output}")
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
