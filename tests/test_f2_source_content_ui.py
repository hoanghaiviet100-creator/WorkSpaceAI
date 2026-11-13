"""Manual UI tests use real ingestion/services and HTTP MockTransport only."""
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from backend.algorithms.f2_content_support import CARD_CLOZE_PREFIX, QUIZ_CLOZE_PREFIX
from backend.core.config import settings
from backend.providers.f2_gemini_provider import GeminiFlashcardProvider, GeminiQuizProvider


APP = Path(__file__).resolve().parents[1] / "frontend/f2_manual_app.py"
TEXT = "Khi gửi yêu cầu, hệ thống chỉ sử dụng các tài liệu đã chọn."
ANSWER = "các tài liệu đã chọn"
KEY = "test-only-ui-no-real-key"


def app(text=TEXT):
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not at.exception
    runtime = at.session_state["f2_manual_runtime"]
    doc = runtime["ingestion"].ingest_file("source-content-test.txt", text.encode())["document"]
    at.run()
    at.multiselect(key="f2_manual_selected").select(doc.doc_id).run()
    assert not at.exception
    return at


def items(study_format, mixed=False, natural=False):
    context = TEXT.replace(ANSWER, "[___]")
    if study_format == "quiz":
        value = {"question": ("Tài liệu nào được dùng khi gửi yêu cầu?" if natural else QUIZ_CLOZE_PREFIX + "\n" + context),
            "options": [{"option_id": "A", "text": ANSWER}, {"option_id": "B", "text": "mọi tài liệu trên mạng"}],
            "correct_option_id": "A", "explanation": "Theo đoạn nguồn: " + TEXT, "source_ids": ["S1"]}
    else:
        value = {"front": "Tài liệu nào được dùng khi gửi yêu cầu?" if natural else CARD_CLOZE_PREFIX + "\n" + context,
            "back": ANSWER, "source_ids": ["S1"]}
    return [value, *items(study_format, natural=True)] if mixed else [value]


@contextmanager
def cloud(study_format="quiz", *, mixed=False, natural=False, empty=False, status=200):
    calls = []
    raw = json.dumps({"questions" if study_format == "quiz" else "cards": [] if empty else items(study_format, mixed, natural)}, ensure_ascii=False)
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"candidates": [{"finishReason": "STOP",
            "content": {"role": "model", "parts": [{"text": raw}]}}]} if status == 200 else {"error": KEY})
    provider_type = GeminiQuizProvider if study_format == "quiz" else GeminiFlashcardProvider
    def factory(api_key, model):
        assert api_key == KEY
        return provider_type(api_key, model, transport=httpx.MockTransport(handler))
    with patch.object(settings, "gemini_api_key", ""), patch(
        "frontend.components.f2_manual_panel." + provider_type.__name__, side_effect=factory):
        yield calls


def select_cloud(at, study_format="quiz"):
    at.selectbox(key="f2_manual_engine").set_value("Gemini").run()
    if study_format == "flashcards":
        at.radio(key="f2_manual_format").set_value("Flashcards").run()
    at.text_input(key="f2_manual_gemini_key").set_value(KEY).run()
    assert not at.exception


def generate(at):
    at.button(key="f2_manual_generate").click().run()
    assert not at.exception


def test_preview_is_opt_in_and_shows_real_text_and_eligibility_counts():
    at = app()
    assert not at.expander and not at.code
    at.button(key="f2_manual_inspect").click().run()
    assert not at.exception and at.code[0].value == TEXT
    assert any("1 đoạn đủ điều kiện" in c.value for c in at.caption)
    assert not at.form and not at.success


def test_empty_extraction_preview_explains_zero_usable_passages():
    at = app("CONTENTS\n-----\n1\n2")
    at.button(key="f2_manual_inspect").click().run()
    assert not at.exception and at.code
    assert any("0 đoạn đủ điều kiện" in c.value for c in at.caption)
    assert any("Không có đoạn" in w.value for w in at.warning)


def test_generate_clears_preview_before_quiz_answer_boundary():
    with cloud() as calls:
        at = app()
        select_cloud(at)
        at.button(key="f2_manual_inspect").click().run()
        assert at.code
        generate(at)
        assert len(calls) == 1 and at.form and not at.code and not at.expander


def test_user_can_select_new_prompt_or_unchanged_definition_mode():
    with cloud() as calls:
        at = app()
        select_cloud(at)
        generate(at)
        at.selectbox(key="f2_manual_content_mode").set_value("Định nghĩa (như bản cũ)").run()
        generate(at)
        prompts = [json.loads(c.content)["contents"][0]["parts"][0]["text"] for c in calls]
        assert "Không giới hạn ở cặp term/definition" in prompts[0]
        assert "Giới hạn của phiên thử Q05" in prompts[1]


@pytest.mark.parametrize("study_format", ["quiz", "flashcards"])
def test_natural_output_is_visible_author_draft_without_learner_release(study_format):
    with cloud(study_format, natural=True):
        at = app()
        select_cloud(at, study_format)
        generate(at)
        assert at.session_state["f2_manual_active"] is None
        assert at.session_state["f2_manual_draft"]["resource"] is not None
        assert not at.form and len(at.expander) == 1
        assert any("Bản nháp cần review" in s.value for s in at.subheader)
        assert any(TEXT == t.value for t in at.text)
        assert not any(b.key == "f2_manual_practice_subset" for b in at.button)


@pytest.mark.parametrize("study_format", ["quiz", "flashcards"])
def test_mixed_draft_requires_explicit_subset_then_hides_author_answers(study_format):
    with cloud(study_format, mixed=True):
        at = app()
        select_cloud(at, study_format)
        generate(at)
        assert len(at.expander) == 2 and at.session_state["f2_manual_active"] is None
        assert at.button(key="f2_manual_practice_subset").label == "Luyện tập 1 mục đã kiểm chứng"
        at.button(key="f2_manual_practice_subset").click().run()
        assert not at.exception and not at.expander
        assert at.session_state["f2_manual_active"]["format"] == study_format
        assert not any("AI đề xuất:" in t.value for t in at.text)
        assert len(at.session_state["f2_manual_draft"]["resource"].questions if study_format == "quiz"
                   else at.session_state["f2_manual_draft"]["resource"].cards) == 2
        at.button(key="f2_manual_return_draft").click().run()
        assert not at.exception and len(at.expander) == 2 and not at.form


def test_draft_revalidation_removes_subset_action_when_source_changes():
    with cloud(mixed=True):
        at = app()
        select_cloud(at)
        generate(at)
        at.session_state["f2_manual_runtime"]["repository"].chunks[0].text = TEXT.replace("chỉ", "không")
        at.run()
        assert not at.exception and not at.form
        assert not any(b.key == "f2_manual_practice_subset" for b in at.button)
        assert not any(TEXT == t.value for t in at.text)


def test_empty_model_output_is_distinguished_from_empty_extraction():
    with cloud(empty=True) as calls:
        at = app()
        select_cloud(at)
        generate(at)
        assert len(calls) == 1 and at.session_state["f2_manual_active"] is None
        assert any("BỘ SINH: trả về danh sách rỗng" in c.value for c in at.caption)
        assert not any("Chưa đủ nội dung" in w.value for w in at.warning)


def test_no_usable_source_does_not_call_provider_or_claim_connection():
    with cloud() as calls:
        at = app("CONTENTS\n-----\n1")
        select_cloud(at)
        generate(at)
        assert calls == [] and not at.form
        assert any("NGUỒN:" in c.value for c in at.caption)


def test_api_failure_diagnostic_has_safe_http_status_and_no_fallback():
    with cloud(status=429) as calls:
        at = app()
        select_cloud(at)
        generate(at)
        assert len(calls) == 1 and not at.form and not at.success
        assert any("HTTP 429" in w.value for w in at.warning)
        assert any("API: yêu cầu thất bại" in c.value for c in at.caption)
        assert all(KEY not in w.value for w in [*at.warning, *at.error, *at.info, *at.caption])


def test_runtime_upgrade_keeps_ingested_repository_and_masked_key_widget():
    with cloud() as calls:
        at = app()
        select_cloud(at)
        runtime = at.session_state["f2_manual_runtime"]
        repository, practice = runtime["repository"], runtime["practice"]
        ids = tuple(repository.documents)
        runtime.pop("version")
        at.run()
        assert not at.exception and calls == []
        updated = at.session_state["f2_manual_runtime"]
        assert updated["repository"] is repository and tuple(repository.documents) == ids
        assert updated["previous_practice"] is practice and updated["practice"] is not practice
        assert at.text_input(key="f2_manual_gemini_key").value == KEY
        assert at.multiselect(key="f2_manual_selected").value == list(ids)
