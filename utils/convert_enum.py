#!/usr/bin/python3
# File name: convert_enum.py
# This file is part of: python3-openttd
#
# LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# FEEDBACK & QUESTIONS
#
# For feedback and questions about python3-openttd please e-mail one of
# the authors named in the AUTHORS file.
########################################################################
"""
Helper script to convert a C++ enum to a Python3 enum.
"""
import re

def parse_values(lines):
    decl_re = re.compile(
        r"(?P<name>[A-Z_]+)(\s*=\s*(?P<value>([0-9]+|0x[0-9a-fA-F]+)))?\s*,(\s*///<\s*(?P<comment>.*))?"
        # r"[A-Z_].*"
    )

    for line in lines:
        line = line.strip()
        match = decl_re.match(line)
        if not match:
            continue

        named_groups = match.groupdict()
        name = named_groups["name"]
        value = named_groups["value"]
        comment = named_groups["comment"]
        if value is not None:
            if value.startswith("0x"):
                value = int(value[2:], 16)
            else:
                value = int(value)

        yield name, value, comment

def strip_prefixes(decls, prefix):
    prefixlen = len(prefix)
    for name, value, comment in decls:
        if name.startswith(prefix):
            name = name[prefixlen:]
        yield name, value, comment

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--strip-prefix",
        default=None,
        help="Prefix to strip from enumeration values"
    )
    parser.add_argument(
        "-i", "--indent",
        type=int,
        default=1,
        help="Level of indent for the output"
    )

    args = parser.parse_args()
    if args.indent < 0:
        print("negative indent? you’re insane.", file=sys.stderr)
        sys.exit(1)

    decls = parse_values(sys.stdin)
    if args.strip_prefix is not None:
        decls = strip_prefixes(decls, args.strip_prefix)

    indent = "    "*args.indent

    prev_value = -1
    for name, value, comment in decls:
        if value is None:
            value = prev_value + 1

        if comment is not None:
            print("{indent}#: {}".format(comment, indent=indent))
        print("{indent}{} = {}".format(name, value, indent=indent))

        prev_value = value
