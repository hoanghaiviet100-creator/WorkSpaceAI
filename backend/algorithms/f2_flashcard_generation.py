"""Extractive offline flashcards from literal definitions; pure stdlib, no I/O."""
from __future__ import annotations

from collections.abc import Sequence

from backend.algorithms.f2_definition_extraction import extract_unambiguous_definitions


DEFAULT_MAX_BACK_WORDS = 60


def build_definition_cards(
    sources: Sequence[tuple[str, str]], requested_count: int,
    *, max_back_words: int = DEFAULT_MAX_BACK_WORDS,
) -> list[dict[str, object]]:
    """Return up to count short cards; omit long answers rather than truncate."""
    if type(requested_count) is not int or requested_count < 1:
        raise ValueError("requested_count must be a positive integer")
    if type(max_back_words) is not int or max_back_words < 1:
        raise ValueError("max_back_words must be a positive integer")
    cards = []
    for source_id, term, definition in extract_unambiguous_definitions(sources):
        if len(definition.split()) > max_back_words:
            continue
        cards.append({
            "front": f"{term} là gì?", "back": definition,
            "source_ids": [source_id],
        })
        if len(cards) == requested_count:
            break
    return cards


__all__ = ["DEFAULT_MAX_BACK_WORDS", "build_definition_cards"]
