"""Run the curated prompt cases through the current router and QA dispatcher."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.core.schemas import RouteType, UserRequest
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.feature1.qa_service import QAService
from backend.services.router_service import route_user_request


DATA = json.loads((Path(__file__).parent / "fixtures" / "feature1_prompt_cases.json").read_text(encoding="utf-8"))


@pytest.fixture
def prompt_service(monkeypatch):
    repository = WorkspaceRepository()
    embedding = Mock()
    embedding.get_embed_fn.return_value = None
    provider = Mock()
    provider.generate_grounded_qa.return_value = []
    service = QAService(repository, provider, embedding)
    repository.ingest_text_document("git-guide.pdf", "git-guide.pdf", [
        (1, "Git fetch reads remote changes. Git pull fetches and merges. Git push can be rejected."),
        (2, "Appendix A — Command Cheat Sheet\nTask\nCommand\nCheck status\ngit status\nStage edits\ngit add ."),
    ])
    repository.ingest_text_document("calculus.pdf", "calculus.pdf", [
        (1, "Miền xác định là tập các điểm tại đó biểu thức có nghĩa. Tập D cho trước giới hạn miền xác định."),
    ])
    monkeypatch.setattr(service, "summarize_document", Mock(return_value={"status": "SUMMARY_GENERATED"}))
    monkeypatch.setattr(service, "_answer_outline_section", Mock(return_value={"status": "ANSWER_VERIFIED"}))
    return service


def test_prompt_dataset_sources_and_ids_are_consistent():
    assert {case["source"] for case in DATA["cases"]} == set(DATA["sources"])
    assert len({case["id"] for case in DATA["cases"]}) == len(DATA["cases"])
    assert len({
        (case["query"].casefold(), tuple(case["selected_doc_ids"]), json.dumps(case.get("history", []), sort_keys=True))
        for case in DATA["cases"]
    }) == len(DATA["cases"])


def test_document_main_topics_reads_explicit_agenda_instead_of_unrelated_snippets(prompt_service):
    doc = "chapter.pptx"
    agenda = "Application layer: overview\nNetwork applications\nHTTP\nDNS\nP2P\nApplication Layer: 2-2"
    prompt_service.repository.ingest_text_document(doc, doc, [(2, agenda), (97, "The value is t0."), (124, "netcinema.com")])
    prompt_service.repository.ingest_text_document("excluded", "excluded", [(2, "Agenda\nPrivate A\nPrivate B\nPrivate C")])
    result = prompt_service.answer_question("Tài liệu này trình bày những chủ đề chính nào?", selected_doc_ids=[doc])
    assert result["status"] == "ANSWER_VERIFIED"
    assert [claim.claim_text for claim in result["validated_claims"]] == ["Network applications", "HTTP", "DNS", "P2P"]
    assert all(claim.cited_doc_id == doc and claim.cited_page == 2 for claim in result["validated_claims"])
    prompt_service.provider.generate_grounded_qa.assert_not_called()
    prompt_service.summarize_document.assert_not_called()


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: case["id"])
def test_feature1_prompt_case(case, prompt_service):
    expected = case["expected"]
    intent = expected["intent"]
    request = UserRequest(
        query=case["query"], selected_doc_ids=case["selected_doc_ids"],
        conversation_history=case.get("history", []),
    )
    route, missing = route_user_request(request)
    if intent == "email_clarification":
        assert route == RouteType.CLARIFICATION_FLOW and expected["slot"] in missing
        return

    assert route == RouteType.QA_FLOW
    response = prompt_service.answer_question(
        request.query, selected_doc_ids=request.selected_doc_ids,
        conversation_history=request.conversation_history,
        tau_rel=0 if intent == "qa" else None,
    )
    if intent == "document_summary":
        options = {"brief": True} if expected["depth"] == "brief" else {"detailed": expected["depth"] == "detailed"}
        prompt_service.summarize_document.assert_called_once_with(expected["document"], **options)
        prompt_service._answer_outline_section.assert_not_called()
    elif intent == "outline":
        args, options = prompt_service._answer_outline_section.call_args
        assert args[:2] == (expected["number"], request.selected_doc_ids)
        assert options == {
            "by_subsection": expected["depth"] != "standard",
            "detailed": expected["depth"] == "detailed",
        }
        prompt_service.summarize_document.assert_not_called()
    else:
        prompt_service.summarize_document.assert_not_called()
        prompt_service._answer_outline_section.assert_not_called()

    if intent == "qa":
        prompt_service.provider.generate_grounded_qa.assert_called_once()
        question, chunks = prompt_service.provider.generate_grounded_qa.call_args.args
        assert all(term in question.casefold() for term in expected["contains"])
        assert chunks and {chunk.doc_id for chunk in chunks} <= set(request.selected_doc_ids)
    else:
        prompt_service.provider.generate_grounded_qa.assert_not_called()

    if intent == "command_reference":
        assert response["status"] == "ANSWER_VERIFIED"
        claims = response["validated_claims"]
        assert {claim.cited_doc_id for claim in claims} == set(request.selected_doc_ids)
        assert all(any(term in claim.claim_text for claim in claims) for term in expected["contains"])
    elif "status" in expected:
        assert response["status"] == expected["status"]
        assert not response["validated_claims"]
        if "slot" in expected:
            assert response["route"] == RouteType.CLARIFICATION_FLOW
            assert expected["slot"] in response["missing_slots"]
        if "message_contains" in expected:
            assert expected["message_contains"] in response["message"]
