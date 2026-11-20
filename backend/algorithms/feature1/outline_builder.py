"""Build an outline over indexed text without changing citation coordinates."""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable

from backend.core.schemas import DocumentChunk, DocumentHeading


NUMBERED = re.compile(
    r"^(?:chapter\s+|chương\s+)?(\d+(?:\.\d+)*)(?:[.:)]\s*|\s+)(\S.*)$", re.I
)
APPENDIX = re.compile(
    r"^(?:appendix|phụ lục)(?:\s+[\w]+)?(?:\s*[:.\-–—]\s*|\s+|$)", re.I
)
CONTENTS = {"contents", "table of contents", "mục lục"}
SUPPORTING_TITLES = CONTENTS | {
    "giới thiệu",
    "how to use this tutorial",
    "further reading",
    "tài liệu tham khảo",
}
DOT_LEADER = re.compile(r"(?:\.\s*){3,}|\s{3,}\d+\s*$")
TOC_ENTRY = re.compile(r"^(.+?)\s*(?:\.\s*){3,}(\d+)\s*$")
STRUCTURED_LINE = re.compile(r"^(?:[$>]|(?:git|gh|python|pip)\s|\s{2,}|\|)|\s[|│]\s|\t")
CHAPTER_MARKER = re.compile(r"^(?:chapter|chương|section|part|phần)\s+(\d+)\s*$", re.I)
MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_INTRO = re.compile(r"^(?:bài tập|câu hỏi|các bước|danh sách|exercise[s]?|questions?|steps?|checklist)\b", re.I)
EXERCISE_TITLE = re.compile(r"^(?:lim\b|[\w]+\s*[.(]\s*[\w]+[,;]|[\w]+\s*(?:=|[+−÷×]|[A-Z]\s+[\w]+\())")
DAMAGED_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]|\b[\w]+\.\s*\w+\s*;\s*\w+\s*/D\b")


def has_damaged_text(text: str) -> bool:
    """Identify signs of unmapped PDF glyphs while retaining source coordinates."""
    return bool(DAMAGED_TEXT.search(text))


@dataclass(frozen=True)
class SourceBlock:
    page: int
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class OutlineSection:
    id: str
    title: str
    level: int
    start_page: int
    end_page: int
    kind: str
    blocks: tuple[SourceBlock, ...]
    parent_id: str | None = None

    @property
    def content(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)

    @property
    def counts_for_coverage(self) -> bool:
        return self.parent_id is None and self.title.casefold() not in SUPPORTING_TITLES


def indexed_blocks(chunks: Iterable[DocumentChunk]) -> dict[tuple[int, int], str]:
    """Recover line order and remove overlapping copies created at ingestion."""
    lines = {}
    for chunk in chunks:
        for number, line in enumerate(chunk.text.splitlines(), chunk.start_line):
            lines[chunk.page_number, number] = line
    return dict(sorted(lines.items()))


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _title_matches(title: str, line: str) -> bool:
    title, line = _normalized(title), _normalized(line)
    return bool(
        title
        and line
        and (
            title == line
            or (len(line) >= 12 and title.startswith(line + " "))
            or SequenceMatcher(None, title, line).ratio() >= 0.86
        )
    )


def _blocks(rows: list[tuple[tuple[int, int], str]]) -> tuple[SourceBlock, ...]:
    """Keep adjacent explanation and structured lines in the same source block."""
    blocks = []
    current: list[tuple[tuple[int, int], str]] = []
    for (page, line), text in rows:
        if current and (page != current[-1][0][0] or line != current[-1][0][1] + 1):
            blocks.append(
                SourceBlock(
                    current[0][0][0],
                    current[0][0][1],
                    current[-1][0][1],
                    "\n".join(value for _, value in current),
                )
            )
            current = []
        current.append(((page, line), text))
    if current:
        blocks.append(
            SourceBlock(
                current[0][0][0],
                current[0][0][1],
                current[-1][0][1],
                "\n".join(value for _, value in current),
            )
        )
    return tuple(blocks)


def build_outline(
    chunks: Iterable[DocumentChunk], headings: Iterable[DocumentHeading] = ()
) -> list[OutlineSection]:
    """Prefer bookmarks, then outline-like body headings, typography, and page spans."""
    chunks = list(chunks)
    lines = indexed_blocks(chunks)
    if not lines:
        return []
    rows = list(lines.items())
    markdown_source = chunks[0].doc_name.lower().endswith(".md")
    by_page: dict[int, list[int]] = {}
    for index, ((page, _), _) in enumerate(rows):
        by_page.setdefault(page, []).append(index)
    hints = list(headings)
    bookmarks = [hint for hint in hints if hint.origin in {"bookmark", "style"} and hint.page in by_page]
    strong_roots = sum(hint.level == 1 for hint in bookmarks)
    explicit_chapters = sum(bool(CHAPTER_MARKER.fullmatch(text.strip())) for text in lines.values())
    found: dict[int, tuple[int, str]] = {}
    main = 0
    contents_page = None
    toc_entries = {}
    in_list = False
    fenced = False
    for index, ((page, _), raw) in enumerate(rows):
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.casefold() in CONTENTS:
            contents_page = page
        if contents_page is not None and page <= contents_page + 4:
            entry = TOC_ENTRY.fullmatch(line)
            if entry:
                toc_entries[entry[1].strip()] = int(entry[2])
        if not line or DOT_LEADER.search(line) or len(line.split()) > 18 or has_damaged_text(line):
            continue
        markdown = MARKDOWN_HEADING.fullmatch(line) if markdown_source else None
        if markdown:
            found[index] = (len(markdown[1]), markdown[2])
            in_list = False
            continue
        chapter_marker = CHAPTER_MARKER.fullmatch(line)
        if chapter_marker and index + 1 < len(rows) and rows[index + 1][0][0] == page:
            title = rows[index + 1][1].strip()
            if title and not NUMBERED.fullmatch(title) and not has_damaged_text(title):
                main = int(chapter_marker[1])
                found[index] = (1, f"{main}. {title}")
                in_list = False
                continue
        if APPENDIX.match(line):
            found[index] = (1, line)
            continue
        match = NUMBERED.fullmatch(line)
        if not match or match[2].endswith((".", "…")):
            in_list = bool(LIST_INTRO.search(line) or line.endswith(":"))
            continue
        number = match[1].split(".")
        explicit_chapter = line.casefold().startswith(("chapter ", "chương "))
        if EXERCISE_TITLE.search(match[2]) or (
            not explicit_chapter and len(number) == 1
            and (strong_roots >= 2 or explicit_chapters >= 2 or in_list)
        ):
            continue
        if len(number) == 1 and (explicit_chapter or int(number[0]) == main + 1):
            if contents_page is not None and page <= contents_page:
                continue
            main = int(number[0])
            found[index] = (1, line)
        elif len(number) > 1 and int(number[0]) == main:
            found[index] = (len(number), line)

    for title, target in toc_entries.items():
        numbered = NUMBERED.fullmatch(title)
        for index in by_page.get(target, []):
            body = rows[index][1].strip()
            body_number = NUMBERED.fullmatch(body)
            if numbered and (not body_number or body_number[1] != numbered[1]):
                continue
            if not _title_matches(title, body):
                continue
            level = len(numbered[1].split(".")) if numbered else 1
            found.setdefault(index, (level, title))
            break

    if bookmarks:
        for hint in bookmarks:
            positions = by_page.get(hint.page, [])
            if hint.line is not None:
                position = next((i for i in positions if rows[i][0][1] == hint.line), None)
                if position is not None:
                    found[position] = (hint.level, hint.title)
                continue
            match_index = None
            for i in positions:
                body = rows[i][1].strip()
                label = NUMBERED.fullmatch(body)
                if label and len(label[1].split(".")) == hint.level and _title_matches(hint.title, label[2]):
                    match_index = i
                    break
                if match_index is None and _title_matches(hint.title, body):
                    match_index = i
            if hint.level == 1:
                marker = next((
                    i for i in positions[:5]
                    if CHAPTER_MARKER.fullmatch(rows[i][1].strip())
                    and i + 1 in positions and _title_matches(hint.title, rows[i + 1][1])
                ), None)
                if marker is not None:
                    number = CHAPTER_MARKER.fullmatch(rows[marker][1].strip())[1]
                    found[marker] = (hint.level, f"{number}. {hint.title}")
                    if match_index is not None and match_index != marker:
                        found.pop(match_index, None)
                    continue
            if match_index is None and hint.level == 1 and positions:
                found.setdefault(positions[0], (hint.level, hint.title))
            elif match_index is not None:
                body = rows[match_index][1].strip()
                found[match_index] = (hint.level, body if NUMBERED.fullmatch(body) else hint.title)
    elif not any(level == 1 for level, _ in found.values()):
        for hint in (hint for hint in hints if hint.origin == "font"):
            for index in by_page.get(hint.page, []):
                if _title_matches(hint.title, rows[index][1]):
                    found.setdefault(index, (hint.level, hint.title))
                    break
    fallback = not any(level == 1 for level, _ in found.values())
    if fallback:
        for offset in range(0, max(1, len(by_page) - 1), 2):
            pages = list(by_page)[offset : offset + 3]
            found[by_page[pages[0]][0]] = (1, f"Trang {pages[0]}–{pages[-1]}")
        found = {index: value for index, value in found.items() if value[0] == 1}
    elif min(found) > 0:
        found[0] = (1, "Giới thiệu")
    roots, result = [], []
    boundaries = sorted(found)
    for position, index in enumerate(boundaries):
        level, title = found[index]
        while roots and roots[-1][0] >= level:
            roots.pop()
        end = next(
            (other for other in boundaries[position + 1 :] if found[other][0] <= level),
            len(rows),
        )
        if fallback and end < len(rows):
            end = by_page[rows[end][0][0]][-1] + 1
        # Parent spans include their children; map requests are partitioned separately.
        section_id = f"s{position + 1}"
        kind = (
            "page_range" if fallback else "appendix"
            if APPENDIX.match(title)
            else "subsection"
            if roots
            else "chapter"
        )
        result.append(
            OutlineSection(
                section_id,
                title,
                level,
                rows[index][0][0],
                rows[end - 1][0][0],
                kind,
                _blocks(rows[index:end]),
                roots[-1][1] if roots else None,
            )
        )
        roots.append((level, section_id))
    return result


def map_packets(
    section: OutlineSection, budget: int = 5800
) -> list[tuple[SourceBlock, ...]]:
    """Pack contiguous text and split oversized prose at paragraph boundaries with overlap."""
    packets: list[tuple[SourceBlock, ...]] = []
    current: list[SourceBlock] = []
    size = 0
    for block in section.blocks:
        lines = block.text.splitlines()
        # Never put damaged glyphs or the rest of their paragraph into model context.
        unsafe = {index for index, line in enumerate(lines) if has_damaged_text(line)}
        for index in tuple(unsafe):
            for adjacent in (index - 1, index + 1):
                if 0 <= adjacent < len(lines) and STRUCTURED_LINE.search(lines[adjacent]):
                    unsafe.add(adjacent)
        units: list[SourceBlock] = []
        start = 0
        if len(block.text) > budget or unsafe:
            for index, text in enumerate(lines):
                if index in unsafe:
                    if index > start:
                        units.append(SourceBlock(
                            block.page, block.start_line + start, block.start_line + index - 1,
                            "\n".join(lines[start:index]),
                        ))
                    start = index + 1
                    continue
                if (
                    not text.strip()
                    and index > start
                    and (
                        index + 1 == len(lines)
                        or not STRUCTURED_LINE.search(lines[index + 1])
                    )
                ):
                    units.append(
                        SourceBlock(
                            block.page,
                            block.start_line + start,
                            block.start_line + index - 1,
                            "\n".join(lines[start:index]),
                        )
                    )
                    start = index + 1
        if start < len(lines):
            units.append(
                SourceBlock(
                    block.page,
                    block.start_line + start,
                    block.end_line,
                    "\n".join(lines[start:]),
                )
            )
        for unit in units:
            if current and size + len(unit.text) > budget:
                packets.append(tuple(current))
                current = (
                    current[-1:]
                    if len(current) > 1 and len(current[-1].text) < budget // 4
                    else []
                )
                size = sum(len(part.text) for part in current)
            current.append(unit)
            size += len(unit.text)
    if current:
        packets.append(tuple(current))
    return packets
