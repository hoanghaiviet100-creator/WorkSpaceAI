import json
from uuid import uuid4
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.schemas import DocumentChunk, GeneratedClaim
from backend.main import app
from backend.providers.llm_provider import llm_provider, GeminiRequestError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services import runtime_service
from backend.services.feature1.qa_service import QAService

KEY = "synthetic-gemini-key-never-sent-6194"
MODEL = "gemini-3.5-flash-lite"
QUOTE = "The report deadline is November 20, 2026."


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", KEY)
    monkeypatch.setattr(settings, "gemini_model", MODEL)
    monkeypatch.setattr(settings, "dense_tau_rel", 0.0)
    monkeypatch.setattr(settings, "bm25_tau_rel", 0.0)
    monkeypatch.setattr(runtime_service, "ENV_PATH", tmp_path / ".env")


@pytest.fixture
def workspace():
    client = TestClient(app)
    headers = {"X-Workspace-ID": str(uuid4())}
    for name, text in (("alpha.txt", QUOTE), ("beta.txt", "Confidential excluded content BETA-6194.")):
        response = client.post("/api/documents/upload", headers=headers, files={"file": (name, text.encode(), "text/plain")})
        assert response.status_code == 200
    return client, headers


def response_text(text):
    return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]})


def grounded_output(extra=None):
    claims = [{"claim": "The deadline is November 20.", "doc_id": "alpha.txt", "page": 1, "line_start": 1, "line_end": 1, "excerpt": QUOTE}]
    if extra:
        claims.append(extra)
    return response_text(json.dumps({"answer": "The deadline is November 20.", "citations": claims}))


def test_gemini_is_called_once_with_only_selected_document_evidence(workspace):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=grounded_output()) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert result.status_code == 200
    assert result.json()["status"] == "ANSWER_VERIFIED"
    assert all(c["cited_doc_id"] == "alpha.txt" for c in result.json()["validated_claims"])
    assert post.call_count == 1
    assert post.call_args.args[0].endswith(f"/{MODEL}:generateContent")
    assert KEY not in post.call_args.args[0]
    payload = json.dumps(post.call_args.kwargs["json"])
    assert QUOTE in payload
    assert "BETA-6194" not in payload
    assert "<untrusted_document_data>" in payload
    assert post.call_args.kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_quiz_explanation_uses_question_and_quiz_sources_instead_of_email_or_summary(workspace):
    client, headers = workspace
    query = "Trong quiz, email tóm tắt có nhắc hạn nộp là November 20. Hãy giải thích đáp án."
    with patch.object(httpx, "post", return_value=grounded_output()) as post:
        response = client.post("/api/chat", headers=headers, json={
            "query": query,
            "selected_doc_ids": ["alpha.txt"],
            "quiz_explanation": True,
            "conversation_history": [{"role": "user", "content": "Other-topic-5417"}],
        })
    assert response.status_code == 200
    assert response.json()["status"] == "ANSWER_VERIFIED"
    post.assert_called_once()
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert query in prompt and QUOTE in prompt
    assert "Other-topic-5417" not in prompt and "BETA-6194" not in prompt


def test_summary_verifies_generated_citations_instead_of_marking_everything_verified(workspace):
    client, headers = workspace
    unsupported = {"claim": "Invented deadline", "doc_id": "alpha.txt", "page": 1, "line_start": 1, "line_end": 1, "excerpt": "The deadline is December 31, 2030 and cannot be changed."}
    with patch.object(httpx, "post", return_value=grounded_output(unsupported)) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "Summarize alpha.txt", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    body = result.json()
    assert body["status"] == "SUMMARY_GENERATED"
    assert len(body["validated_claims"]) == 1
    assert len(body["hallucination_flags"]) == 1
    assert "Invented deadline" not in body["summary"]
    assert body["grounding_score"] < 1.0


@pytest.mark.parametrize("detailed", [False, True])
def test_report_summary_and_followup_include_middle_and_end(workspace, detailed):
    client, headers = workspace
    original_question = "Bạn hãy tóm tắt giúp tôi những gì được nêu trên file"
    report = "\n".join([QUOTE] + [
        f"Report section {i:03}: " + "The project architecture and evaluation are documented here. " * 5
        for i in range(1, 61)
    ])
    upload = client.post("/api/documents/upload", headers=headers, files={"file": ("alpha.txt", report.encode(), "text/plain")})
    assert upload.status_code == 200
    doc_id = upload.json()["document"]["doc_id"]
    output = json.loads(grounded_output().json()["candidates"][0]["content"]["parts"][0]["text"])
    output["citations"][0].update(doc_id=doc_id, section="Project schedule")
    with patch.object(httpx, "post", return_value=response_text(json.dumps(output))) as post:
        result = client.post("/api/chat", headers=headers, json={
            "query": "Hãy mô tả chi tiết giúp tôi" if detailed else original_question,
            "selected_doc_ids": [doc_id],
            "conversation_history": [{"role": "user", "content": original_question}] if detailed else [],
        })
    assert result.json()["status"] == "SUMMARY_GENERATED"
    assert result.json()["summary_scope"] == "all_indexed_passages"
    assert result.json()["validated_claims"][0]["section"] == "Project schedule"
    post.assert_called_once()
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "Report section 030" in prompt and "Report section 060" in prompt
    assert "BETA-6194" not in prompt
    assert ("Hãy mô tả chi tiết các phần chính." in prompt) == detailed


@pytest.mark.parametrize("supplement_fails", [False, True])
def test_long_summary_fills_uncovered_pages_and_preserves_verified_output(supplement_fails):
    repo = WorkspaceRepository()
    repo.chunks = [DocumentChunk(
        chunk_id=f"page-{page}", doc_id="report.pdf", doc_name="report.pdf",
        page_number=page, start_line=1, end_line=1,
        text=f"Section {page} documents a separate milestone in the fictional project.",
    ) for page in range(1, 11)]
    first = GeneratedClaim(
        claim_text="The first milestone defines project scope.", section="Scope",
        cited_doc_id="report.pdf", cited_page=1, evidence_quote=repo.chunks[0].text,
    )
    last = first.model_copy(update={
        "claim_text": "The final milestone documents risk review.", "section": "Risks",
        "cited_page": 10, "evidence_quote": repo.chunks[-1].text,
    })
    result_of_supplement = GeminiRequestError("Temporarily unavailable") if supplement_fails else [last, last]
    with patch.object(llm_provider, "generate_grounded_qa", side_effect=[[first], result_of_supplement]) as generate:
        result = QAService(repository=repo).summarize_document("report.pdf")
    assert result["status"] == "SUMMARY_GENERATED"
    assert [claim.cited_page for claim in result["validated_claims"]] == ([1] if supplement_fails else [1, 10])
    assert generate.call_count == 2
    assert generate.call_args.kwargs["supplemental_summary"] is True
    assert {chunk.page_number for chunk in generate.call_args.args[1]} == set(range(2, 11))


@pytest.mark.parametrize("engine", ["gemini", "ollama"])
def test_detailed_summary_fills_uncovered_numbered_sections_on_the_same_page(engine):
    settings.llm_provider = engine
    repo = WorkspaceRepository()
    outline = [
        ("1. Architecture", "Use TCP for commands and UDP for file data."),
        ("2. Requirements", "Submit a report with seven mandatory sections."),
        ("3. Grading", "Live coding counts for twenty percent."),
        ("4. Defense", "Demonstrate a successful upload and download."),
    ]
    repo.chunks = [DocumentChunk(
        chunk_id=str(index), doc_id="brief.docx", doc_name="brief.docx",
        start_line=3 * index - 2, end_line=3 * index,
        text=f"{heading}\n{index}.1 Details\n{fact}",
    ) for index, (heading, fact) in enumerate(outline, 1)]
    claims = [GeneratedClaim(
        claim_text=fact, cited_doc_id="brief.docx", cited_page=1,
        cited_start_line=3 * index, cited_end_line=3 * index, evidence_quote=fact,
    ) for index, (_, fact) in enumerate(outline, 1)]
    with patch.object(llm_provider, "generate_grounded_qa", side_effect=[[claims[0]], claims[1:]]) as generate:
        result = QAService(repository=repo).answer_question(
            "Hãy nêu chi tiết những gì có ở trong file", selected_doc_ids=["brief.docx"],
        )
    assert result["status"] == "SUMMARY_GENERATED"
    assert result["summary_scope"] == "all_indexed_passages"
    assert generate.call_args_list[0].args[1] == repo.chunks
    assert generate.call_args_list[1].args[1] == repo.chunks[1:]
    assert [claim.section for claim in result["validated_claims"]] == [heading for heading, _ in outline]
    assert [claim.subsection for claim in result["validated_claims"]] == [
        f"{index}.1 Details" for index in range(1, 5)
    ]
    assert not result["hallucination_flags"]


def test_detailed_ollama_fallback_excerpts_cover_numbered_sections_on_the_same_page():
    settings.llm_provider = "ollama"
    repo = WorkspaceRepository()
    facts = [
        "TCP carries commands and UDP carries file payloads.",
        "The technical report contains seven mandatory sections.",
        "Live coding contributes twenty percent of the overall grade.",
        "The defense includes a live demonstration of file transfer.",
    ]
    lines = [line for i, fact in enumerate(facts, 1) for line in (f"{i}. Section {i}", fact, "")]
    repo.chunks = [DocumentChunk(
        chunk_id="brief", doc_id="brief.docx", doc_name="brief.docx",
        start_line=1, end_line=len(lines), text="\n".join(lines),
    )]
    with patch.object(llm_provider, "generate_grounded_qa", return_value=[]):
        result = QAService(repository=repo).summarize_document("brief.docx", detailed=True)
    assert result["summary_scope"] == "representative_excerpts"
    assert [claim.claim_text for claim in result["validated_claims"]] == facts


def test_email_and_empty_selection_never_call_gemini(workspace):
    client, headers = workspace
    with patch.object(httpx, "post") as post:
        draft = client.post("/api/chat", headers=headers, json={"query": "Draft an email about the report", "recipient_email": "test@example.org", "selected_doc_ids": ["alpha.txt"]})
        empty = client.post("/api/chat", headers=headers, json={"query": "What is the deadline?", "selected_doc_ids": []})
        assert llm_provider.call_gemini("Email prompt", feature="email") is None
    post.assert_not_called()
    assert draft.json()["status"] == "PENDING_APPROVAL"
    assert empty.json()["status"] == "ABSTAINED_NO_SOURCE_SELECTED"
    status = runtime_service.runtime_status()
    assert status["feature_engines"] == {"qa": "gemini", "study": "gemini", "email": "offline"}
    assert status["gemini_scope"] == "feature1_and_study"


def test_saved_key_does_not_enable_calls_when_another_engine_is_selected():
    settings.llm_provider = "mock"
    with patch.object(httpx, "post") as post:
        assert llm_provider.call_gemini("Do not send") is None
    post.assert_not_called()


@pytest.mark.parametrize("code", [429, 404, 403, 503])
def test_quota_and_access_errors_never_retry_or_switch_models(workspace, code):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=httpx.Response(code, text=KEY)) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    assert result.status_code == 503
    assert KEY not in result.text
    assert "validated_claims" not in result.json()


def test_summary_retries_unavailable_gemini_once_with_same_request():
    unavailable = httpx.Response(503, text=KEY)
    with patch("time.sleep"), patch.object(
        httpx, "post", side_effect=[unavailable, response_text("{}")]
    ) as post:
        assert llm_provider.call_gemini("Test summary", enforce_json=True, feature="summary") == "{}"
    assert len(post.call_args_list) == 2
    assert post.call_args_list[0] == post.call_args_list[1]


def test_summary_returns_verified_local_passages_when_gemini_stays_unavailable(workspace):
    client, headers = workspace
    with patch("time.sleep"), patch.object(httpx, "post", return_value=httpx.Response(503)) as post:
        result = client.post("/api/chat", headers=headers, json={
            "query": "Summarize alpha.txt", "selected_doc_ids": ["alpha.txt"],
        })
    assert post.call_count == 2
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "SUMMARY_GENERATED"
    assert "503" in body["message"]
    assert body["summary_scope"] == "representative_excerpts"
    assert body["validated_claims"][0]["claim_text"] == QUOTE
    assert body["validated_claims"][0]["verification_status"] == "VERIFIED_EXACT"
    assert "BETA-6194" not in body["summary"]


@pytest.mark.parametrize("code,attempts", [(429, 1), (503, 2)])
def test_summary_stops_after_quota_or_persistent_unavailability(code, attempts):
    with patch("time.sleep"), patch.object(
        httpx, "post", return_value=httpx.Response(code, text=KEY)
    ) as post, pytest.raises(GeminiRequestError, match="quota|temporarily unavailable") as error:
        llm_provider.call_gemini("Test summary", feature="summary")
    assert post.call_count == attempts
    assert KEY not in str(error.value)


def test_missing_citations_do_not_get_replaced_with_a_fabricated_quote(workspace):
    client, headers = workspace
    with patch.object(httpx, "post", return_value=response_text('{"answer":"An unsupported answer"}')) as post:
        result = client.post("/api/chat", headers=headers, json={"query": "What is the report deadline?", "selected_doc_ids": ["alpha.txt"]})
    assert post.call_count == 1
    assert result.status_code == 503


def test_connect_enables_qa_and_study_without_sending_content():
    settings.offline_only = True
    settings.llm_provider = "mock"
    models = httpx.Response(200, json={"models": [{"name": "models/" + MODEL, "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models), patch.object(httpx, "post") as post:
        response = TestClient(app).post("/api/runtime/gemini", json={"api_key": KEY, "model": MODEL, "enable_feature1": True, "save_locally": True})
    post.assert_not_called()
    assert response.status_code == 200
    assert response.json()["feature_engines"] == {"qa": "gemini", "study": "gemini", "email": "offline"}
    assert not response.json()["offline_only"]
    assert KEY not in response.text
    assert 'WORKSPACE_OFFLINE_ONLY="false"' in runtime_service.ENV_PATH.read_text()


def test_unavailable_model_preserves_current_configuration():
    settings.offline_only = True
    settings.llm_provider = "mock"
    models = httpx.Response(200, json={"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models):
        with pytest.raises(ValueError, match="no automatic switch"):
            runtime_service.configure_gemini(KEY, model=MODEL, enable_feature1=True)
    assert settings.offline_only and settings.llm_provider == "mock"
    assert not runtime_service.ENV_PATH.exists()


def test_offline_switch_blocks_cloud_immediately_and_is_local_only():
    client = TestClient(app)
    denied = client.post("/api/runtime/offline", headers={"Origin": "https://other.example"}, json={})
    assert denied.status_code == 403
    response = client.post("/api/runtime/offline", json={"save_locally": True})
    assert response.json()["offline_only"]
    assert response.json()["feature_engines"]["qa"] == "offline"
    with patch.object(httpx, "post") as post:
        assert llm_provider.call_gemini("Do not send") is None
    post.assert_not_called()
    assert 'WORKSPACE_OFFLINE_ONLY="true"' in runtime_service.ENV_PATH.read_text()


@pytest.mark.parametrize("pasted", [f'"{KEY}"', f"'{KEY}'", f'GEMINI_API_KEY="{KEY}"', f"export GEMINI_API_KEY='{KEY}'"])
def test_pasted_key_wrappers_are_normalized_without_exposing_credentials(pasted):
    models = httpx.Response(200, json={"models": [{"name": "models/" + MODEL, "supportedGenerationMethods": ["generateContent"]}]})
    with patch.object(httpx, "get", return_value=models) as get:
        result = runtime_service.configure_gemini(pasted, False, MODEL)
    assert get.call_args.kwargs["headers"]["x-goog-api-key"] == KEY
    assert result["engine_mode"] == "gemini"
    assert KEY not in json.dumps(result)
