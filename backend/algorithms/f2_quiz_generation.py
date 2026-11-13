"""Extractive definition MCQs for the offline adapter. Pure stdlib, no I/O.

Distractors are other distinct source terms, never invented factual statements.
Ambiguous repeated terms/definitions are excluded. This is not a semantic
answer verifier and deliberately does not generate from arbitrary prose.
"""
from __future__ import annotations

from collections.abc import Sequence
from backend.algorithms.f2_definition_extraction import extract_unambiguous_definitions


def build_definition_questions(
    sources: Sequence[tuple[str, str]], requested_count: int
) -> list[dict[str, object]]:
    """Return up to requested_count questions from unambiguous definitions.

    Each input pair is (server-assigned source ID, verbatim passage text).
    Options contain 2–4 source terms depending on available distinct content.
    """
    eligible = extract_unambiguous_definitions(sources)
    if len(eligible) < 2:
        return []
    questions = []
    for index, (source_id, term, body) in enumerate(eligible[:requested_count]):
        choices = [eligible[(index + offset) % len(eligible)][1] for offset in range(min(4, len(eligible)))]
        rotation = index % len(choices)
        choices = choices[rotation:] + choices[:rotation]
        options = [{"option_id": chr(65 + i), "text": text} for i, text in enumerate(choices)]
        key = next(option["option_id"] for option in options if option["text"] == term)
        questions.append({
            "question": f"Khái niệm nào được mô tả sau đây?\n{body}",
            "options": options,
            "correct_option_id": key,
            "explanation": f"Theo đoạn nguồn, {term}: {body}",
            "source_ids": [source_id],
        })
    return questions


__all__ = ["build_definition_questions"]
