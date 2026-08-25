"""Shared parsing and validation for Mihomo domain rule sources.

Upstream projects publish their rules as plain text (`.list`) or as a Clash
`payload:` YAML document. Those texts are the authoritative form: the `.mrs`
files they also publish are compiled artifacts of the same data, produced by a
Mihomo version we do not control. Reading the text and compiling it ourselves
keeps the semantics of the merged ruleset pinned to the Mihomo CLI this
repository pins.

`mihomo convert-ruleset domain text` accepts any line and stores it verbatim,
so a source that starts shipping classical rules (`DOMAIN-SUFFIX,example.com`),
Geosite attributes (`keyword:ads`, `regexp:^ad`), or IP literals would be baked
into reject-all.mrs as dead entries instead of failing the build. Every rule is
therefore validated against the domain patterns Mihomo can actually match.
"""

from __future__ import annotations

import ipaddress
import re

# A host label, which may carry `*` wildcards anywhere Mihomo accepts them --
# as a whole label (`*.example.com`) or inside one (`stun*.example.com`).
# Non-ASCII characters are allowed so IDN rules survive alongside punycode.
_LABEL_CHAR = r"(?:[^\W_]|\*)"
_LABEL = rf"(?:{_LABEL_CHAR}|{_LABEL_CHAR}[\w\-*]*{_LABEL_CHAR})"
_RULE = re.compile(rf"^(?:\+\.|\*\.|\.)?{_LABEL}(?:\.{_LABEL})*$", re.UNICODE)

_COMMENT_PREFIXES = ("#", "//", "!")


class RuleError(ValueError):
    """A source line that Mihomo's domain behavior cannot represent."""


def strip_payload(line: str, *, yaml: bool) -> str | None:
    """Return the rule text of a source line, or None when it carries none."""
    rule = line.strip()
    if not rule or rule.startswith(_COMMENT_PREFIXES):
        return None
    if yaml:
        if rule == "payload:":
            return None
        if not rule.startswith("-"):
            raise RuleError(f"unexpected YAML line outside the payload list: {line.strip()}")
        rule = rule[1:].strip()
        if len(rule) >= 2 and rule[0] == rule[-1] and rule[0] in "'\"":
            rule = rule[1:-1].strip()
        if not rule or rule.startswith(_COMMENT_PREFIXES):
            return None
    return rule.lower()


def bare_domain(rule: str) -> str:
    if rule.startswith("+."):
        return rule[2:]
    if rule.startswith("*."):
        return rule[2:]
    if rule.startswith("."):
        return rule[1:]
    return rule


def validate(rule: str) -> str:
    """Return the rule unchanged, or raise when Mihomo could not match it."""
    if not _RULE.match(rule):
        raise RuleError(f"not a Mihomo domain rule: {rule}")
    candidate = bare_domain(rule)
    if "*" not in candidate:
        try:
            ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            pass
        else:
            raise RuleError(f"IP/CIDR rule is not allowed in a domain ruleset: {rule}")
    return rule
