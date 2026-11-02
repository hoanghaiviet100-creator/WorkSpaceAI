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
from datetime import date
from typing import List

from fastapi.testclient import TestClient
from backend.main import app
from backend.core.config import settings
from backend.core.schemas import DocumentSelectRequest, UserRequest
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository
from backend.services.document_service import DocumentService, document_service
from backend.services.qa_service import QAService, expand_contextual_query, qa_service
from backend.algorithms.citation_verifier import (
    CitationClaim,
    verify_citations,
)


class TestFeature1GroundedQA(unittest.TestCase):
    def setUp(self):
        settings.llm_provider = "mock"
        workspace_repository.seed_demo_workspace()
        self.client = TestClient(app)

    def test_01_pure_stdlib_isolation(self):
        """Assures backend.algorithms.citation_verifier uses ONLY standard library."""
        code = (
            "import sys\n"
            "import backend.algorithms.citation_verifier\n"
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
            cited_end_line=5,
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
            cited_end_line=5,
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


if __name__ == "__main__":
    unittest.main()
