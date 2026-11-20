# Copyright (c) SurfSense
# SPDX-License-Identifier: Apache-2.0
# Adapted from surfsense_local/backend/modules/chat/prompt.py at
# https://github.com/MODSetter/SurfSense/blob/b764f2838969974fd1b0e8c386326039a0f3ad3a/surfsense_local/backend/modules/chat/prompt.py
# WorkspaceAI uses JSON source IDs and derives page and line coordinates locally.
# See SURFSENSE_LICENSE.txt.

import re
from collections.abc import Sequence

from backend.core.schemas import DocumentChunk, GeneratedClaim

_TAGS = re.compile(
    r"</?(?:source|context|document|retrieved_context|untrusted_document_data)\b[^>\r\n]*>",
    re.IGNORECASE,
)


def number_passages(chunks: Sequence[DocumentChunk]) -> dict[int, DocumentChunk]:
    """Create the catalog of excerpts the model may cite for one turn."""
    return dict(enumerate(chunks, start=1))


def label_passage(source_id: int, content: str) -> str:
    """Prevent a source from closing a context tag or introducing its own."""
    return f"[{source_id}] {_TAGS.sub('', content)}"


def resolve_citation(
    source_id: object, claim: str, excerpt: str, passages: dict[int, DocumentChunk],
) -> GeneratedClaim | None:
    """Resolve one SurfSense source label and locate the quote inside its passage."""
    if type(source_id) is not int or source_id not in passages:
        return None
    chunk = passages[source_id]
    pattern = r"\s+".join(re.escape(word) for word in excerpt.split())
    if not pattern:
        return None
    match = re.search(pattern, chunk.text, re.IGNORECASE)
    if match is None:
        return None

    start_line = chunk.start_line + chunk.text.count("\n", 0, match.start())
    end_line = start_line + match.group().count("\n")
    if end_line > chunk.end_line:
        return None
    return GeneratedClaim(
        claim_text=claim.strip(),
        cited_doc_id=chunk.doc_id,
        cited_page=chunk.page_number,
        cited_start_line=start_line,
        cited_end_line=end_line,
        evidence_quote=match.group(),
        doc_version=chunk.doc_version,
        doc_hash=chunk.doc_hash,
    )
