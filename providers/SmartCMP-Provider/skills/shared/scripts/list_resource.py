#!/usr/bin/env python3
"""List SmartCMP resource details by resource ID."""

import argparse
import sys


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List SmartCMP resource details by resource ID."
    )
    parser.add_argument("resource_ids", nargs="+")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    _ = parse_args(argv)
    print("list-resource placeholder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
