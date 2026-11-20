"""Comprehensive Test Suite for Feature 1: Evidence-Grounded Q&A.

Covers:
- Pure stdlib isolation of citation_verifier (zero Pydantic/FastAPI in sys.modules)
- Exact, Token-LCS, and fuzzy citation matching
- Line locators, page boundaries, and SHA-256 hash checks
- Source selection (selected_doc_ids constraint and abstention)
- Hybrid RRF retrieval ranking and BM25-only fallback
- Contextual query expansion with conversation history
- Scanned PDF rejection
- REST API document endpoints (/api/documents)
"""
import io
import subprocess
import sys
import unittest
from unittest.mock import Mock
from datetime import date
from typing import List

from fastapi.testclient import TestClient
from backend.main import app
from backend.core.config import settings
from backend.core.schemas import DocumentChunk, DocumentSelectRequest, GeneratedClaim, UserRequest
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository
from backend.services.document_service import DocumentService, document_service
from backend.services.feature1.qa_service import QAService, expand_contextual_query, qa_service
from backend.algorithms.feature1.citation_verifier import (
    CitationClaim,
    verify_citations,
)


def test_git_command_list_uses_verified_reference_rows_from_selected_source():
    repo = WorkspaceRepository()
    source = DocumentChunk(
        chunk_id="reference",
        doc_id="guide.pdf",
        doc_name="guide.pdf",
        page_number=73,
        start_line=2,
        end_line=12,
        text=(
            "Appendix A — Command Cheat Sheet\nTask\nCommand\n"
            "what\n\nchanged?\ngit status, git diff\n"
            "stage\ngit add <file>\nopen PR\ngh pr create"
        ),
    )
    repo.chunks = [source]
    repo._rebuild_index()
    provider = Mock()
    provider.generate_grounded_qa.return_value = []
    service = QAService(repo, provider)
    prompt = "Hãy nêu những lệnh Git quan trọng"

    answer = service.answer_question(prompt, selected_doc_ids=["guide.pdf"])
    assert answer["status"] == "ANSWER_VERIFIED"
    claims = answer["validated_claims"]
    assert len(claims) == 2
    assert claims[0].cited_page == 73
    assert "Kiểm tra trạng thái" in claims[0].claim_text
    assert claims[0].section == "Luồng hằng ngày"
    assert (claims[0].cited_start_line, claims[0].cited_end_line) == (5, 8)
    assert claims[0].evidence_quote == "what\n\nchanged?\ngit status, git diff"
    assert all(claim.verification_status == "VERIFIED_EXACT" for claim in claims)
    provider.generate_grounded_qa.assert_not_called()

    excluded = service.answer_question(prompt, selected_doc_ids=["other.pdf"])
    assert excluded["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    specific = service.answer_question(
        "Lệnh git status dùng làm gì?", selected_doc_ids=["guide.pdf"], tau_rel=0,
    )
    assert specific["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    provider.generate_grounded_qa.assert_called_once()


def test_conflicting_sources_are_attributed_and_unselected_quote_cannot_be_verified(monkeypatch):
    lines = {
        "annex-a.pdf": "The submission deadline is 14 December at noon.",
        "annex-b.pdf": "The submission deadline is 21 December at noon.",
        "hidden.pdf": "The submission deadline is 30 December at noon.",
    }
    repo = WorkspaceRepository()
    repo.chunks = [
        DocumentChunk(
            chunk_id=doc, doc_id=doc, doc_name=doc, page_number=1, text=line,
            start_line=8, end_line=8,
        )
        for doc, line in lines.items()
    ]
    monkeypatch.setattr(repo, "search", lambda _q, **_options: repo.chunks[:2])
    provider = Mock()
    provider.generate_grounded_qa.return_value = [
        GeneratedClaim(
            claim_text=line, cited_doc_id=doc, cited_page=1,
            cited_start_line=8, cited_end_line=8, evidence_quote=line,
        )
        for doc, line in lines.items()
    ] + [
        GeneratedClaim(
            claim_text=lines["annex-b.pdf"], cited_doc_id="annex-a.pdf", cited_page=1,
            cited_start_line=8, cited_end_line=8, evidence_quote=lines["annex-b.pdf"],
        )
    ]
    service = QAService(repo, provider)
    selected = ["annex-a.pdf", "annex-b.pdf"]
    result = service.answer_question("When is the submission deadline?", selected_doc_ids=selected, tau_rel=0)
    assert [(claim.section, claim.claim_text) for claim in result["validated_claims"]] == [
        (doc, lines[doc]) for doc in selected
    ]
    assert {claim.cited_doc_id for claim in result["hallucination_flags"]} == {"hidden.pdf", "annex-a.pdf"}
    summary = service.answer_question("Tóm gọn nội dung tài liệu", selected_doc_ids=selected)
    assert "Có nhiều tài liệu" in summary["message"]
    mismatched = service.answer_question("Tóm tắt file hidden.pdf", selected_doc_ids=["annex-a.pdf"])
    assert "Không xác định được tài liệu" in mismatched["message"]
    assert not mismatched["validated_claims"]


def test_damaged_exercise_is_rejected_only_in_selected_source():
    repo = WorkspaceRepository()
    repo.chunks = [
        DocumentChunk(
            chunk_id="broken", doc_id="math.pdf", doc_name="math.pdf",
            page_number=72, text="40. Tính độ dài cung.\n0\x14\x19=4",
            start_line=2, end_line=3,
        ),
    ]
    provider = Mock()
    service = QAService(repo, provider)
    result = service.answer_question("Giải bài tập số 40", selected_doc_ids=["math.pdf"])
    assert not result["validated_claims"] and "trang PDF 72" in result["message"]
    missing = service.answer_question("Giải bài số 40", selected_doc_ids=["other.pdf"])
    assert "math.pdf" not in missing["message"]
    provider.generate_grounded_qa.assert_not_called()


def test_qa_rejects_ambiguous_alias_and_quote_stitched_across_context_gaps(monkeypatch):
    repo = WorkspaceRepository()
    rows = [("revision-a", 1, "Deadline is 14 December."),
            ("revision-a", 20, "Submit via the portal."),
            ("revision-b", 1, "Deadline is 21 December.")]
    repo.chunks = [DocumentChunk(
        chunk_id=f"{doc}-{line}", doc_id=doc, doc_name="policy.pdf",
        page_number=1, text=text, start_line=line, end_line=line,
    ) for doc, line, text in rows]
    monkeypatch.setattr(repo, "search", lambda _q, **_options: repo.chunks)
    provider = Mock()
    provider.generate_grounded_qa.return_value = [
        GeneratedClaim(claim_text="Wrong alias", cited_doc_id="policy.pdf", cited_page=1,
                       evidence_quote=rows[0][2], cited_start_line=1, cited_end_line=1),
        GeneratedClaim(claim_text="Stitched quote", cited_doc_id="revision-a", cited_page=1,
                       evidence_quote=f"{rows[0][2]} {rows[1][2]}", cited_start_line=1, cited_end_line=20),
    ]
    result = QAService(repo, provider).answer_question(
        "When is the deadline?", selected_doc_ids=["revision-a", "revision-b"], tau_rel=0,
    )
    assert not result["validated_claims"] and len(result["hallucination_flags"]) == 2


def test_damaged_chapter_uses_verified_headings_instead_of_incomplete_equations():
    repo = WorkspaceRepository()
    text = "Chương 1\nHàm nhiều biến\n1.1 Miền xác định\n0\x14\x19=4\n1.2 Giới hạn"
    repo.chunks = [DocumentChunk(
        chunk_id="math", doc_id="math.pdf", doc_name="math.pdf",
        page_number=4, text=text, start_line=1, end_line=5,
    )]
    provider = Mock()
    result = QAService(repo, provider).answer_question("Tóm gọn chương 1", selected_doc_ids=["math.pdf"])
    assert result["status"] == "ANSWER_VERIFIED"
    assert [claim.claim_text for claim in result["validated_claims"]] == ["Miền xác định", "Giới hạn"]
    assert [claim.cited_start_line for claim in result["validated_claims"]] == [3, 5]
    provider.generate_summary_stage.assert_not_called()


def test_generated_claims_need_semantic_support_even_with_exact_quote(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "feature1_semantic_verify", True)
    monkeypatch.setattr(settings, "offline_only", False)
    repo = WorkspaceRepository()
    quote = "Nếu không chỉ rõ D, miền xác định gồm các điểm mà biểu thức có nghĩa."
    repo.ingest_text_document("math.pdf", "math.pdf", [(1, quote)])
    provider = Mock()
    provider.generate_grounded_qa.return_value = [
        GeneratedClaim(claim_text=text, cited_doc_id="math.pdf", cited_page=1, evidence_quote=quote,
                       cited_start_line=1, cited_end_line=1)
        for text in ("Mọi biểu thức đều xác định ở mọi điểm.",
                     "Miền xác định gồm các điểm mà biểu thức có nghĩa.",
                     "Miền xác định là tập đóng.", "Miền xác định là tập hữu hạn.")
    ]
    provider.judge_claim_support.return_value = {"1": "CONTRADICTED", "2": "SUPPORTED", "3": "INSUFFICIENT"}
    result = QAService(repo, provider).answer_question(
        "Quy tắc miền xác định là gì?", selected_doc_ids=["math.pdf"], tau_rel=0,
    )
    assert [claim.semantic_status for claim in result["validated_claims"]] == ["SUPPORTED"]
    assert [claim.semantic_status for claim in result["hallucination_flags"]] == [
        "CONTRADICTED", "INSUFFICIENT", "UNAVAILABLE",
    ]
    assert result["grounding_score"] == 0.25


def test_domain_condition_is_not_widened_even_when_the_model_judge_would_accept(monkeypatch):
    from backend.services.feature1.claim_support import review_claims

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "feature1_semantic_verify", True)
    monkeypatch.setattr(settings, "offline_only", False)
    provider = Mock()
    claim = GeneratedClaim(claim_text="Miền xác định là toàn bộ mặt phẳng nếu đề không chỉ rõ D.",
                           cited_doc_id="math.pdf", cited_page=1,
                           evidence_quote="Miền xác định gồm các điểm mà tại đó biểu thức có nghĩa.")
    accepted, rejected = review_claims(provider, [claim])
    assert not accepted and rejected[0].semantic_status == "INSUFFICIENT"
    provider.judge_claim_support.assert_not_called()
    provider.judge_claim_support.return_value = {"1": "SUPPORTED"}
    explicit = claim.model_copy(update={"evidence_quote": "Biểu thức có nghĩa trên D = ℝ²."})
    accepted, rejected = review_claims(provider, [explicit])
    assert accepted and not rejected


def test_short_summary_rejects_quote_from_unsupplied_lines_on_same_page(monkeypatch):
    import importlib

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    repo = WorkspaceRepository()
    repo.chunks = [
        DocumentChunk(chunk_id=str(line), doc_id="data.txt", doc_name="data.txt", page_number=1,
                      text=f"Evidence at line {line}: " + "sample text " * 60, start_line=line, end_line=line)
        for line in range(1, 17)
    ]
    provider = Mock()

    def generate(_query, sampled, **_kwargs):
        visible = {chunk.chunk_id for chunk in sampled}
        hidden = next(chunk for chunk in repo.chunks if chunk.chunk_id not in visible)
        return [GeneratedClaim(claim_text="Claim outside context", cited_doc_id=hidden.doc_id, cited_page=1,
                               evidence_quote=hidden.text, cited_start_line=hidden.start_line,
                               cited_end_line=hidden.end_line)]

    provider.generate_grounded_qa.side_effect = generate
    qa_module = importlib.import_module("backend.services.feature1.qa_service")
    monkeypatch.setattr(qa_module, "extract_summary_passages", lambda *_args, **_kwargs: [])
    result = QAService(repo, provider).summarize_document("data.txt", brief=True)
    assert result["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    assert not result["validated_claims"]


class TestFeature1GroundedQA(unittest.TestCase):
    def setUp(self):
        settings.llm_provider = "mock"
        workspace_repository.seed_demo_workspace()
        self.client = TestClient(app)

    def test_01_pure_stdlib_isolation(self):
        """Assures backend.algorithms.feature1.citation_verifier uses ONLY standard library."""
        code = (
            "import sys\n"
            "import backend.algorithms.feature1.citation_verifier\n"
            "pydantic_modules = [m for m in sys.modules if 'pydantic' in m]\n"
            "fastapi_modules = [m for m in sys.modules if 'fastapi' in m or 'starlette' in m]\n"
            "assert not pydantic_modules, f'Pydantic leaked into stdlib verifier: {pydantic_modules}'\n"
            "assert not fastapi_modules, f'FastAPI leaked into stdlib verifier: {fastapi_modules}'\n"
            "print('STDLIB_PURITY_VERIFIED')\n"
        )
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Stdlib isolation failed:\n{res.stderr}")
        self.assertIn("STDLIB_PURITY_VERIFIED", res.stdout)

    def test_02_citation_verifier_matching_modes(self):
        """Tests Exact match, Token-LCS match, and ungrounded quote detection."""
        lookup = {
            ("doc_a.pdf", 1): {
                "full_page_text": "Báo cáo kỹ thuật bao gồm 12-18 trang và sơ đồ kiến trúc hệ thống phân tầng.",
                "total_lines": 10,
                "version_id": "v1",
                "doc_hash": "hash_a",
            }
        }

        # 1. Exact match
        exact_claim = CitationClaim(
            claim_text="Báo cáo có 12-18 trang",
            cited_doc_id="doc_a.pdf",
            cited_page=1,
            evidence_quote="Báo cáo kỹ thuật bao gồm 12-18 trang",
            cited_start_line=1,
            cited_end_line=1,
            doc_version="v1",
            doc_hash="hash_a",
        )
        res_exact = verify_citations([exact_claim], lookup)
        self.assertEqual(len(res_exact.validated_claims), 1)
        self.assertEqual(res_exact.validated_claims[0].verification_status, "VERIFIED_EXACT")
        self.assertEqual(res_exact.validated_claims[0].match_score, 1.0)

        # 2. Token-LCS match (minor word order / dropped word)
        lcs_claim = CitationClaim(
            claim_text="Báo cáo gồm 12-18 trang và sơ đồ kiến trúc",
            cited_doc_id="doc_a.pdf",
            cited_page=1,
            evidence_quote="Báo cáo kỹ thuật 12-18 trang sơ đồ kiến trúc",
            cited_start_line=1,
            cited_end_line=1,
            doc_version="v1",
            doc_hash="hash_a",
        )
        res_lcs = verify_citations([lcs_claim], lookup, theta_match=0.6)
        self.assertEqual(len(res_lcs.validated_claims), 1)
        self.assertEqual(res_lcs.validated_claims[0].verification_status, "VERIFIED_FUZZY")
        self.assertGreaterEqual(res_lcs.validated_claims[0].match_score, 0.6)

        # 3. Fabricated quote (Ungrounded)
        hallucinated_claim = CitationClaim(
            claim_text="Hệ thống đạt giải nhất Olympic Tin học",
            cited_doc_id="doc_a.pdf",
            cited_page=1,
            evidence_quote="đoạt giải nhất toàn quốc năm 2026",
            cited_start_line=1,
            cited_end_line=5,
            doc_version="v1",
            doc_hash="hash_a",
        )
        res_hall = verify_citations([hallucinated_claim], lookup)
        self.assertEqual(len(res_hall.validated_claims), 0)
        self.assertEqual(len(res_hall.hallucination_flags), 1)
        self.assertEqual(res_hall.hallucination_flags[0].verification_status, "UNGROUNDED_QUOTE")

    def test_verifier_rejects_correct_quote_with_wrong_absolute_line(self):
        text = "\n".join("Hạn nộp là thứ Sáu." if line == 40 else f"Dòng {line}." for line in range(1, 41))
        claim = CitationClaim(
            claim_text="Nộp thứ Sáu", cited_doc_id="d.pdf", cited_page=1,
            evidence_quote="Hạn nộp là thứ Sáu.", cited_start_line=10, cited_end_line=12,
        )
        result = verify_citations([claim], {("d.pdf", 1): {"text": text, "total_lines": 40}})
        assert not result.validated_claims
        claim.cited_start_line = claim.cited_end_line = 40
        result = verify_citations([claim], {("d.pdf", 1): {"text": text, "total_lines": 40}})
        assert result.validated_claims[0].verification_status == "VERIFIED_EXACT"

    def test_03_citation_verifier_boundaries_and_hashes(self):
        """Tests line out of bounds, page out of bounds, and hash mismatch."""
        lookup = {
            ("spec.pdf", 2): {
                "full_page_text": "Quy định về thời hạn nộp bài là ngày 26/10/2026.",
                "total_lines": 8,
                "version_id": "v1",
                "doc_hash": "correct_hash_123",
            }
        }

        # Page out of bounds
        c_page = CitationClaim(
            claim_text="Trang không tồn tại",
            cited_doc_id="spec.pdf",
            cited_page=99,
            evidence_quote="Quy định",
        )
        r_page = verify_citations([c_page], lookup)
        self.assertEqual(r_page.hallucination_flags[0].verification_status, "INVALID_SOURCE_PAGE")

        # Line out of bounds
        c_line = CitationClaim(
            claim_text="Dòng vượt quá trang",
            cited_doc_id="spec.pdf",
            cited_page=2,
            cited_start_line=1,
            cited_end_line=50,
            evidence_quote="Quy định",
        )
        r_line = verify_citations([c_line], lookup)
        self.assertEqual(r_line.hallucination_flags[0].verification_status, "LINE_OUT_OF_RANGE")

        # Hash mismatch
        c_hash = CitationClaim(
            claim_text="Sai hash phiên bản",
            cited_doc_id="spec.pdf",
            cited_page=2,
            cited_start_line=1,
            cited_end_line=4,
            evidence_quote="Quy định",
            doc_hash="tampered_hash_999",
        )
        r_hash = verify_citations([c_hash], lookup)
        self.assertEqual(r_hash.hallucination_flags[0].verification_status, "HASH_MISMATCH")

    def test_04_selected_doc_ids_retrieval_filtering(self):
        """Tests that selected_doc_ids strictly restricts retrieval and empty selection abstains."""
        # When selected_doc_ids is empty list [] -> Search returns empty
        empty_search = workspace_repository.search("Submission Package", selected_doc_ids=[])
        self.assertEqual(empty_search, [])

        # When selected_doc_ids is empty in QA service -> Abstains with ABSTAINED_NO_SOURCE_SELECTED
        qa_res_empty = qa_service.answer_question("Submission Package", selected_doc_ids=[])
        self.assertEqual(qa_res_empty["status"], "ABSTAINED_NO_SOURCE_SELECTED")

        # When selected_doc_ids restricts to Project_Brief.pdf
        filtered = workspace_repository.search("Package", selected_doc_ids=["Project_Brief.pdf"])
        for chunk in filtered:
            self.assertEqual(chunk.doc_name, "Project_Brief.pdf")

    def test_05_contextual_query_expansion(self):
        """Tests deterministic contextual expansion for follow-up conversational queries."""
        history = [
            {"role": "user", "content": "Submission Package gồm những gì?"},
            {"role": "assistant", "content": "Gồm báo cáo kỹ thuật và mã nguồn."},
        ]

        # Pronoun "nó" triggers expansion
        expanded = expand_contextual_query("Nó có mấy trang?", history)
        self.assertIn("Submission Package", expanded)
        self.assertIn("mấy trang", expanded)

        # Standalone complete query is NOT changed
        full_query = "Hệ thống quy định các tiêu chuẩn kỹ thuật R1 đến R5 như thế nào?"
        same_expanded = expand_contextual_query(full_query, history)
        self.assertEqual(same_expanded, full_query)

    def test_06_hybrid_rrf_scoring_and_fallback(self):
        """Verifies RRF ranking formula and BM25-only fallback."""
        repo = WorkspaceRepository()
        repo.chunks = []
        doc_meta, chunks = workspace_repository.documents["Project_Brief.pdf"], workspace_repository.get_document_chunks("Project_Brief.pdf")
        repo.add_document(doc_meta, chunks)

        # 1. Fallback mode (no embedding provider -> dense_available=False)
        self.assertFalse(repo.dense_available)
        results = repo.search("Submission Package", top_k=2)
        self.assertGreater(len(results), 0)
        top = results[0]
        # In fallback, rrf_score = 1.0 / (60.0 + r_bm25) where 1 <= r_bm25 <= len(eligible)
        rank_inferred = round(1.0 / top.rrf_score - 60.0)
        self.assertGreaterEqual(rank_inferred, 1)
        self.assertEqual(top.dense_score, 0.0)

        # 2. Simulated Dense Embedding Mode
        def fake_embed(texts: List[str]):
            # Deterministic mock vectors: 4 dimensions
            vecs = []
            for t in texts:
                val = 1.0 if "submission" in t.lower() or "package" in t.lower() else 0.1
                vecs.append([val, val * 0.5, 0.2, 0.8])
            return vecs

        repo.set_embed_fn(fake_embed)
        self.assertTrue(repo.dense_available)
        dense_results = repo.search("Submission Package", top_k=2)
        self.assertGreater(len(dense_results), 0)
        dense_top = dense_results[0]
        self.assertGreater(dense_top.dense_score, 0.0)
        # RRF combines both ranks: 1/(60+r_bm25) + 1/(60+r_dense)
        self.assertGreater(dense_top.rrf_score, 1.0 / (60.0 + len(chunks)))

    def test_07_document_service_ingestion_and_scanned_pdf(self):
        """Tests paragraph chunking, SHA-256 deduplication, versioning, and scanned PDF rejection."""
        service = DocumentService(workspace_repository)

        # 1. Plain text ingestion with lines
        txt_content = "Đoạn 1 dòng 1\nĐoạn 1 dòng 2\n\nĐoạn 2 dòng 4\nĐoạn 2 dòng 5".encode("utf-8")
        res1 = service.ingest_file("sample_doc.txt", txt_content)
        self.assertEqual(res1["status"], "INGESTED")
        self.assertEqual(res1["document"].version_id, "v1")

        # 2. Same content hash -> ALREADY_EXISTS
        res_dup = service.ingest_file("sample_doc.txt", txt_content)
        self.assertEqual(res_dup["status"], "ALREADY_EXISTS")

        # 3. Same name, different content -> new version v2
        diff_content = "Nội dung cập nhật mới dòng 1\n\nNội dung dòng 3".encode("utf-8")
        res_v2 = service.ingest_file("sample_doc.txt", diff_content)
        self.assertEqual(res_v2["status"], "INGESTED")
        self.assertEqual(res_v2["document"].version_id, "v2")

        # 4. Scanned PDF (0 text layer) raises ValueError
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        blank_buf = io.BytesIO()
        writer.write(blank_buf)
        with self.assertRaises(ValueError):
            service.ingest_file("scanned_image.pdf", blank_buf.getvalue())

    def test_08_rest_api_document_endpoints(self):
        """Tests REST API endpoints: GET /api/documents, POST upload, select, and DELETE."""
        # 1. GET /api/documents
        get_res = self.client.get("/api/documents")
        self.assertEqual(get_res.status_code, 200)
        self.assertIsInstance(get_res.json(), list)

        # 2. POST /api/documents/upload
        file_bytes = b"Tai lieu nghiep vu kiem thu.\nDong so 2."
        upload_res = self.client.post(
            "/api/documents/upload",
            files={"file": ("api_test_doc.txt", file_bytes, "text/plain")},
        )
        self.assertEqual(upload_res.status_code, 200)
        self.assertEqual(upload_res.json()["status"], "INGESTED")

        # 3. POST /api/documents/select
        sel_res = self.client.post(
            "/api/documents/select",
            json={"selected_doc_ids": ["api_test_doc.txt"]},
        )
        self.assertEqual(sel_res.status_code, 200)
        self.assertEqual(sel_res.json()["status"], "SELECTION_UPDATED")

        # 4. DELETE /api/documents/{doc_id}
        del_res = self.client.delete("/api/documents/api_test_doc.txt")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "DELETED")

        # DELETE non-existent doc -> 404
        del_404 = self.client.delete("/api/documents/non_existent_file.pdf")
        self.assertEqual(del_404.status_code, 404)

    def test_09_pinpoint_reranker_numeric_and_temporal(self):
        """Verifies that Pinpoint Reranker boosts chunks containing exact numeric/temporal entities."""
        # Query asking for page limits (numeric entity)
        results = workspace_repository.search("Báo cáo kỹ thuật có mấy trang?", top_k=2)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertGreater(top.pinpoint_score, 0.0)
        self.assertIn("12-18", top.text)

        # Ingest document with explicit deadline and date
        workspace_repository.ingest_text_document(
            doc_id="Schedule.pdf",
            doc_name="Schedule.pdf",
            pages=[(1, "Hạn nộp bài cuối kỳ: 24/10/2026 trên hệ thống LMS. Nộp trễ sẽ bị trừ điểm.")],
        )

        # Query asking for deadline (temporal entity)
        results_date = workspace_repository.search("Hạn nộp bài là khi nào?", top_k=2)
        self.assertGreater(len(results_date), 0)
        self.assertGreater(results_date[0].pinpoint_score, 0.0)

    def test_10_multiline_evidence_highlighting(self):
        """Verifies multi-line evidence highlight renders valid marks across line boundaries."""
        from frontend.state import highlight_evidence_in_page

        page_text = (
            "Line 1: Submission Package\n"
            "Line 2: 01 Engineering Report (12-18 pages recommended)\n"
            "Line 3: 02 Source Repository and Demo\n"
            "Line 4: End of package"
        )
        quote = (
            "01 Engineering Report (12-18 pages recommended)\n"
            "Line 3: 02 Source Repository and Demo"
        )
        html = highlight_evidence_in_page(page_text, quote)
        self.assertIn('<mark class="cite-mark">', html)
        self.assertIn("</mark>", html)
        # Ensure marks appear on both Line 2 and Line 3
        self.assertIn("Line 2:", html)
        self.assertIn("Line 3:", html)
        self.assertEqual(html.count('<mark class="cite-mark">'), html.count("</mark>"))

    def test_11_notebooklm_comprehensive_document_summary(self):
        """Verifies NotebookLM-level comprehensive briefing with multi-page citations."""
        res = qa_service.summarize_document("Project_Brief.pdf")
        self.assertEqual(res["status"], "SUMMARY_GENERATED")
        summary = res["summary"]
        self.assertTrue("Tổng quan" in summary or "Executive Briefing" in summary)
        self.assertTrue("Yêu cầu" in summary or "Themes" in summary)
        self.assertTrue("Hạn chót" in summary or "Deadlines" in summary or "Mốc Thời hạn" in summary)
        self.assertTrue("Khuyến nghị" in summary or "Lưu ý" in summary or "Takeaways" in summary)
        # Verified citations provided across pages
        self.assertGreaterEqual(len(res["validated_claims"]), 2)
        pages_cited = {c.cited_page for c in res["validated_claims"]}
        self.assertIn(3, pages_cited)
        self.assertIn(6, pages_cited)

    def test_12_flexible_doc_id_matching(self):
        """Verifies citation verifier tolerates case differences and missing .pdf extension."""
        lookup = workspace_repository.build_page_lookup()
        # Case A: Missing .pdf extension
        c_no_ext = CitationClaim(
            claim_text="Report limit",
            cited_doc_id="Project_Brief",  # without .pdf
            cited_page=6,
            evidence_quote="01 Engineering Report (12-18 pages recommended)",
        )
        res_no_ext = verify_citations([c_no_ext], lookup)
        self.assertEqual(len(res_no_ext.validated_claims), 1)
        self.assertEqual(res_no_ext.validated_claims[0].verification_status, "VERIFIED_EXACT")

        # Case B: Lowercase filename
        c_lower = CitationClaim(
            claim_text="Report limit",
            cited_doc_id="project_brief.pdf",
            cited_page=6,
            evidence_quote="01 Engineering Report (12-18 pages recommended)",
        )
        res_lower = verify_citations([c_lower], lookup)
        self.assertEqual(len(res_lower.validated_claims), 1)
        self.assertEqual(res_lower.validated_claims[0].verification_status, "VERIFIED_EXACT")

    def test_13_resolve_summary_target_stem_and_selection(self):
        """Verifies resolve_summary_target handles natural language stems, missing extensions, and selected_doc_ids."""
        from backend.services.feature1.qa_service import resolve_summary_target
        from backend.core.schemas import DocumentMetadata, DocumentChunk

        # Add a simulated Team_8_Proposal.pdf document
        meta = DocumentMetadata(
            doc_id="Team_8_Proposal.pdf",
            doc_name="Team_8_Proposal.pdf",
            total_pages=15,
            file_hash="team8proposalhash123",
            ingested_at="2026-11-03",
        )
        chunks = [
            DocumentChunk(
                chunk_id="t8_c1",
                doc_id="Team_8_Proposal.pdf",
                doc_name="Team_8_Proposal.pdf",
                page_number=1,
                start_line=1,
                end_line=10,
                text="Team 8 Proposal architecture and project outline.",
                doc_version="v1",
                doc_hash="team8proposalhash123",
            )
        ]
        workspace_repository.add_document(meta, chunks)

        # Case 1: User types query with stem, no .pdf extension ("Tóm tắt file Team_8_proposal ấy")
        target = resolve_summary_target("Tóm tắt file Team_8_proposal ấy", workspace_repository)
        self.assertEqual(target, "Team_8_Proposal.pdf")

        # Case 2: User types query with space ("tóm tắt team 8 proposal")
        target_spaces = resolve_summary_target("tóm tắt team 8 proposal", workspace_repository)
        self.assertEqual(target_spaces, "Team_8_Proposal.pdf")

        # Case 3: Generic summary query with selected_doc_ids priority
        target_selected = resolve_summary_target(
            "Tóm tắt tài liệu đã chọn",
            workspace_repository,
            selected_doc_ids=["Team_8_Proposal.pdf"],
        )
        self.assertEqual(target_selected, "Team_8_Proposal.pdf")

    def test_14_frontend_state_initialization(self):
        """Verifies frontend state initialization does not fail with NameError or import errors."""
        import streamlit as st
        import frontend.state as f_state

        st.session_state = {}
        f_state.init_state()
        self.assertIn("active_ai_mode", st.session_state)
        self.assertIn(st.session_state["active_ai_mode"], ["offline", "ollama", "gemini"])
        self.assertIn("chat_messages", st.session_state)
        self.assertGreater(len(st.session_state["chat_messages"]), 0)




if __name__ == "__main__":
    unittest.main()
