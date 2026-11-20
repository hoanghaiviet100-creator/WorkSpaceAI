"""Evaluate a Git/GitHub tutorial summary with a cold and a warm cache."""

import argparse
import json
import logging
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.core.config import settings
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.feature1.qa_service import QAService


EXPECTED = [str(chapter) for chapter in range(1, 23)] + ["A", "B", "C", "D"]
QUESTION = "Hãy nêu chi tiết những gì có trên file"


def chapter_key(title: str) -> str | None:
    match = re.match(r"^(?:chapter\s+|chương\s+)?(\d+)[.:)]?", title, re.I)
    if match:
        return match[1]
    appendix = re.match(r"^(?:appendix|phụ lục)\s+([A-D])\b", title, re.I)
    return appendix[1].upper() if appendix else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--model", help="Local Ollama model name")
    parser.add_argument(
        "--review",
        type=Path,
        help="Manual JSON review with missing, incorrect, supported_claims, reviewed_claims",
    )
    parser.add_argument(
        "--report", type=Path, help="Write chapter notes and evidence for manual review"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings.llm_provider = "ollama"
    settings.offline_only = False
    if args.model:
        settings.ollama_model = args.model

    repo = WorkspaceRepository()
    document = DocumentService(repo).ingest_file(args.pdf.name, args.pdf.read_bytes())[
        "document"
    ]
    service = QAService(repo)
    with TemporaryDirectory(prefix="feature1-eval-") as directory:
        service.summary_cache_dir = Path(directory)
        started = perf_counter()
        cold = service.answer_question(QUESTION, selected_doc_ids=[document.doc_id])
        cold_seconds = perf_counter() - started
        started = perf_counter()
        warm = service.answer_question(QUESTION, selected_doc_ids=[document.doc_id])
        warm_seconds = perf_counter() - started
        cached, cached_seconds = warm, warm_seconds
        if not warm.get("summary_cache_hit") and not warm.get("coverage", {}).get(
            "missing_sections"
        ):
            started = perf_counter()
            cached = service.answer_question(
                QUESTION, selected_doc_ids=[document.doc_id]
            )
            cached_seconds = perf_counter() - started

    assessed = max(
        (cold, warm, cached),
        key=lambda result: result.get("coverage", {}).get("explained_sections", 0),
    )
    coverage = assessed.get("coverage", {})
    explained = {chapter_key(title) for title in coverage.get("explained_titles", [])}
    missing = [key for key in EXPECTED if key not in explained]
    claims = assessed.get("validated_claims", [])
    source_count = sum(
        claim.verification_status.startswith("VERIFIED_") for claim in claims
    )
    print(
        f"1. Coverage: {len(EXPECTED) - len(missing)}/{len(EXPECTED)}; missing: {', '.join(missing) or 'none'}"
    )
    if args.review:
        review = json.loads(args.review.read_text(encoding="utf-8"))
        print(
            f"2. Important details: {len(review['missing'])} missing, {len(review['incorrect'])} incorrect"
        )
        reviewed = review["reviewed_claims"]
        supported = review["supported_claims"]
        if (
            type(reviewed) is not int
            or type(supported) is not int
            or not 0 <= supported <= reviewed <= len(claims)
        ):
            parser.error(
                "reviewed_claims and supported_claims must be valid counts for this report"
            )
        print(f"3. Semantic source support (manual): {supported}/{reviewed}")
    else:
        print("2. Important details: manual review pending (use --review)")
        print("3. Semantic source support: manual review pending (use --review)")
    print(f"   Source quotations verified automatically: {source_count}/{len(claims)}")
    print(
        f"4. Response time: cold {cold_seconds:.2f}s; repeat {warm_seconds:.2f}s; "
        f"cached {cached_seconds:.2f}s; cache hit: {cached.get('summary_cache_hit', False)}"
    )
    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "expected": EXPECTED,
                    "coverage": coverage,
                    "cold_coverage": cold.get("coverage"),
                    "repeat_coverage": warm.get("coverage"),
                    "seconds": {
                        "cold": cold_seconds,
                        "repeat": warm_seconds,
                        "cached": cached_seconds,
                    },
                    "cache_hit": cached.get("summary_cache_hit", False),
                    "claims": [claim.model_dump(mode="json") for claim in claims],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
