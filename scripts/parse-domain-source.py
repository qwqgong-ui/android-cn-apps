#!/usr/bin/env python3
"""Convert an upstream domain rule source into validated Mihomo domain text."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain_rules import RuleError, strip_payload, validate  # noqa: E402

MAX_REPORTED = 20


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", required=True, choices=("list", "yaml"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    is_yaml = args.format == "yaml"
    rules: list[str] = []
    problems: list[str] = []
    with args.input.open(encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
            try:
                rule = strip_payload(line, yaml=is_yaml)
                if rule is None:
                    continue
                rules.append(validate(rule))
            except RuleError as error:
                problems.append(f"  line {number}: {error}")

    if problems:
        preview = "\n".join(problems[:MAX_REPORTED])
        extra = len(problems) - MAX_REPORTED
        if extra > 0:
            preview += f"\n  ... and {extra} more"
        print(f"error: {args.input.name} carries rules Mihomo cannot match:\n{preview}", file=sys.stderr)
        return 1
    if not rules:
        print(f"error: {args.input.name} has no domain rules", file=sys.stderr)
        return 1

    args.output.write_text("".join(f"{rule}\n" for rule in rules), encoding="utf-8")
    print(len(rules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
