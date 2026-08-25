#!/usr/bin/env python3
"""Resolve a v2fly domain-list-community list into Mihomo rules.

MetaCubeX's geosite `.list`/`.mrs` files are themselves built from
https://github.com/v2fly/domain-list-community, and that build drops every
entry a domain rule-set cannot hold. Resolving the list data here instead
means the merged ruleset comes from the list source rather than from someone
else's rendering of it, and that the entries a domain MRS cannot hold are
reported rather than lost.

The parsing, attribute filtering, inclusion resolution and redundant-subdomain
pruning below follow domain-list-community's own `main.go`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

MAX_DOMAIN_LEN = 253
MAX_LABEL_LEN = 63

DOMAIN, FULL, KEYWORD, REGEXP, INCLUDE = "domain", "full", "keyword", "regexp", "include"


class DataError(ValueError):
    pass


class Entry:
    __slots__ = ("type", "value", "attrs", "plain")

    def __init__(self, type_: str, value: str, attrs: tuple[str, ...]) -> None:
        self.type = type_
        self.value = value
        self.attrs = attrs
        self.plain = f"{type_}:{value}"
        if attrs:
            self.plain += ":" + ",".join(f"@{attr}" for attr in attrs)


class Inclusion:
    __slots__ = ("source", "must", "ban")

    def __init__(self, source: str, must: list[str], ban: list[str]) -> None:
        self.source = source
        self.must = must
        self.ban = ban


class ParsedList:
    __slots__ = ("inclusions", "entries", "rough", "final")

    def __init__(self) -> None:
        self.inclusions: list[Inclusion] = []
        self.entries: list[Entry] = []
        self.rough: dict[str, Entry] | None = None
        self.final: list[Entry] | None = None


def valid_domain_chars(value: str) -> bool:
    return bool(value) and all(
        ("a" <= c <= "z") or ("0" <= c <= "9") or c in ".-" for c in value
    )


def valid_domain_name(value: str) -> bool:
    if not valid_domain_chars(value) or len(value) > MAX_DOMAIN_LEN:
        return False
    return all(
        label and len(label) <= MAX_LABEL_LEN and label[0] != "-" and label[-1] != "-"
        for label in value.split(".")
    )


def parse_data(data_dir: Path) -> dict[str, ParsedList]:
    lists: dict[str, ParsedList] = {}

    def get(name: str) -> ParsedList:
        return lists.setdefault(name, ParsedList())

    for path in sorted(data_dir.iterdir()):
        if not path.is_file():
            continue
        parsed = get(path.name.upper())
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            where = f"{path.name}:{number}"
            type_, separator, rule = line.partition(":")
            if not separator:
                type_, rule = DOMAIN, type_
            else:
                type_ = type_.lower()
            fields = rule.split()
            if not fields:
                raise DataError(f"{where}: empty rule")
            if type_ == INCLUDE:
                parsed.inclusions.append(parse_inclusion(fields, where))
                continue
            entry, affiliations = parse_entry(type_, fields, where)
            for affiliation in affiliations:
                get(affiliation).entries.append(entry)
            parsed.entries.append(entry)
    return lists


def parse_inclusion(fields: list[str], where: str) -> Inclusion:
    must: list[str] = []
    ban: list[str] = []
    for field in fields[1:]:
        if field[0] != "@":
            raise DataError(f"{where}: unknown inclusion field {field!r}")
        attr = field[1:].lower()
        if attr.startswith("-"):
            ban.append(attr[1:])
        else:
            must.append(attr)
    return Inclusion(fields[0].upper(), must, ban)


def parse_entry(type_: str, fields: list[str], where: str) -> tuple[Entry, list[str]]:
    if type_ == REGEXP:
        value = fields[0]
    elif type_ in (DOMAIN, FULL):
        value = fields[0].lower()
        if not valid_domain_name(value):
            raise DataError(f"{where}: invalid domain {value!r}")
    elif type_ == KEYWORD:
        value = fields[0].lower()
        if not valid_domain_chars(value):
            raise DataError(f"{where}: invalid keyword {value!r}")
    else:
        raise DataError(f"{where}: unknown rule type {type_!r}")

    attrs: set[str] = set()
    affiliations: list[str] = []
    for field in fields[1:]:
        if field[0] == "@":
            attrs.add(field[1:].lower())
        elif field[0] == "&":
            affiliations.append(field[1:].upper())
        else:
            raise DataError(f"{where}: unknown field {field!r}")
    return Entry(type_, value, tuple(sorted(attrs))), affiliations


def matches(entry: Entry, inclusion: Inclusion) -> bool:
    if not entry.attrs:
        return not inclusion.must
    if any(attr not in entry.attrs for attr in inclusion.must):
        return False
    return not any(attr in entry.attrs for attr in inclusion.ban)


def polish(rough: dict[str, Entry]) -> list[Entry]:
    """Drop subdomains already covered by a parent `domain:` entry."""
    final: list[Entry] = []
    queued: list[Entry] = []
    parents: set[str] = set()
    for entry in rough.values():
        if entry.type in (REGEXP, KEYWORD):
            final.append(entry)
            continue
        if entry.type == DOMAIN:
            parents.add(entry.value)
            if entry.attrs:
                parents.add(entry.plain.split(":", 1)[1])
        queued.append(entry)

    for entry in queued:
        parent = entry.value if not entry.attrs else entry.plain.split(":", 1)[1]
        if entry.type == FULL:
            # So that `domain:example.org` overrides `full:example.org`.
            parent = "." + parent
        redundant = False
        while True:
            _, separator, parent = parent.partition(".")
            if not separator:
                break
            if parent in parents:
                redundant = True
                break
        if not redundant:
            final.append(entry)
    return sorted(final, key=lambda entry: entry.plain)


def resolve(lists: dict[str, ParsedList], name: str, resolving: set[str]) -> ParsedList:
    parsed = lists.get(name)
    if parsed is None:
        raise DataError(f"list {name!r} not found")
    if parsed.rough is not None:
        return parsed
    if name in resolving:
        raise DataError(f"circular inclusion in {name!r}")
    resolving.add(name)

    rough = {entry.plain: entry for entry in parsed.entries}
    for inclusion in parsed.inclusions:
        included = resolve(lists, inclusion.source, resolving)
        take_all = not inclusion.must and not inclusion.ban
        assert included.rough is not None
        for entry in included.rough.values():
            if take_all or matches(entry, inclusion):
                rough[entry.plain] = entry

    parsed.rough = rough
    parsed.final = polish(rough)
    resolving.discard(name)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--list", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--unsupported", required=True, type=Path)
    args = parser.parse_args()

    lists = parse_data(args.data)
    resolved = resolve(lists, args.list.upper(), set())
    assert resolved.final is not None

    rules: list[str] = []
    unsupported: list[str] = []
    for entry in resolved.final:
        if entry.type == DOMAIN:
            rules.append(f"+.{entry.value}")
        elif entry.type == FULL:
            rules.append(entry.value)
        elif entry.type == KEYWORD:
            unsupported.append(f"DOMAIN-KEYWORD,{entry.value}")
        else:
            unsupported.append(f"DOMAIN-REGEX,{entry.value}")

    if not rules:
        raise DataError(f"list {args.list!r} resolved to no domain rules")

    args.output.write_text("".join(f"{rule}\n" for rule in sorted(set(rules))), encoding="utf-8")
    args.unsupported.write_text(
        "".join(f"{rule}\n" for rule in sorted(set(unsupported))), encoding="utf-8"
    )
    print(len(set(rules)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DataError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
