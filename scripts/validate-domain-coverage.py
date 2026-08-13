#!/usr/bin/env python3
"""Check that every custom domain rule is represented by the final rule text."""

from __future__ import annotations

import argparse
from pathlib import Path


def read_rules(path: Path) -> set[str]:
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "//"))
    }


def covered(rule: str, final: set[str]) -> bool:
    if rule in final:
        return True

    candidate = rule[2:] if rule.startswith("+.") else rule.lstrip(".")
    labels = candidate.split(".")
    for index in range(len(labels)):
        suffix = ".".join(labels[index:])
        if "*" not in suffix and f"+.{suffix}" in final:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    args = parser.parse_args()

    custom = read_rules(args.custom)
    final = read_rules(args.final)
    missing = sorted(rule for rule in custom if not covered(rule, final))
    if missing:
        preview = "\n".join(f"  - {rule}" for rule in missing[:20])
        raise SystemExit(f"custom rules missing from final semantics:\n{preview}")

    exact_samples = sorted(custom & final)[:5]
    if not exact_samples:
        raise SystemExit("no custom rule remains as an exact sample in final ruleset")

    print("Custom rule samples found exactly in reject-all.mrs dump:")
    for rule in exact_samples:
        print(f"  - {rule}")
    print(f"All {len(custom)} accepted custom rules are semantically covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
