"""Unit & integration tests for Feature 1 Ollama optimizations and CPU FastEmbed retrieval."""
from __future__ import annotations

from unittest.mock import patch
import numpy as np
import pytest

from backend.core.config import settings
from backend.core.schemas import DocumentChunk, DocumentMetadata
from backend.providers.embedding_provider import EmbeddingProvider
from backend.providers.llm_provider import LLMProvider
from backend.providers.prompts import build_qa_prompt, build_system_prompt_for_chunks
from backend.repositories.workspace_repository import WorkspaceRepository


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_ollama_tags_cache_and_invalidation(monkeypatch):
    provider = LLMProvider()
    monkeypatch.setattr(settings, "ollama_tags_cache_ttl", 60.0)
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_keep_alive", "30m")
    monkeypatch.setattr(settings, "ollama_num_ctx", 3072)
    monkeypatch.setattr(settings, "ollama_num_predict", 900)

    get_calls = []
    post_payloads = []
    post_status = {"code": 200}

    def fake_get(url, timeout=None):
        get_calls.append(url)
        return _DummyResponse(200, {"models": [{"name": "qwen2.5:7b"}]})

    def fake_post(url, json=None, timeout=None):
        post_payloads.append((url, json))
        if post_status["code"] != 200:
            return _DummyResponse(post_status["code"], {})
        return _DummyResponse(200, {"response": '{"answer": "ok", "citations": []}'})

    with patch("backend.providers.llm_provider.httpx.get", side_effect=fake_get), patch(
        "backend.providers.llm_provider.httpx.post", side_effect=fake_post
    ):
        assert provider.is_ollama_online() is True
        assert provider.get_effective_ollama_model() == "qwen2.5:7b"
        out = provider.call_ollama("test prompt", enforce_json=True)
        assert out == '{"answer": "ok", "citations": []}'
        assert len(get_calls) == 1

        payload = post_payloads[0][1]
        assert payload["stream"] is False
        assert payload["keep_alive"] == "30m"
        assert payload["format"] == "json"
        assert payload["options"]["num_ctx"] == 3072
        assert payload["options"]["num_predict"] == 900

        # Error on /api/generate must invalidate /api/tags cache
        post_status["code"] = 500
        assert provider.call_ollama("fail prompt") is None
        assert provider.is_ollama_online() is True
        assert len(get_calls) == 2


def test_prompt_thinking_is_concise_and_toggleable():
    chunk = DocumentChunk(
        chunk_id="c1",
        doc_id="Doc.pdf",
        doc_name="Doc.pdf",
        page_number=1,
        start_line=1,
        end_line=2,
        text="Line 1\nLine 2",
        doc_version="v1",
        doc_hash="h1",
    )
    with_thinking = build_system_prompt_for_chunks([chunk], include_thinking=True)
    assert '"thinking":' in with_thinking
    assert "1–2 câu" in with_thinking

    without_thinking = build_system_prompt_for_chunks([chunk], include_thinking=False)
    assert '"thinking":' not in without_thinking
    assert '"answer":' in without_thinking
    assert '"citations":' in without_thinking

    qa_prompt = build_qa_prompt("Câu hỏi?", [chunk])
    assert "<untrusted_document_data>" in qa_prompt


def test_embedding_provider_e5_prefixes_and_hash_fallback(monkeypatch):
    seen_inputs = []

    class _FakeFastEmbedModel:
        def embed(self, texts):
            seen_inputs.extend(texts)
            vecs = []
            for t in texts:
                if "nộp" in t or "submission" in t.lower():
                    vecs.append(np.array([1.0, 0.2, 0.0, 0.0], dtype=np.float32))
                else:
                    vecs.append(np.array([0.0, 0.0, 1.0, 0.2], dtype=np.float32))
            return vecs

    provider = EmbeddingProvider(fastembed_model="intfloat/multilingual-e5-small")

    def fake_try_load():
        provider._fastembed_model = _FakeFastEmbedModel()
        return True

    monkeypatch.setattr(settings, "embedding_backend", "auto")
    monkeypatch.setattr(provider, "_try_load_fastembed", fake_try_load)

    embed_fn = provider.get_embed_fn()
    q_vecs = embed_fn.embed_queries(["Hạn nộp bài?"])
    p_vecs = embed_fn.embed_passages(["Submission deadline is Friday", "Unrelated docker notes"])

    assert seen_inputs[0] == "query: Hạn nộp bài?"
    assert seen_inputs[1] == "passage: Submission deadline is Friday"
    assert seen_inputs[2] == "passage: Unrelated docker notes"
    assert q_vecs.shape == (1, 4)
    assert p_vecs.shape == (2, 4)
    assert embed_fn.score_floor == 0.70

    # Hash fallback remains deterministic when requested or offline without cache
    monkeypatch.setattr(settings, "embedding_backend", "hash")
    fallback_provider = EmbeddingProvider()
    fallback_fn = fallback_provider.get_embed_fn()
    vecs = fallback_fn.embed_queries(["Kiểm tra fallback offline"])
    assert fallback_provider.using_hash_fallback is True
    assert fallback_fn.score_floor == 0.0
    assert vecs.shape == (1, 384)


def test_workspace_repository_uses_query_passage_and_score_floor(monkeypatch):
    seen = []

    class _FakeRepoEmbed:
        score_floor = 0.70

        def embed_queries(self, texts):
            seen.append(("q", texts))
            return np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

        def embed_passages(self, texts):
            seen.append(("p", texts))
            out = []
            for t in texts:
                if "deadline" in t.lower():
                    out.append(np.array([0.85, 0.52678, 0.0], dtype=np.float32))
                else:
                    out.append(np.array([0.65, 0.75993, 0.0], dtype=np.float32))
            return np.asarray(out, dtype=np.float32)

        def __call__(self, texts):
            return self.embed_passages(texts)

    repo = WorkspaceRepository(embed_fn=_FakeRepoEmbed())
    meta = DocumentMetadata(
        doc_id="Doc.txt",
        doc_name="Doc.txt",
        file_type="txt",
        page_count=1,
        chunk_count=2,
        total_lines=2,
        file_hash="abc123",
    )
    chunks = [
        DocumentChunk(
            chunk_id="c_rel",
            doc_id="Doc.txt",
            doc_name="Doc.txt",
            page_number=1,
            start_line=1,
            end_line=1,
            text="Submission deadline is Oct 24.",
            doc_version="v1",
            doc_hash="abc123",
        ),
        DocumentChunk(
            chunk_id="c_irr",
            doc_id="Doc.txt",
            doc_name="Doc.txt",
            page_number=1,
            start_line=2,
            end_line=2,
            text="Bánh mì Sài Gòn.",
            doc_version="v1",
            doc_hash="abc123",
        ),
    ]
    repo.add_document(meta, chunks)
    results = repo.search("Khi nào nộp bài?", top_k=2)

    assert seen[0][0] == "q"
    assert seen[1][0] == "p"
    assert results[0].chunk_id == "c_rel"
    # raw sim 0.85 calibrated with floor 0.70 -> (0.85 - 0.70)/0.30 = 0.50
    assert results[0].dense_score == pytest.approx(0.5, abs=0.01)
    # raw sim 0.65 calibrated with floor 0.70 -> 0.0
    assert results[1].dense_score == 0.0


def test_real_cached_fastembed_multilingual_e5_small_if_present(monkeypatch):
    monkeypatch.setattr(settings, "embedding_backend", "fastembed")
    provider = EmbeddingProvider(fastembed_model="intfloat/multilingual-e5-small")
    provider.load_model()
    if not provider.using_fastembed:
        pytest.skip("Local FastEmbed cache not present in offline test environment.")

    embed_fn = provider.get_embed_fn()
    q = embed_fn.embed_queries(["Hạn nộp bài cuối kỳ là khi nào?"])[0]
    passages = embed_fn.embed_passages(
        [
            "Thời hạn bàn giao đồ án môn học vào ngày 24/10/2026 trên LMS.",
            "Công thức nấu phở bò truyền thống Hà Nội.",
        ]
    )
    assert float(np.dot(q, passages[0])) > float(np.dot(q, passages[1]))
