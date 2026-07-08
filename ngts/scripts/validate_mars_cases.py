#!/usr/bin/env python3
"""
Validate MARS .cases XML files for structural correctness.

Catches bugs like duplicate <name> tags or <static_args> orphaned outside
a <cmd> block, which cause MARS to init a case with name=None and crash.

Usage:
    python3 validate_mars_cases.py [root_dir]

    root_dir defaults to the repo root (two levels up from this script).
"""
import sys
import os
import glob
import xml.etree.ElementTree as ET


def validate_cases_file(path):
    errors = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]

    root = tree.getroot()
    expected_root = "CASE" + "DEF"
    if root.tag != expected_root:
        errors.append(f"Root element must be <{expected_root}>, got <{root.tag}>")

    for i, case in enumerate(root.findall("case")):
        case_label = f"case[{i}]"

        # Each <case> must have exactly one <name> direct child with non-empty text
        names = case.findall("name")
        if len(names) == 0:
            errors.append(f"{case_label}: missing <name>")
        elif len(names) > 1:
            name_values = [n.text.strip() if n.text else "" for n in names]
            errors.append(
                f"{case_label}: duplicate <name> tags: {name_values}"
            )
        else:
            name_text = names[0].text.strip() if names[0].text else ""
            if not name_text:
                errors.append(f"{case_label}: <name> is empty")
            else:
                case_label = f"case '{name_text}'"

        # <static_args> must live under <cmd>/<params>, never directly under <case>
        orphan_static_args = case.findall("static_args")
        if orphan_static_args:
            errors.append(
                f"{case_label}: <static_args> found directly under <case> "
                "(must be inside <cmd>/<params>/<static_args>)"
            )

        # Each <case> must have at least one <cmd> with <params>/<static_args>
        cmds = case.findall("cmd")
        if not cmds:
            errors.append(f"{case_label}: no <cmd> block found")
        else:
            for j, cmd in enumerate(cmds):
                params = cmd.find("params")
                if params is None:
                    errors.append(f"{case_label} cmd[{j}]: missing <params>")
                elif params.find("static_args") is None:
                    errors.append(
                        f"{case_label} cmd[{j}]: <params> has no <static_args>"
                    )

    return errors


_CASES_DIRS = [
    "nvos-tool/mars/cases",
]


def find_cases_files(root_dir):
    files = []
    for subdir in _CASES_DIRS:
        pattern = os.path.join(root_dir, subdir, "**", "*.cases")
        files.extend(glob.glob(pattern, recursive=True))
    return files


def main():
    root_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", ".."
    )
    root_dir = os.path.abspath(root_dir)

    cases_files = find_cases_files(root_dir)
    if not cases_files:
        print(f"No .cases files found under {root_dir}")
        return 0

    failed = []
    for path in sorted(cases_files):
        errors = validate_cases_file(path)
        if errors:
            rel = os.path.relpath(path, root_dir)
            failed.append((rel, errors))

    if failed:
        print("MARS cases validation FAILED:\n")
        for rel, errors in failed:
            print(f"  {rel}:")
            for err in errors:
                print(f"    - {err}")
        print(f"\n{len(failed)} file(s) with errors.")
        return 1

    print(f"MARS cases validation passed ({len(cases_files)} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
