import json
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import app
from backend.providers.feature2.f2_gemini_provider import GeminiStudyProvider
from backend.providers.feature2.f2_study_provider import StudyProviderError


def test_react_study_practice_keeps_answers_on_server_until_action(monkeypatch):
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-only-api-key")
    prompts = []

    def generate(self, prompt, study_format):
        prompts.append(study_format)
        assert "Cache: Fast temporary memory." in prompt
        assert "untrusted_document_data" in prompt and "learning_objectives" in prompt
        assert "EXCLUDED_SENTINEL" not in prompt
        if study_format == "quiz":
            questions = [{
                "question": "Which memory would suit a short-lived lookup?",
                "options": [{"option_id": "A", "text": "Cache"}, {"option_id": "B", "text": "CPU"}],
                "correct_option_id": "A", "explanation": "Cache is temporary memory.", "source_ids": ["S1"],
            }]
            if "single, multiple, blank, short" in prompt:
                assert "độ khó hard" in prompt and "tiếng Anh" in prompt and "focus probe" in prompt
                questions += [
                    {"kind": "multiple", "question": "Which entries describe storage?", "options": [
                        {"option_id": "A", "text": "Cache"}, {"option_id": "B", "text": "RAM"},
                        {"option_id": "C", "text": "CPU"}], "correct_option_id": "A", "extra_keys": ["B"],
                        "explanation": "Cache and RAM store data.", "source_ids": ["S1"]},
                    {"kind": "blank", "question": "A short-lived lookup can use [___].", "options": [],
                        "correct_option_id": "cache", "extra_keys": ["a cache"],
                        "explanation": "Cache provides temporary memory.", "source_ids": ["S1"]},
                    {"kind": "short", "question": "What component executes instructions?", "options": [],
                        "correct_option_id": "CPU", "explanation": "The CPU executes instructions.", "source_ids": ["S1"]},
                ]
            return json.dumps({"questions": questions})
        return json.dumps({"cards": [
            {"front": "Why is a cache useful for quick access?", "back": "It provides temporary storage with fast access.", "source_ids": ["S1"]},
            {"front": "What makes a cache suitable for short-lived data?", "back": "It holds data temporarily.", "source_ids": ["S1"]},
        ]})

    monkeypatch.setattr(GeminiStudyProvider, "generate_from_prompt", generate)
    client = TestClient(app)
    headers = {"X-Workspace-ID": str(uuid4()), "X-Study-Learner": str(uuid4())}
    response = client.post("/api/documents/upload", headers=headers, files={
        "file": ("study.txt", b"Cache: Fast temporary memory.\nRAM: Volatile working storage.\nCPU: A processor executing instructions."),
    })
    assert response.status_code == 200
    doc_id = response.json()["document"]["doc_id"]
    client.post("/api/documents/upload", headers=headers, files={
        "file": ("excluded.txt", b"EXCLUDED_SENTINEL: Do not use this neighboring document."),
    })

    def create(kind):
        response = client.post("/api/study", headers=headers, json={
            "selected_doc_ids": [doc_id], "requested_count": 3, "study_format": kind, "engine": "gemini",
        })
        assert response.status_code == 200, response.text
        return response.json()

    quiz = create("quiz")
    assert quiz["draft"] is True
    quiz_url = f"/api/study/quiz/{quiz['session_id']}"
    assert "correct_option_id" not in str(quiz)
    assert client.get(quiz_url, headers={**headers, "X-Study-Learner": str(uuid4())}).status_code == 404
    question = quiz["questions"][0]
    assert question["question"] == "Which memory would suit a short-lived lookup?"
    submitted = client.post(quiz_url, headers=headers, json={"answers": [{
        "question_id": question["question_id"], "option_id": question["options"][0]["option_id"],
    }]})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["answered_count"] == 1
    assert submitted.json()["items"][0]["source_refs"][0]["doc_id"] == doc_id
    assert client.get(quiz_url, headers=headers).json()["result"] == submitted.json()

    card = create("flashcards")
    assert card["draft"] is True and card["front"] == "Why is a cache useful for quick access?"
    card_url = f"/api/study/flashcard/{card['session_id']}"
    assert "back" not in card and "source_refs" not in card
    flipped = client.post(card_url, headers=headers, json={"card_id": card["card_id"], "action": "flip"})
    assert flipped.status_code == 200, flipped.text
    assert flipped.json()["side"] == "back"
    assert flipped.json()["source_refs"][0]["doc_id"] == doc_id
    next_card = client.post(card_url, headers=headers, json={"card_id": card["card_id"], "action": "next"}).json()
    assert next_card["current_index"] == 1 and "back" not in next_card
    assert prompts == ["quiz", "flashcards"]

    request = {"selected_doc_ids": [doc_id], "requested_count": 3, "study_format": "quiz", "engine": "gemini"}
    mixed = client.post("/api/study", headers=headers, json={
        **request, "requested_count": 4, "question_types": ["single", "multiple", "blank", "short"],
        "difficulty": "hard", "language": "en", "focus": "focus probe",
    })
    assert mixed.status_code == 200, mixed.text
    view = mixed.json()
    assert view["draft"] and {q["kind"] for q in view["questions"]} == {"single", "multiple", "blank", "short"}
    assert not any("extra_keys" in q or "correct_option_id" in q for q in view["questions"])
    mixed_url = f"/api/study/quiz/{view['session_id']}"
    answers = [
        {"question_id": "q2", "option_ids": ["B", "A"]},
        {"question_id": "q3", "text": " A CACHE. "},
        {"question_id": "q4", "text": "cpu"},
    ]
    score = client.post(mixed_url, headers=headers, json={"answers": answers})
    assert score.status_code == 200, score.text
    assert score.json()["correct_count"] == 3
    assert score.json()["items"][2]["expected_text"] == "cache"
    answers[0]["option_ids"].reverse()
    assert client.post(mixed_url, headers=headers, json={"answers": answers}).json() == score.json()
    monkeypatch.setattr(settings, "offline_only", True)
    assert client.post("/api/study", headers=headers, json=request).status_code == 409
    assert prompts == ["quiz", "flashcards", "quiz"]

    def unavailable(*args):
        raise StudyProviderError("PROVIDER_UNAVAILABLE", "Gemini test unavailable")

    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(GeminiStudyProvider, "generate_from_prompt", unavailable)
    failure = client.post("/api/study", headers=headers, json=request)
    assert failure.status_code == 503
    assert failure.json()["detail"] == "Gemini test unavailable"
