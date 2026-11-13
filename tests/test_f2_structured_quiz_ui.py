"""LLM JSON -> real source mapping -> interactive draft form. No live API."""
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest

from backend.core.config import settings
from backend.providers.f2_gemini_provider import GeminiQuizProvider
from backend.services.f2_source_service import SourceAccessContext


APP = Path(__file__).resolve().parents[1] / "frontend/f2_manual_app.py"
TEXT = "The application sends only selected documents to the chosen provider."
QUESTION = "Ứng dụng gửi những tài liệu nào tới nhà cung cấp đã chọn?"
EXPLANATION = "Ứng dụng chỉ gửi tài liệu đã chọn tới nhà cung cấp được chọn."
KEY = "test-only-interactive-draft-key"


@contextmanager
def cloud(raw=None):
    calls = []
    if raw is None:
        raw = json.dumps({"questions": [{"question": QUESTION,
            "options": [{"option_id": "A", "text": "Các tài liệu đã chọn"},
                        {"option_id": "B", "text": "Mọi tài liệu trong máy"}],
            "correct_option_id": "A", "explanation": EXPLANATION, "source_ids": ["S1"]}]}, ensure_ascii=False)
    def factory(api_key, model):
        assert api_key == KEY
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": raw}]}}]})
        return GeminiQuizProvider(api_key, model, transport=httpx.MockTransport(handler))
    with patch.object(settings, "gemini_api_key", ""), patch(
        "frontend.components.f2_manual_panel.GeminiQuizProvider", side_effect=factory):
        yield calls


def generated():
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not at.exception
    runtime = at.session_state["f2_manual_runtime"]
    doc = runtime["ingestion"].ingest_file("interactive-draft-test.txt", TEXT.encode())["document"]
    at.run()
    at.multiselect(key="f2_manual_selected").select(doc.doc_id).run()
    at.selectbox(key="f2_manual_engine").set_value("Gemini").run()
    at.text_input(key="f2_manual_gemini_key").set_value(KEY).run()
    at.button(key="f2_manual_generate").click().run()
    assert not at.exception
    return at


def start_preview(at):
    at.button(key="f2_manual_try_draft").click().run()
    assert not at.exception
    assert at.session_state["f2_manual_active"] is None
    return at.session_state["f2_manual_draft_quiz"]


def submit(at):
    next(b for b in at.button if b.label == "Nộp bản nháp").click().run()
    assert not at.exception


def test_natural_llm_json_becomes_radio_form_with_hidden_proposals_before_submit():
    with cloud() as calls:
        at = generated()
        assert len(calls) == 1
        state = start_preview(at)
        assert len(at.form) == 1 and not at.expander and not at.success
        assert any(t.value == QUESTION for t in at.text)
        assert not any(t.value == EXPLANATION or t.value == TEXT or "Đáp án AI đề xuất:" in t.value for t in at.text)
        assert at.radio(key=f"f2_draft_answer_{state['attempt_id']}_q1").value is None
        assert any("UNVERIFIED_DRAFT" in c.value for c in at.caption)
        assert any("chưa phải kết quả" in w.value for w in at.warning)


def test_submit_reveals_comparison_explanation_and_sources_without_verified_score():
    with cloud() as calls:
        at = generated()
        state = start_preview(at)
        at.radio(key=f"f2_draft_answer_{state['attempt_id']}_q1").set_value("A")
        submit(at)
        assert len(calls) == 1 and not at.form and not at.success
        assert any("Khớp đáp án AI đề xuất: 1/1" in i.value and "chưa phải điểm đã kiểm chứng" in i.value for i in at.info)
        assert any(t.value == EXPLANATION for t in at.text)
        assert len(at.expander) == 1 and any(t.value == TEXT for t in at.text)
        assert at.session_state["f2_manual_active"] is None
        runtime = at.session_state["f2_manual_runtime"]
        context = SourceAccessContext(runtime["workspace_id"], frozenset(runtime["repository"].documents))
        assert runtime["review"].review(at.session_state["f2_manual_draft"]["resource"], context=context).validation.status == "REVIEW_REQUIRED"


def test_empty_submission_reports_unanswered_against_actual_count():
    with cloud():
        at = generated()
        start_preview(at)
        submit(at)
        assert any("Khớp đáp án AI đề xuất: 0/1" in i.value for i in at.info)
        assert any("Đã trả lời 0/1" in c.value for c in at.caption)


def test_retry_creates_blank_form_and_keeps_full_generated_draft():
    with cloud() as calls:
        at = generated()
        state = start_preview(at)
        old_id = state["attempt_id"]
        at.radio(key=f"f2_draft_answer_{old_id}_q1").set_value("B")
        submit(at)
        at.button(key="f2_manual_retry_draft").click().run()
        assert not at.exception and len(calls) == 1
        new = at.session_state["f2_manual_draft_quiz"]
        assert new["attempt_id"] != old_id and new["submission"] is None
        assert at.radio(key=f"f2_draft_answer_{new['attempt_id']}_q1").value is None
        assert at.form and not at.expander
        at.button(key="f2_manual_back_review").click().run()
        assert not at.exception and not at.form and len(at.expander) == 1
        assert at.session_state["f2_manual_draft"]["resource"].questions[0].question == QUESTION


def test_source_change_blocks_preview_display_and_submission():
    with cloud():
        at = generated()
        start_preview(at)
        at.session_state["f2_manual_runtime"]["repository"].chunks[0].text = TEXT.replace("only selected", "all")
        at.run()
        assert not at.exception and at.error and not at.form and not at.expander
        assert not any(t.value == QUESTION or t.value == EXPLANATION or t.value == TEXT for t in at.text)


def test_malformed_llm_json_never_creates_interactive_quiz_or_demo_fallback():
    with cloud('```json\n{"questions": []}\n```') as calls:
        at = generated()
        assert len(calls) == 1 and at.error and not at.form
        assert at.session_state["f2_manual_active"] is None and at.session_state["f2_manual_draft"] is None


def test_generate_again_leaves_preview_and_uses_new_response_and_resource():
    with cloud() as calls:
        at = generated()
        state = start_preview(at)
        old_quiz_id = state["quiz_set_id"]
        at.button(key="f2_manual_generate").click().run()
        assert not at.exception and len(calls) == 2 and not at.form
        assert at.session_state["f2_manual_draft_quiz"] is None
        assert at.session_state["f2_manual_draft"]["resource"].quiz_set_id != old_quiz_id
