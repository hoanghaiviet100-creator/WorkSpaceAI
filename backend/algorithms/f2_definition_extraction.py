"""Shared literal definition extraction for offline study adapters; stdlib only."""
from __future__ import annotations

from collections.abc import Sequence
import re


_DEFINITION = re.compile(
    r"^(?P<term>[^:\n]{1,80}?)(?::\s+|\s+[–—-]\s+|\s+(?:is|are|means|refers to|là|được định nghĩa là)\s+)(?P<body>\S.*)$",
    re.I,
)


def _canonical(text: str) -> str:
    return " ".join(text.split()).casefold()


def extract_unambiguous_definitions(
    sources: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str, str], ...]:
    """Return (source_id, term, definition), preserving original source order.

    Same-term conflicting definitions and identical-definition aliases are
    excluded conservatively. This is literal deduplication, not semantic proof.
    """
    parsed: list[tuple[str, str, str]] = []
    definitions: dict[str, set[str]] = {}
    terms: dict[str, set[str]] = {}
    for source_id, quote in sources:
        match = _DEFINITION.match(" ".join(quote.split()))
        if not match or quote.rstrip().endswith("?"):
            continue
        term, body = match["term"].strip(), match["body"].strip()
        if not any(c.isalpha() for c in term):
            continue
        term_key, body_key = _canonical(term), _canonical(body)
        definitions.setdefault(term_key, set()).add(body_key)
        terms.setdefault(body_key, set()).add(term_key)
        parsed.append((source_id, term, body))
    eligible = []
    seen = set()
    for source_id, term, body in parsed:
        key = _canonical(term)
        if key in seen or len(definitions[key]) != 1 or len(terms[_canonical(body)]) != 1:
            continue
        seen.add(key)
        eligible.append((source_id, term, body))
    return tuple(eligible)


__all__ = ["extract_unambiguous_definitions"]
