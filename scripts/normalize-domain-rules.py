#!/usr/bin/env python3
"""Normalize and conservatively prune Mihomo domain rule text files."""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import sys


def normalize(raw: str) -> str | None:
    rule = raw.strip()
    if not rule or rule.startswith("#") or rule.startswith("//"):
        return None
    return rule.lower()


def address_candidate(rule: str) -> str:
    if rule.startswith("+."):
        return rule[2:]
    if rule.startswith("."):
        return rule[1:]
    return rule


def reject_ip_rule(rule: str) -> None:
    candidate = address_candidate(rule)
    if "*" in candidate:
        return
    try:
        ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        return
    raise ValueError(f"IP/CIDR rule is not allowed in a domain ruleset: {rule}")


def suffixes(rules: set[str]) -> set[str]:
    result: set[str] = set()
    for rule in rules:
        if not rule.startswith("+."):
            continue
        suffix = rule[2:]
        if "*" not in suffix and suffix and not suffix.startswith("."):
            result.add(suffix)
    return result


def covered_by_suffix(rule: str, domain_suffixes: set[str]) -> bool:
    candidate = address_candidate(rule)
    labels = candidate.split(".")
    for index in range(len(labels)):
        suffix = ".".join(labels[index:])
        if "*" in suffix:
            continue
        if suffix in domain_suffixes and rule != f"+.{suffix}":
            return True
    return False


def load(paths: list[Path]) -> tuple[int, set[str]]:
    before = 0
    rules: set[str] = set()
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for raw in source:
                rule = normalize(raw)
                if rule is None:
                    continue
                before += 1
                reject_ip_rule(rule)
                rules.add(rule)
    return before, rules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stats", required=True, type=Path)
    args = parser.parse_args()

    before, exact_rules = load(args.inputs)
    domain_suffixes = suffixes(exact_rules)
    final_rules = sorted(
        rule for rule in exact_rules if not covered_by_suffix(rule, domain_suffixes)
    )

    if not final_rules:
        raise ValueError("normalization produced an empty domain ruleset")

    args.output.write_text("".join(f"{rule}\n" for rule in final_rules), encoding="utf-8")
    args.stats.write_text(
        f"merged_before={before}\n"
        f"exact_unique={len(exact_rules)}\n"
        f"pruned={len(exact_rules) - len(final_rules)}\n"
        f"normalized_final={len(final_rules)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
