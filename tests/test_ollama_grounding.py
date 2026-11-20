from backend.core.schemas import UserRequest, RouteType, DocumentChunk
from backend.services.router_service import route_user_request
from backend.providers.llm_provider import LLMProvider
from backend.core.config import settings
import pytest

@pytest.mark.parametrize('query', ['Thư viện socket dùng để làm gì?', 'Các bước thông thường là gì?', 'Explain sendall in sockets', 'What is an iterable?'])
def test_document_questions_are_not_actions(query):
    assert route_user_request(UserRequest(query=query))[0] == RouteType.QA_FLOW

def test_explicit_email_still_requests_recipient():
    assert route_user_request(UserRequest(query='Soạn thư báo cáo tiến độ dự án'))[0] == RouteType.CLARIFICATION_FLOW

@pytest.mark.parametrize('response', ['{"answer":"Unsupported answer","citations":[]}', '{"answer":"Unsupported answer"}', '[]', 'plain unsupported answer'])
def test_ollama_never_invents_citations(monkeypatch, response):
    monkeypatch.setattr(settings, 'llm_provider', 'ollama')
    monkeypatch.setattr(settings, 'offline_only', False)
    provider = LLMProvider()
    monkeypatch.setattr(provider, 'is_ollama_online', lambda: True)
    monkeypatch.setattr(provider, 'call_ollama', lambda *args, **kwargs: response)
    chunk = DocumentChunk(chunk_id='c', doc_id='d', doc_name='d', text='Real source text')
    assert provider.generate_grounded_qa('Question', [chunk]) == []

from backend.services.feature1.qa_service import expand_contextual_query, is_detail_followup, outline_request, QAService

@pytest.mark.parametrize('followup', ['mô tả một cách chi tiết', 'hãy giải thích chi tiết hơn', 'chi tiết hơn', 'explain in detail'])
def test_elaboration_keeps_original_topic_across_followups(followup):
    history = [
        {'role': 'user', 'content': 'Thư viện socket dùng để làm gì?'},
        {'role': 'assistant', 'content': 'Socket kết nối client và server.'},
        {'role': 'user', 'content': 'giải thích chi tiết hơn'},
        {'role': 'assistant', 'content': 'Thông tin trao đổi qua socket.'},
    ]
    result = expand_contextual_query(followup, history)
    assert 'Thư viện socket' in result
    assert followup in result

@pytest.mark.parametrize('query', [
    'Mô tả chi tiết HTTP và HTTPS', 'Giải thích chi tiết thư viện asyncio',
    'Hạn nộp báo cáo là ngày nào?', 'Ăn cơm chưa?', 'UDP?', 'Hôm nay trên phố có mưa không?',
    'Thế giới có bao nhiêu nước?', 'Vậy thủ đô nước Pháp là gì?',
])
def test_new_subject_is_not_replaced(query):
    assert not is_detail_followup(query)
    assert expand_contextual_query(query, [{'role': 'user', 'content': 'Socket là gì?'}]) == query


def test_named_followup_uses_its_previous_topic_after_an_intervening_question():
    earlier = 'Lệnh git remote -v khác git remote ở điểm nào'
    chapter = 'Chương 8 hướng dẫn những thao tác nào khi làm việc với GitHub?'
    followup = 'Giải thích kỹ hơn phần vừa nói về remote và cho ví dụ có trong tài liệu'
    history = [{'role': 'user', 'content': text} for text in [earlier, chapter]]
    assert expand_contextual_query(followup, history) == f'{earlier} {followup}'
    assert outline_request(chapter) == ('8', True, False)


def test_unrelated_questions_never_send_ftp_evidence_to_ollama():
    from unittest.mock import Mock
    from backend.repositories.workspace_repository import WorkspaceRepository

    repo = WorkspaceRepository()
    repo.ingest_text_document("ftp.txt", "ftp.txt", [
        (1, "FTP uses TCP for the control channel. RETR downloads the specified file."),
        (2, "The data channel uses UDP. The server supports uploading a single file."),
    ])
    provider = Mock()
    provider.generate_grounded_qa.return_value = []
    service = QAService(repository=repo, provider=provider)
    history = [{"role": "user", "content": "Lệnh RETR dùng để làm gì?"}]
    selected = ["ftp.txt"]

    for question in ("Ăn cơm chưa", "Đá bóng không?", "What is the capital of France?"):
        result = service.answer_question(question, selected_doc_ids=selected, conversation_history=history)
        assert result["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
        assert result["validated_claims"] == []
    provider.generate_grounded_qa.assert_not_called()

    service.answer_question("UDP?", selected_doc_ids=selected, conversation_history=history)
    assert "UDP" in provider.generate_grounded_qa.call_args.args[1][0].text
    assert provider.generate_grounded_qa.call_args.kwargs["conversation_history"] is None

def test_retrieval_and_generation_both_receive_followup_topic():
    class Repo:
        dense_available = False
        def set_embed_fn(self, fn): pass
        def search(self, query, **kwargs):
            self.query = query
            return [DocumentChunk(chunk_id='c', doc_id='d', doc_name='d', text='Socket kết nối client và server.', score=1)]
        def build_page_lookup(self): return {}
    class Provider:
        def generate_grounded_qa(self, query, chunks, **kwargs):
            self.query = query
            return []
    repo, provider = Repo(), Provider()
    QAService(repository=repo, provider=provider).answer_question(
        'mô tả một cách chi tiết', selected_doc_ids=['d'],
        conversation_history=[{'role': 'user', 'content': 'Socket là gì?'}])
    assert 'Socket' in repo.query
    assert repo.query == provider.query

from backend.providers.prompts import build_qa_prompt, requests_detailed_answer

def test_detailed_prompt_preserves_explanation_in_visible_claims():
    chunk = DocumentChunk(chunk_id='c', doc_id='d', doc_name='d', text='socket opens a network endpoint')
    prompt = build_qa_prompt('Socket là gì? mô tả một cách chi tiết', [chunk], [{'role': 'assistant', 'content': 'Previous short answer'}])
    assert 'YÊU CẦU TRIỂN KHAI CHI TIẾT' in prompt
    assert '2–4 câu' in prompt
    assert 'không phải lặp lại' in prompt
    assert 'citations[].claim' in prompt
    assert not requests_detailed_answer('Socket là gì?')

@pytest.mark.parametrize('query,budget', [('Socket là gì?', 1024), ('Mô tả socket chi tiết', 2048)])
def test_ollama_detail_budget_keeps_context_and_cpu_limits(monkeypatch, query, budget):
    from types import SimpleNamespace
    import importlib
    provider_module = importlib.import_module("backend.providers.llm_provider")
    monkeypatch.setattr(settings, 'llm_provider', 'ollama')
    monkeypatch.setattr(settings, 'offline_only', False)
    provider = LLMProvider()
    monkeypatch.setattr(provider, 'is_ollama_online', lambda: True)
    monkeypatch.setattr(provider, 'get_effective_ollama_model', lambda: 'qwen2.5:7b')
    captured = {}
    def post(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {'response': 'ok'})
    monkeypatch.setattr(provider_module.httpx, 'post', post)
    provider.generate_grounded_qa(query, [DocumentChunk(chunk_id="c", doc_id="d", doc_name="d", text="Socket source")])
    assert captured['json']['options']['num_predict'] == budget
    assert captured['json']['options']['num_ctx'] == 4096
    assert captured['json']['options']['num_thread'] == 4
    citation = captured['json']['format']['properties']['citations']['items']
    assert citation['required'] == ['claim', 'source_id', 'excerpt']
    assert citation['properties']['source_id']['enum'] == [1]

@pytest.mark.parametrize('query', ['alo', 'xin chào!', 'hello'])
def test_greeting_does_not_retrieve_or_repeat_document(query):
    class Repo:
        def set_embed_fn(self, fn): pass
        def search(self, *args, **kwargs): raise AssertionError('Greeting must not search documents')
    result = QAService(repository=Repo()).answer_question(query, selected_doc_ids=[], conversation_history=[{'role':'user','content':'Socket là gì?'}])
    assert result['status'] == 'CONVERSATION'
    assert not result['validated_claims']

@pytest.mark.parametrize('query', ['hãy nêu giúp tôi file trên đang nói về chủ đề gì', 'hãy nêu cho tôi biết những gì có trong file'])
def test_document_overview_uses_summary_instead_of_random_top_snippets(query, monkeypatch):
    service = QAService()
    import importlib
    monkeypatch.setattr(importlib.import_module('backend.services.feature1.qa_service'), 'resolve_summary_target', lambda *args: 'selected.pdf')
    monkeypatch.setattr(service, 'summarize_document', lambda doc_id, **kwargs: {'status':'SUMMARY_GENERATED','doc_name':doc_id})
    assert service.answer_question(query, selected_doc_ids=['selected.pdf'])['doc_name'] == 'selected.pdf'


@pytest.mark.parametrize("query", [
    "Hãy miêu tả chi tiết toàn bộ những thông tin trong file giúp tôi",
    "Hãy nêu chi tiết những gì có ở trong file",
    "Hãy nêu chi tiết những gì có trong file",
    "Hãy nêu chi tiết những gì có trên file",
    "Cho tôi biết chi tiết tài liệu này có những gì",
])
def test_whole_document_description_uses_detailed_summary(monkeypatch, query):
    from unittest.mock import Mock
    import importlib

    service = QAService()
    monkeypatch.setattr(importlib.import_module('backend.services.feature1.qa_service'), 'resolve_summary_target', lambda *args: 'selected.pdf')
    summarize = Mock(return_value={'status': 'SUMMARY_GENERATED'})
    monkeypatch.setattr(service, 'summarize_document', summarize)
    service.answer_question(query, selected_doc_ids=['selected.pdf'])
    summarize.assert_called_once_with('selected.pdf', detailed=True)


@pytest.mark.parametrize("query", [
    "Hãy nêu chi tiết lệnh RETR trong file", "Tóm tắt chương 8 của tài liệu",
    "Tóm tắt quy trình commit trong file",
])
def test_specific_question_in_file_uses_retrieval(monkeypatch, query):
    from unittest.mock import Mock

    service = QAService()
    search = Mock(return_value=[])
    monkeypatch.setattr(service.repository, "search", search)
    service.answer_question(query, selected_doc_ids=["selected.docx"])
    search.assert_called_once()


def test_long_document_summary_keeps_chapter_openings_and_appendix(monkeypatch):
    from unittest.mock import Mock
    from backend.repositories.workspace_repository import WorkspaceRepository

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    repo = WorkspaceRepository()
    doc = "tutorial.pdf"
    repo.chunks = [
        DocumentChunk(
            chunk_id=str(page), doc_id=doc, doc_name=doc, page_number=page,
            text={2: "1. Why Version Control?", 4: "2. Working with GitHub",
                  6: "Appendix A — Command Cheat Sheet"}.get(page, "Exercises"),
        )
        for page in range(1, 8)
    ]
    for chunk in repo.chunks:
        chunk.text += "\n" + ("A paragraph describing a Git concept. " * 110)
        chunk.end_line = 2
    provider = Mock()
    provider.get_effective_ollama_model.return_value = "qwen-test"
    provider.generate_summary_stage.return_value = {}
    QAService(repository=repo, provider=provider).answer_question(
        "Hãy nêu chi tiết những gì có trên file", selected_doc_ids=[doc],
    )
    calls = provider.generate_summary_stage.call_args_list
    assert all(call.kwargs["stage"] == "map" for call in calls)
    prompts = "\n".join(call.args[0] for call in calls)
    assert all(heading in prompts for heading in (
        "1. Why Version Control?", "2. Working with GitHub", "Appendix A — Command Cheat Sheet",
    ))


def test_ollama_detailed_summary_receives_more_context_than_chat(monkeypatch):
    from unittest.mock import Mock
    import httpx

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    provider = LLMProvider()
    monkeypatch.setattr(provider, "is_ollama_online", lambda: True)
    monkeypatch.setattr(provider, "get_effective_ollama_model", lambda: "qwen2.5:7b")
    post = Mock(return_value=httpx.Response(200, json={"response": '{"answer":"ok","citations":[]}'}))
    monkeypatch.setattr(httpx, "post", post)
    chunk = DocumentChunk(chunk_id="c", doc_id="d", doc_name="d", text="The TCP channel carries commands.")

    provider.generate_grounded_qa("Hãy mô tả chi tiết các phần chính.", [chunk], document_summary=True)

    options = post.call_args.kwargs["json"]["options"]
    assert options["num_ctx"] == 16384
    assert options["num_predict"] == 4096


@pytest.mark.parametrize('query', ['feat2', 'Tóm tắt tính năng 2', 'Hãy mô tả chi tiết giúp tôi'])
def test_numbered_feature_question_uses_only_its_section(query):
    from unittest.mock import Mock
    from backend.repositories.workspace_repository import WorkspaceRepository

    repo = WorkspaceRepository()
    pages = [
        '2.1.2 Feature 2 — Adaptive Revision . . . . . 9',
        'Feature 1 planner text\n2.1.2 Feature 2 — Adaptive Revision\nGrades verified quiz answers.',
        'Ranks topics by error rate.\n2.1.3 Feature 3 — Copilot\nFeature 3 chatbot text',
    ]
    repo.chunks = [DocumentChunk(chunk_id=str(page), doc_id='report.pdf', doc_name='report.pdf',
                                 page_number=page, start_line=1, end_line=len(text.splitlines()), text=text)
                   for page, text in enumerate(pages, 1)]
    provider = Mock()
    provider.generate_grounded_qa.return_value = []
    previous = 'feat2' if 'chi tiết' in query else 'Tóm tắt toàn bộ tài liệu'
    QAService(repository=repo, provider=provider).answer_question(
        query, selected_doc_ids=['report.pdf'], conversation_history=[{'role': 'user', 'content': previous}],
    )
    question, chunks = provider.generate_grounded_qa.call_args.args
    assert 'Tóm tắt toàn bộ tài liệu' not in question
    assert [(chunk.page_number, chunk.start_line) for chunk in chunks] == [(2, 2), (3, 1)]
    assert [chunk.text for chunk in chunks] == [
        '2.1.2 Feature 2 — Adaptive Revision\nGrades verified quiz answers.', 'Ranks topics by error rate.',
    ]
