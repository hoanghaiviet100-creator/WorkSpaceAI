"""SIMULATED Ollama protocol checks; no model or embedding inference."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from types import SimpleNamespace

import httpx
import pytest

from backend.core.config import settings
from backend.core.schemas import DocumentChunk
from backend.providers.llm_provider import GenerationError, LLMProvider
from backend.providers.prompts import build_qa_prompt, build_summary_prompt
from backend.services.runtime_service import RuntimeService
from benchmarks.f1_latency import observer

MODEL = "qwen3.5:9b-q4_K_M"
F3_MODEL = "qwen2.5:7b"
TEXT = "TCP provides reliable and ordered delivery of data between devices."
PRIVATE = "SIMULATED_NATIVE_REASONING_NOT_PUBLIC"


def final_answer(explanation="The quoted source describes reliable TCP delivery."):
    return {"thinking": explanation, "answer": TEXT, "citations": [
        {"claim": TEXT, "evidence_id": "REQUEST_EVIDENCE_1", "excerpt": TEXT},
    ]}


@pytest.fixture
def f1(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_model", F3_MODEL)
    monkeypatch.setattr(settings, "f1_generation_model", MODEL)
    monkeypatch.setattr(settings, "f1_generation_think", True)
    monkeypatch.setattr(settings, "ollama_base_url", "http://f1-model.invalid:11434")
    state = SimpleNamespace(provider=LLMProvider(), calls=[], tags=[MODEL, F3_MODEL, "qwen3-embedding:0.6b"],
                            envelope={"model": MODEL, "done": True, "response": json.dumps(final_answer()),
                                      "thinking": PRIVATE})
    state.chunk = DocumentChunk(chunk_id="tcp-1", doc_id="tcp.txt", doc_name="tcp.txt",
                                text=TEXT, doc_hash="simulated-document-hash")

    def get(url, **kwargs):
        state.calls.append(("GET", url, kwargs))
        return httpx.Response(200, json={"models": [{"name": tag} for tag in state.tags]},
                              request=httpx.Request("GET", url))

    def post(url, **kwargs):
        state.calls.append(("POST", url, kwargs))
        envelope = dict(state.envelope)
        if kwargs["json"].get("format") == "json" and isinstance(envelope.get("response"), str):
            eid = re.search(r"=== EVIDENCE_ID: (ev_[0-9a-f]{16}_\d+) ===", kwargs["json"]["prompt"]).group(1)
            envelope["response"] = envelope["response"].replace("REQUEST_EVIDENCE_1", eid)
        return httpx.Response(200, json=envelope, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "post", post)
    return state


@pytest.mark.parametrize("think", [True, False])
@pytest.mark.parametrize("operation", ["qa", "summary"])
def test_native_thinking_uses_exact_f1_payload_and_only_final_response(f1, operation, caplog, monkeypatch, think):
    monkeypatch.setattr(settings, "f1_generation_think", think)
    if not think:
        f1.envelope.pop("thinking", None)
    if operation == "qa":
        result = f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])
        public = json.dumps([claim.model_dump() for claim in result])
        assert result[0].thinking == final_answer()["thinking"]
    else:
        f1.envelope["response"] = "### TCP summary\n\n" + TEXT
        result = f1.provider.generate_summary("tcp.txt", [f1.chunk])
        public = result
        assert result == f1.envelope["response"]
    assert PRIVATE not in public and PRIVATE not in caplog.text
    assert not vars(f1.provider), "No response/reasoning state may survive on the provider"
    posts = [call for call in f1.calls if call[0] == "POST"]
    assert len(posts) == 1
    _, url, kwargs = posts[0]
    assert url == "http://f1-model.invalid:11434/api/generate"
    payload = kwargs["json"]
    assert payload["model"] == MODEL and payload["think"] is think and payload["stream"] is False
    assert payload["options"] == {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.1, "top_p": 0.85, "repeat_penalty": 1.1}
    assert kwargs["timeout"].read == 150.0 and kwargs["timeout"].connect == 3.0
    assert payload.get("format") == ("json" if operation == "qa" else None)
    assert "reasoning_effort" not in payload and "response_format" not in payload
    assert settings.ollama_model == F3_MODEL


@pytest.mark.parametrize("final", ["{", "", "<think>private</think>" + json.dumps(final_answer()),
                                   chr(96) * 3 + "json\n" + json.dumps(final_answer()) + "\n" + chr(96) * 3])
def test_native_reasoning_cannot_reconstruct_invalid_final_json(f1, final):
    f1.envelope.update(response=final, thinking=json.dumps(final_answer()))
    with pytest.raises(GenerationError, match="^GENERATION_INVALID_RESPONSE$"):
        f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])
    assert not vars(f1.provider)


@pytest.mark.parametrize("tags", [[F3_MODEL], ["qwen3-embedding:0.6b"], ["qwen3.5:9b"],
                                  ["qwen3.5:9b-q8_0"], []])
def test_nearby_or_legacy_tags_never_substitute_for_f1(f1, tags):
    f1.tags = tags
    with pytest.raises(GenerationError, match="^GENERATION_MODEL_MISSING$"):
        f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])
    assert not [call for call in f1.calls if call[0] == "POST"]


@pytest.mark.parametrize("flag", [None, "true", "false", 1, 0])
def test_non_boolean_thinking_fails_before_generation(f1, monkeypatch, flag):
    monkeypatch.setattr(settings, "f1_generation_think", flag)
    with pytest.raises(GenerationError, match="^GENERATION_INVALID_CONFIG$"):
        f1.provider.generate_summary("tcp.txt", [f1.chunk])
    assert not f1.calls


def test_legacy_f3_payload_is_unchanged_and_uses_old_model(f1):
    f1.envelope["response"] = "SUBJECT: Existing subject\nBODY: Existing body"
    result = f1.provider.generate_email_draft("Progress update", [f1.chunk], "review@example.com")
    assert result == ("Existing subject", "Existing body")
    payload = next(call[2]["json"] for call in f1.calls if call[0] == "POST")
    assert payload["model"] == F3_MODEL and payload["stream"] is False
    assert "think" not in payload and "format" not in payload
    assert payload["options"] == {"num_ctx": 4096, "temperature": 0.1, "top_p": 0.85, "repeat_penalty": 1.1}
    assert "reasoning_effort" not in payload and "response_format" not in payload
    assert not vars(f1.provider)


def test_runtime_reports_f1_model_without_reconfiguring_f3(f1):
    status = RuntimeService().get_status()
    assert status["model"] == MODEL and status["model_options"][0] == MODEL
    assert status["provider_options"][0]["model"] == MODEL
    assert settings.ollama_model == F3_MODEL
    assert settings.ollama_embed_model == "qwen3-embedding:0.6b"


def test_prompts_keep_explanation_contract_separate_from_native_reasoning(f1):
    prompt = build_qa_prompt("Explain TCP", [f1.chunk], evidence_ids=["ev_0000000000000000_1"])
    assert '"thinking"' in prompt and '"answer"' in prompt and '"citations"' in prompt
    assert "Không đưa suy luận nội bộ" in prompt
    assert "<untrusted_document_data>" in prompt and "[Dòng 1]" in prompt
    for name in ("network_lecture.txt", "project_brief.txt", "notes.txt"):
        summary = build_summary_prompt(name, [f1.chunk])
        assert "<untrusted_document_data>" in summary and "#### 1." in summary


@pytest.mark.parametrize("env_flag,enabled", [(None, True), ("true", True), ("false", False), ("invalid", None)])
def test_f1_environment_defaults_do_not_change_legacy_or_embedding_model(env_flag, enabled):
    env = dict(os.environ)
    env.pop("F1_GENERATION_MODEL", None)
    env.pop("F1_GENERATION_THINK", None)
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1", OLLAMA_MODEL=F3_MODEL,
               OLLAMA_EMBED_MODEL="qwen3-embedding:0.6b")
    if env_flag is not None:
        env["F1_GENERATION_THINK"] = env_flag
    code = ("import json; from backend.core.config import settings as s; "
            "print(json.dumps([s.f1_generation_model,s.f1_generation_think,s.ollama_model,s.ollama_embed_model]))")
    run = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
                         env=env, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [MODEL, enabled, F3_MODEL, "qwen3-embedding:0.6b"]


def test_concurrent_provider_and_observer_metadata_are_request_local(f1, monkeypatch):
    barrier = Barrier(2)
    native = {"alpha": "SIMULATED_PRIVATE_ALPHA", "beta": "SIMULATED_PRIVATE_BETA_LONGER"}

    def post(url, **kwargs):
        request_id = "alpha" if "alpha" in kwargs["json"]["prompt"] else "beta"
        barrier.wait(timeout=5)
        return httpx.Response(200, json={"model": MODEL, "done": True,
                              "thinking": native[request_id],
                              "response": json.dumps(final_answer("Public explanation " + request_id)).replace(
                                  "REQUEST_EVIDENCE_1", re.search(r"=== EVIDENCE_ID: (ev_[0-9a-f]{16}_\d+) ===", kwargs["json"]["prompt"]).group(1))},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", observer.observed_post(post))

    def worker(request_id):
        trace = {"clock": observer.perf_counter(), "spans": [], "request_id": request_id}
        token = observer.CURRENT.set(trace)
        try:
            claims = f1.provider.generate_grounded_qa(request_id, [f1.chunk])
            return request_id, claims, trace
        finally:
            observer.CURRENT.reset(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ["alpha", "beta"]))
    for request_id, claims, trace in results:
        assert claims[0].thinking == "Public explanation " + request_id
        span, = trace["spans"]
        assert span["model"] == MODEL and span["requested_think"] is True
        assert span["output_format"] == "json" and span["thinking_present"] is True
        assert span["thinking_length"] == len(native[request_id])
        serialized = json.dumps({"trace": trace, "claims": [c.model_dump() for c in claims]})
        assert all(reasoning not in serialized for reasoning in native.values())
    assert not vars(f1.provider)
    assert observer.CURRENT.get() is None


@pytest.mark.parametrize("operation", ["qa", "summary"])
@pytest.mark.parametrize("reason", ["length", "max_tokens", "context_length", "truncated"])
def test_fix01_explicit_truncation_rejects_complete_nonempty_output(f1, operation, reason):
    f1.envelope["done_reason"] = reason
    if operation == "summary":
        f1.envelope["response"] = "### Summary\n\n" + TEXT
    with pytest.raises(GenerationError, match="^GENERATION_INVALID_RESPONSE$"):
        if operation == "qa":
            f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])
        else:
            f1.provider.generate_summary("tcp.txt", [f1.chunk])
    assert len([call for call in f1.calls if call[0] == "POST"]) == 1
    assert not vars(f1.provider)


@pytest.mark.parametrize("operation", ["qa", "summary"])
@pytest.mark.parametrize("reason", [None, "stop"])
def test_fix01_omitted_or_normal_done_reason_remains_compatible(f1, operation, reason):
    if reason is not None:
        f1.envelope["done_reason"] = reason
    if operation == "qa":
        assert f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])[0].claim_text == TEXT
    else:
        f1.envelope["response"] = TEXT
        assert f1.provider.generate_summary("tcp.txt", [f1.chunk]) == TEXT


@pytest.mark.parametrize("operation", ["qa", "summary"])
@pytest.mark.parametrize("markup", [
    "<think>SIMULATED_PRIVATE</think>", "<think>SIMULATED_UNCLOSED",
    "SIMULATED_ORPHAN</think>", '<THINK class="native">SIMULATED_PRIVATE</THINK>',
    "<thinking>SIMULATED_PRIVATE</thinking>", "< think >SIMULATED_PRIVATE</ think >", "<think",
])
def test_fix01_inline_native_markup_is_rejected_without_repair(f1, operation, markup):
    if operation == "qa":
        f1.envelope["response"] = json.dumps(final_answer("Source explanation " + markup))
    else:
        f1.envelope["response"] = "### Summary\n\n" + TEXT + "\n" + markup
    with pytest.raises(GenerationError, match="^GENERATION_INVALID_RESPONSE$"):
        if operation == "qa":
            f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])
        else:
            f1.provider.generate_summary("tcp.txt", [f1.chunk])
    assert not vars(f1.provider)


@pytest.mark.parametrize("field", ["answer", "thinking", "excerpt"])
def test_fix01_json_escaped_inline_native_markup_cannot_escape_validation(f1, field):
    payload = final_answer()
    text = "<think>SIMULATED_PRIVATE</think>"
    if field == "excerpt":
        payload["citations"][0][field] = text
    else:
        payload[field] = text
    f1.envelope["response"] = json.dumps(payload).replace("<", "\\u003c").replace(">", "\\u003e")
    with pytest.raises(GenerationError, match="^GENERATION_INVALID_RESPONSE$"):
        f1.provider.generate_grounded_qa("How does TCP deliver data?", [f1.chunk])


@pytest.mark.parametrize("operation", ["qa", "summary"])
def test_fix01_unrelated_tag_names_are_not_native_thinking_markup(f1, operation):
    explanation = "The document uses <thinker> as an example element."
    if operation == "qa":
        f1.envelope["response"] = json.dumps(final_answer(explanation))
        assert f1.provider.generate_grounded_qa("Explain TCP", [f1.chunk])[0].thinking == explanation
    else:
        f1.envelope["response"] = explanation
        assert f1.provider.generate_summary("tcp.txt", [f1.chunk]) == explanation


def test_fix01_f3_transport_keeps_legacy_text_and_completion_behavior(f1):
    legacy = "<think>SIMULATED_LEGACY_TEXT</think>\nSUBJECT: Existing\nBODY: Existing body"
    f1.envelope.update(done_reason="length", response=legacy)
    assert f1.provider.call_ollama("Legacy F3 prompt") == legacy
    payload = next(call[2]["json"] for call in f1.calls if call[0] == "POST")
    assert payload["model"] == F3_MODEL and "think" not in payload


def test_fix01_embedded_verifier_blocks_network_and_supports_stdlib_socketpair():
    import ast
    import re

    root = Path(__file__).resolve().parents[1]
    verifier = (root / "deploy/f1/verify.ps1").read_text(encoding="utf-8")
    runner = re.search(r"\$f1Code\s*=\s*@'\n(.*?)\n'@", verifier, re.DOTALL).group(1)
    bootstrap = next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(runner))
                     if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bootstrap" for t in node.targets))
    guard = bootstrap.split("import pytest\n", 1)[0]
    # The first assertions fail before any socket operation if a guard is absent.
    checks = '''
import asyncio
import smtplib
from types import SimpleNamespace
assert socket.socket.connect.__name__ == "guarded_connect"
assert socket.socket.connect_ex.__name__ == "guarded_connect_ex"
assert socket.create_connection is blocked
assert smtplib.SMTP.connect is blocked and smtplib.SMTP_SSL.connect is blocked
assert httpx.HTTPTransport.handle_request is blocked
def expect_blocked(call):
    try:
        call()
    except AssertionError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("Network guard did not reject operation")
fake = SimpleNamespace(family=socket.AF_INET)
expect_blocked(lambda: guarded_connect(fake, ("127.0.0.1", 11434)))
expect_blocked(lambda: guarded_connect_ex(fake, ("127.0.0.1", 11434)))
expect_blocked(lambda: socket.create_connection(("127.0.0.1", 11434)))
expect_blocked(lambda: smtplib.SMTP.connect(None, "unit.invalid", 587))
expect_blocked(lambda: smtplib.SMTP_SSL.connect(None, "unit.invalid", 465))
expect_blocked(lambda: httpx.HTTPTransport.handle_request(None, None))
expect_blocked(lambda: asyncio.run(httpx.AsyncHTTPTransport.handle_async_request(None, None)))
left, right = socket.socketpair()
left.close()
right.close()
print("OFFLINE_GUARD_AND_SOCKETPAIR_PASS")
'''
    run = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", guard + checks], cwd=root,
                         capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "OFFLINE_GUARD_AND_SOCKETPAIR_PASS" in run.stdout


@pytest.mark.parametrize("ctx,budget", [(8192,0),(8192,-1),(4096,4096),(8192,8192),(True,4096),(8192,True),(8192,"4096")])
def test_m3_final_invalid_generation_budget_fails_before_transport(f1, monkeypatch, ctx, budget):
    monkeypatch.setattr(settings,"f1_generation_num_ctx",ctx)
    monkeypatch.setattr(settings,"f1_generation_num_predict",budget)
    with pytest.raises(GenerationError,match="^GENERATION_INVALID_CONFIG$"):
        f1.provider.generate_grounded_qa("Explain TCP",[f1.chunk])
    assert not f1.calls


def test_thinking_off_rejects_unexpected_native_reasoning(f1, monkeypatch):
    monkeypatch.setattr(settings,"f1_generation_think",False)
    with pytest.raises(GenerationError,match="^GENERATION_INVALID_RESPONSE$"):
        f1.provider.generate_grounded_qa("Explain TCP",[f1.chunk])
    assert not vars(f1.provider)


def test_open_r5_partial_compound_from_compact_trial_must_abstain():
    """Offline replay of the PUBLIC proposal, not a runtime-inference claim.

    Exact query, source and partial claim from reviewed compact-prompt evidence.
    This must stay red until whole-request coverage is enforced; rollback is not
    a resolution and the expected abstention must not be changed to verified.
    """
    from backend.core.schemas import GeneratedClaim
    from backend.services.qa_service import QAService
    text="Report T requires exactly 7 pages."
    digest="e0452e70bed9e1f3943c27f1d449374e7f1d87e8de5d5129f700e28b5a557cba"
    chunk=DocumentChunk(chunk_id="M3-Numeric.pdf_p1_c0",doc_id="M3-Numeric.pdf",doc_name="M3-Numeric.pdf",
        text=text,page_number=1,start_line=1,end_line=1,doc_version="v1",doc_hash=digest,score=1.0)
    claim=GeneratedClaim(claim_text="Report T requires exactly 7 pages",cited_doc_id=chunk.doc_id,cited_page=1,
        cited_start_line=1,cited_end_line=1,evidence_quote=text,doc_version="v1",doc_hash=digest)
    repo=SimpleNamespace(chunks=[chunk],dense_available=False,search=lambda *a,**kw:[chunk])
    provider=SimpleNamespace(generate_grounded_qa=lambda *a,**kw:[claim])
    qa=QAService(repository=repo,provider=provider,embed_provider=SimpleNamespace(get_embed_fn=lambda:None))
    result=qa.answer_question('Is the complete statement "T requires 7 pages and T is approved" supported? If not, provide no supported assertion for the complete statement.',selected_doc_ids=[chunk.doc_id])
    assert result["status"]=="ABSTAINED_INSUFFICIENT_EVIDENCE"
    assert not result["validated_claims"]


def _offline_coverage_result(source, output, question):
    """Fixed untrusted proposal; real F1 citation/support/controller path."""
    import hashlib
    from backend.core.schemas import GeneratedClaim
    from backend.services.qa_service import QAService
    digest=hashlib.sha256(source.encode()).hexdigest()
    chunk=DocumentChunk(chunk_id="coverage:1",doc_id="coverage.txt",doc_name="coverage.txt",text=source,
        page_number=1,start_line=1,end_line=1,doc_version="v1",doc_hash=digest,score=1.0)
    claim=GeneratedClaim(claim_text=output,cited_doc_id=chunk.doc_id,cited_page=1,cited_start_line=1,
        cited_end_line=1,evidence_quote=source,doc_version="v1",doc_hash=digest)
    repo=SimpleNamespace(chunks=[chunk],dense_available=False,search=lambda *a,**kw:[chunk])
    qa=QAService(repository=repo,provider=SimpleNamespace(generate_grounded_qa=lambda *a,**kw:[claim]),
        embed_provider=SimpleNamespace(get_embed_fn=lambda:None))
    return qa.answer_question(question,selected_doc_ids=[chunk.doc_id])


@pytest.mark.parametrize("question",[
    'Evaluate "V has a mass of 5 mg and Z is approved".',
    'Kiểm chứng “V has a mass of 5 mg and Z is approved”.',
    'V has a mass of 5 mg and Z is approved?',
    'Compare "V has a mass of 5 mg" and "Z is approved".',
])
def test_r5_incomplete_compound_rejected_without_fixture_markers(question):
    result=_offline_coverage_result('Sample V has a mass of 5 mg.','V has a mass of 5 mg.',question)
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE'
    assert result['validated_claims']==[] and result['grounding_score']==0


@pytest.mark.parametrize("question",[
    'Evaluate "V has a mass of 5 mg and W requires 9 pages".',
    'V has a mass of 5 mg and W requires 9 pages?',
])
def test_r5_complete_supported_compound_still_answers(question):
    result=_offline_coverage_result('Sample V has a mass of 5 mg. Report W requires exactly 9 pages.',
        'V has a mass of 5 mg. and W requires 9 pages.',question)
    assert result['status']=='ANSWER_VERIFIED' and result['validated_claims']


@pytest.mark.parametrize("question",['What is the mass of V?','Give the fact "V has a mass of 5 mg".'])
def test_r5_simple_atomic_questions_not_over_abstained(question):
    result=_offline_coverage_result('Sample V has a mass of 5 mg.','V has a mass of 5 mg.',question)
    assert result['status']=='ANSWER_VERIFIED' and result['validated_claims']
