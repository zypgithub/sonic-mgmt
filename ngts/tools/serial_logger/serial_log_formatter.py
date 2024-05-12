"""
Based on:
    sx_fit_regression/libs/scripts/logs_extractor/serial_log_formatter.py
"""

import argparse
import sys
import re
from datetime import datetime

ANSI_ESCAPE = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
LONG_SPACE = re.compile(r'\s{5,}')


def parse_args():
    cmd_line_parser = argparse.ArgumentParser(usage=__doc__,
                                              formatter_class=argparse.RawDescriptionHelpFormatter)
    cmd_line_parser.add_argument('-b', '--before', help='string to be inserted as before each log line',
                                 required=False, dest="before", default="")
    cmd_line_parser.add_argument('-a', '--after', help='string to be inserted as after each log line',
                                 required=False, dest="after", default="")
    args = cmd_line_parser.parse_args()
    if args.before:
        args.before = args.before.strip() + " "
    if args.after:
        args.after = " " + args.after.strip()
    return args


def main(parsed_args):
    """read lines from stdin, remove ANSI escape chars and long spaces, format log lines before writing to stdout"""
    # Receive lines from pipe stream
    input_line = sys.stdin.readline()
    while input_line:
        # Remove ASCII escape sequences
        input_line = ANSI_ESCAPE.sub('', input_line)
        # Replace long spaces with newline
        input_line = LONG_SPACE.sub('\n', input_line)
        for line in input_line.splitlines():
            line = line.strip()
            if len(line):
                # Add the current time to the line and print it
                sys.stdout.writelines(datetime.now().strftime("%b %d %H:%M:%S") + " " + parsed_args.before + line +
                                      parsed_args.after + "\n")
                sys.stdout.flush()
        # Read the next line
        input_line = sys.stdin.readline()


if __name__ == "__main__":
    main(parse_args())
