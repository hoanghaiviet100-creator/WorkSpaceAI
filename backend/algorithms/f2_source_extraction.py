"""Conservative, extractive study-span recognition. Pure stdlib; no I/O.

Kinds describe textual patterns, not verified facts or guaranteed quiz items.
Returned text is a contiguous, verbatim substring of the supplied chunk.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class StudySpanKind(str, Enum):
    DEFINITION = "definition"
    FACT = "fact"
    EXAMPLE = "example"
    PROCEDURE = "procedure"


@dataclass(frozen=True)
class ExtractedStudySpan:
    kind: StudySpanKind
    text: str
    start_line: int  # Inclusive, 1-based within the chunk.
    end_line: int


_STEP = re.compile(r"^\s*(?:\d+[.)]\s+|(?:step|bước)\s+\d+\s*[:.)-]?\s+)\S", re.I)
_EXAMPLE = re.compile(r"^\s*(?:for example|e\.g\.|example|ví dụ|chẳng hạn)(?:\s*[:,–-]|\s)", re.I)
_DEFINITION = re.compile(
    r"^\s*(?P<term>[^:\n]{1,80}?)(?::\s+|\s+[–—-]\s+|\s+(?:is|are|means|refers to|là|được định nghĩa là)\s+)(?P<body>\S.*)$",
    re.I,
)
_NOISE = re.compile(
    r"^\s*(?:#{1,6}\s|[-_=*─━]{3,}\s*$|©|copyright\b|"
    r"(?:page|trang)\s+\d+(?:\s*(?:/|of)\s*\d+)?\s*$|"
    r"(?:lecture|chapter|section|slide|bài|chương|mục|course)\s+\d+\b|"
    r"(?:table of contents|mục lục)\s*$)|\.{3,}\s*\d+\s*$",
    re.I,
)
_WORDS = re.compile(r"\w+", re.UNICODE)


def extract_study_spans(text: str) -> tuple[ExtractedStudySpan, ...]:
    """Find definitions, examples, multi-step procedures and factual prose.

    Blank/noise lines split units. Soft-wrapped lines stay together. Generic
    prose needs >=3 word tokens and sentence punctuation or a numeric fact;
    these eligibility heuristics deliberately make no semantic guarantee.
    """
    raw_lines = text.splitlines(keepends=True)
    result: list[ExtractedStudySpan] = []
    start = 0
    pending: list[str] = []
    kind = StudySpanKind.FACT

    def flush() -> None:
        if not pending:
            return
        flat = " ".join(line.strip() for line in pending)
        words = _WORDS.findall(flat)
        alphabetic_words = sum(any(c.isalpha() for c in word) for word in words)
        usable = len(words) >= 3 and not flat.endswith("?")
        if kind == StudySpanKind.PROCEDURE:
            usable = sum(bool(_STEP.match(line)) for line in pending) >= 2
        elif kind == StudySpanKind.DEFINITION:
            match = _DEFINITION.match(pending[0])
            usable = bool(
                match and any(c.isalpha() for c in match["term"])
                and _WORDS.search(match["body"])
            ) and not flat.endswith("?")
        elif kind == StudySpanKind.FACT:
            usable = usable and alphabetic_words >= 2 and (
                flat.endswith((".", "!", ";")) or any(c.isdigit() for c in flat)
            )
        if usable:
            quote = "".join(raw_lines[start:start + len(pending)]).rstrip("\r\n")
            result.append(ExtractedStudySpan(kind, quote, start + 1, start + len(pending)))
        pending.clear()

    for index, raw in enumerate(raw_lines):
        line = raw.rstrip("\r\n")
        if not line.strip() or _NOISE.search(line):
            flush()
            continue
        marker = None
        if _STEP.match(line):
            marker = StudySpanKind.PROCEDURE
        elif _EXAMPLE.match(line):
            marker = StudySpanKind.EXAMPLE
        elif _DEFINITION.match(line):
            marker = StudySpanKind.DEFINITION
        continuing_steps = pending and marker == kind == StudySpanKind.PROCEDURE
        if marker is not None and not continuing_steps:
            flush()
        if not pending:
            start = index
            kind = marker or StudySpanKind.FACT
        pending.append(line)
    flush()
    return tuple(result)


__all__ = ["StudySpanKind", "ExtractedStudySpan", "extract_study_spans"]


def extract_contextual_study_spans(text: str) -> tuple[ExtractedStudySpan, ...]:
    """Keep original units and add heading+section evidence within this chunk.

    Context is a contiguous verbatim span, never a fabricated title appended
    to a quote. No cross-page/chunk inference. Original units/aliases retain
    their order; contextual spans follow them. Empty/noise-only sections add
    nothing. Preparation and inspection must use the same extractor.
    """
    original = extract_study_spans(text)
    lines = text.splitlines(keepends=True)
    heading = re.compile(r"^\s*(?:#{1,6}\s+\S|(?:Concepts?|Procedure|Rule|Policy|Function|Khái niệm|Quy trình|Quy tắc|Hàm)\s*:\s*\S)", re.I)
    starts = [i for i, line in enumerate(lines) if heading.match(line)]
    contexts = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
        # Standard page/copyright footer is outside the instructional section.
        for i in range(start + 1, stop):
            if re.match(r"\s*(?:copyright\b|©|(?:page|trang)\s+\d+\b)", lines[i], re.I):
                stop = i
                break
        while stop > start + 1 and not lines[stop - 1].strip():
            stop -= 1
        children = [s for s in original if s.start_line > start + 1 and s.end_line <= stop]
        if not children:
            continue
        quote = "".join(lines[start:stop]).rstrip("\r\n")
        if any(s.text == quote and s.start_line == start + 1 for s in original):
            continue
        kind = StudySpanKind.PROCEDURE if any(s.kind == StudySpanKind.PROCEDURE for s in children) else StudySpanKind.FACT
        contexts.append(ExtractedStudySpan(kind, quote, start + 1, stop))
    return (*original, *contexts)


__all__.append("extract_contextual_study_spans")
