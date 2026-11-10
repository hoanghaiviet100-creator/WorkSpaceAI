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

from backend.services.qa_service import expand_contextual_query, is_detail_followup, QAService

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

@pytest.mark.parametrize('query', ['Mô tả chi tiết HTTP và HTTPS', 'Giải thích chi tiết thư viện asyncio', 'Hạn nộp báo cáo là ngày nào?'])
def test_new_subject_is_not_replaced(query):
    assert not is_detail_followup(query)
    assert expand_contextual_query(query, [{'role': 'user', 'content': 'Socket là gì?'}]) == query

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
    provider = LLMProvider()
    monkeypatch.setattr(provider, 'is_ollama_online', lambda: True)
    monkeypatch.setattr(provider, 'get_effective_ollama_model', lambda: 'qwen2.5:7b')
    captured = {}
    def post(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {'response': 'ok'})
    monkeypatch.setattr(provider_module.httpx, 'post', post)
    provider.call_ollama(build_qa_prompt(query, [DocumentChunk(chunk_id="c", doc_id="d", doc_name="d", text="Socket source")]), enforce_json=True)
    assert captured['json']['options']['num_predict'] == budget
    assert captured['json']['options']['num_ctx'] == 4096
    assert captured['json']['options']['num_thread'] == 4
