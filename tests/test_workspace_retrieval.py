import json
from unittest.mock import Mock

from backend.core.config import settings
from backend.core.schemas import GeneratedClaim
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.feature1.qa_service import QAService
from backend.services.feature1.research_index import ResearchIndex


class RecordingEncoder:
    def __init__(self, values=None):
        self.values = values or {}
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return [self.values.get(text, [1.0, 0.0]) for text in texts]


def library(path, encoder, index_id):
    repository = WorkspaceRepository()
    repository.set_embed_fn(encoder, index_id=index_id)
    return DocumentService(repository, library_path=path)


def test_vectors_follow_upload_delete_and_restart(tmp_path):
    path = tmp_path / "workspace.json"
    encoder = RecordingEncoder()
    service = library(path, encoder, "encoder:v1")
    service.ingest_file("alpha.txt", b"Alpha denotes the first release.")
    service.ingest_file("beta.txt", b"Beta denotes the second release.")
    assert encoder.calls == [["Alpha denotes the first release."], ["Beta denotes the second release."]]

    restarted_encoder = RecordingEncoder()
    restarted = library(path, restarted_encoder, "encoder:v1")
    assert restarted_encoder.calls == []
    for _ in range(2):
        result = restarted.repository.search("alpha", selected_doc_ids=["alpha.txt"])
        assert [item.doc_id for item in result] == ["alpha.txt"]
    assert restarted_encoder.calls == [["alpha"], ["alpha"]]

    assert restarted.delete_document("alpha.txt")
    assert restarted.repository.search("alpha", selected_doc_ids=["alpha.txt"]) == []
    assert len(json.loads(path.read_text(encoding="utf-8"))["embeddings"]["vectors"]) == 1


def test_old_snapshot_is_indexed_without_changing_evidence(tmp_path):
    path = tmp_path / "workspace.json"
    legacy = DocumentService(WorkspaceRepository(), library_path=path)
    legacy.ingest_file("notes.txt", b"TCP has ordered delivery.")
    previous = json.loads(path.read_text(encoding="utf-8"))
    assert "embeddings" not in previous

    encoder = RecordingEncoder()
    library(path, encoder, "encoder:v1")
    assert encoder.calls == [["TCP has ordered delivery."]]
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["documents"] == previous["documents"]
    assert updated["chunks"] == previous["chunks"]
    assert updated["embeddings"]["encoder"] == "encoder:v1"

    replacement = RecordingEncoder({"TCP has ordered delivery.": [0.0, 1.0]})
    switched = library(path, replacement, "encoder:v2")
    assert replacement.calls == [["TCP has ordered delivery."]]
    assert json.loads(path.read_text(encoding="utf-8"))["embeddings"]["encoder"] == "encoder:v2"
    assert switched.repository.search("TCP")[0].text == "TCP has ordered delivery."


def test_hybrid_prefers_combined_evidence_inside_selected_sources():
    query = "rocket launch engine calibration"
    combined = "Rocket engine adjustment uses measured thrust."
    paraphrase = "Tune the propulsion unit before liftoff."
    weak_keyword = "Rocket is a salad leaf."
    exact_outside = "Rocket launch engine calibration procedure."
    encoder = RecordingEncoder({
        query: [1.0, 0.0],
        combined: [0.8, 0.6],
        paraphrase: [0.9, 0.436],
        weak_keyword: [0.0, 1.0],
        exact_outside: [1.0, 0.0],
    })
    repository = WorkspaceRepository(encoder)
    repository.ingest_text_document(
        "manual", "manual.txt", [(1, weak_keyword), (2, paraphrase), (3, combined)],
    )
    repository.ingest_text_document("other", "other.txt", [(1, exact_outside)])
    hits = repository.search(query, selected_doc_ids=["manual"])
    assert [hit.text for hit in hits] == [combined, paraphrase, weak_keyword]
    assert hits[-1].score == 0.25
    assert repository.search(query, selected_doc_ids=[]) == []


def test_encoder_failure_leaves_keyword_search_available():
    encoder = Mock(side_effect=RuntimeError("encoder unavailable"))
    repository = WorkspaceRepository(encoder)
    repository.ingest_text_document("tcp", "tcp.txt", [(1, "TCP confirms receipt with an ACK.")])
    assert repository.search("TCP")[0].dense_score == 0
    assert repository.search("orchid taxonomy") == []


def test_procedural_question_recovers_a_passage_with_singular_terms(monkeypatch):
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    query = "How do I display the fetch and push URLs of configured remotes?"
    evidence = "To display the URL for each configured remote, run git remote -v. It prints fetch and push addresses."
    repository = WorkspaceRepository()
    provider = Mock()
    qa = QAService(repository, provider)
    repository.ingest_text_document("guide", "guide.txt", [
        (1, query + " See the example in the next chapter."),
        (2, evidence),
    ])
    repository.ingest_text_document("other", "other.txt", [(1, evidence)])
    selection = ["guide"]
    assert repository.search(query, top_k=1, selected_doc_ids=selection)[0].page_number == 1

    def answer(question, chunks, **kwargs):
        assert question == query
        assert [(chunk.doc_id, chunk.page_number) for chunk in chunks] == [("guide", 2)]
        return [GeneratedClaim(
            claim_text="Run git remote -v.",
            cited_doc_id="guide",
            cited_page=2,
            cited_start_line=1,
            cited_end_line=1,
            evidence_quote=evidence,
        )]

    provider.generate_grounded_qa.side_effect = answer
    result = qa.answer_question(query, top_k=1, selected_doc_ids=selection)
    assert result["status"] == "ANSWER_VERIFIED"
    assert result["validated_claims"][0].verification_status == "VERIFIED_EXACT"


def test_vietnamese_command_question_finds_an_english_passage(monkeypatch):
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    query = "Lệnh nào hiển thị URL fetch và push của các remote đã cấu hình?"
    evidence = "Run git remote -v to display each fetch and push address."
    repository = WorkspaceRepository()
    repository.ingest_text_document("guide", "guide.txt", [(26, evidence)])
    repository.ingest_text_document("unselected", "unselected.txt", [(1, query)])
    provider = Mock()
    provider.generate_grounded_qa.return_value = [GeneratedClaim(
        claim_text="Dùng git remote -v.", cited_doc_id="guide", cited_page=26,
        cited_start_line=1, cited_end_line=1, evidence_quote=evidence,
    )]
    result = QAService(repository, provider).answer_question(query, selected_doc_ids=["guide"])
    assert result["status"] == "ANSWER_VERIFIED"
    assert [chunk.doc_id for chunk in provider.generate_grounded_qa.call_args.args[1]] == ["guide"]


def test_broad_question_reads_other_passages_from_short_source():
    repository = WorkspaceRepository()
    repository.ingest_text_document("checklist", "checklist.txt", [
        (1, "Các bước chuẩn bị: kiểm tra danh sách tài liệu."),
        (2, "Mở ứng dụng và tạo thư mục."),
        (3, "Kết thúc bằng việc lưu nhật ký."),
    ])
    repository.ingest_text_document("other", "other.txt", [(1, "Các bước chuẩn bị ngoài phạm vi.")])
    provider = Mock()
    provider.generate_grounded_qa.return_value = []
    QAService(repository, provider).answer_question(
        "Liệt kê tất cả các bước chuẩn bị", selected_doc_ids=["checklist"],
    )
    evidence = provider.generate_grounded_qa.call_args.args[1]
    assert [(chunk.doc_id, chunk.page_number) for chunk in evidence] == [
        ("checklist", 1), ("checklist", 2), ("checklist", 3),
    ]


def test_standalone_topic_explanation_retrieves_definition_and_example(monkeypatch):
    monkeypatch.setattr(settings, "feature1_semantic_verify", True)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    repo = WorkspaceRepository()
    definition = "A checkpoint records the current configuration."
    example = "$ tool checkpoint save nightly"
    repo.ingest_text_document("guide", "guide.txt", [
        (1, "index\ncheckpoint\nappendix"), (2, definition), (3, example),
    ])
    repo.ingest_text_document("other", "other.txt", [(1, "$ tool checkpoint restore private")])
    provider = Mock()
    provider.generate_grounded_qa.return_value = [GeneratedClaim(
        claim_text="A checkpoint erases the current configuration.", cited_doc_id="guide", cited_page=2,
        cited_start_line=1, cited_end_line=1, evidence_quote=definition,
    )]
    def judge(pairs):
        assert pairs == {"1": {"claim": "A checkpoint erases the current configuration.", "evidence": definition}}
        return {"1": "INSUFFICIENT"}

    provider.judge_claim_support.side_effect = judge
    qa = QAService(repo, provider)
    answer = qa.answer_question("Giải thích thêm về checkpoint và cho ví dụ", selected_doc_ids=["guide"])
    supplied = provider.generate_grounded_qa.call_args.args[1]
    assert any(chunk.text == definition for chunk in supplied)
    assert all(chunk.doc_id == "guide" for chunk in supplied)
    assert answer["status"] == "ANSWER_VERIFIED"
    cited, = answer["validated_claims"]
    assert (cited.cited_doc_id, cited.cited_page, cited.cited_start_line, cited.evidence_quote) == ("guide", 3, 1, example)
    provider.judge_claim_support.assert_called_once()
    assert answer["hallucination_flags"][0].semantic_status == "INSUFFICIENT"

    provider.reset_mock()
    result = qa.answer_question("Giải thích thêm về quasar và cho ví dụ", selected_doc_ids=["guide"])
    assert result["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    provider.generate_grounded_qa.assert_not_called()


def test_research_index_uses_original_selected_passage_in_qa(monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    monkeypatch.setenv("WORKSPACE_RESEARCH_URL", "http://index.test/search")
    repo = WorkspaceRepository()
    evidence = "The prototype carries the internal designation Helios-47."
    repo.ingest_text_document("guide", "guide.txt", [(12, evidence)])
    repo.ingest_text_document("private", "private.txt", [(13, "Another designation is Apollo-12.")])
    selected = repo.get_document_chunks("guide")[0]
    excluded = repo.get_document_chunks("private")[0]
    received = []

    def search(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"hits": [
            {"document_id": "private", "chunk_id": excluded.chunk_id, "score": 0.99},
            {"document_id": "guide", "chunk_id": selected.chunk_id, "score": 0.95},
        ]})

    client_type = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_type(transport=httpx.MockTransport(search), **kwargs))
    provider = Mock()
    provider.generate_grounded_qa.return_value = [GeneratedClaim(
        claim_text="The designation is Helios-47.", cited_doc_id="guide", cited_page=12,
        cited_start_line=1, cited_end_line=1, evidence_quote=evidence,
    )]
    qa = QAService(repo, provider, research_index=ResearchIndex("catalog", repo))
    result = qa.answer_question("What alias identifies the pilot system?", tau_rel=0.90, selected_doc_ids=["guide"])
    assert len(received) == 1 and received[0]["workspace"] == "catalog"
    assert [document["id"] for document in received[0]["documents"]] == ["guide"]
    assert [chunk.chunk_id for chunk in provider.generate_grounded_qa.call_args.args[1]] == [selected.chunk_id]
    claim, = result["validated_claims"]
    assert (claim.cited_doc_id, claim.cited_page, claim.cited_start_line) == ("guide", 12, 1)
