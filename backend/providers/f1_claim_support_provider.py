"""Strict semantic protocol, explicit test double, and pinned offline CPU adapter."""
from dataclasses import dataclass
from typing import Protocol, Tuple
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
import threading

from backend.algorithms.f1_claim_support import AtomDecision, Evidence, SupportStatus


@dataclass(frozen=True)
class SemanticItem:
    claim_id: str
    text: str
    evidence_ids: Tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


@dataclass(frozen=True)
class SemanticRequest:
    context_id: str
    items: Tuple[SemanticItem, ...]
    evidence: Tuple[Evidence, ...]

    def __post_init__(self):
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "evidence", tuple(self.evidence))


class SemanticVerifier(Protocol):
    def verify(self, request: SemanticRequest) -> object:
        """Return an untrusted structured response; never an authorization token."""
        ...


class SemanticProtocolError(ValueError):
    pass


def validate_simulated_response(request: SemanticRequest, response: object) -> Tuple[AtomDecision, ...]:
    """Strict protocol validation, explicitly labelled as simulated semantics."""
    def invalid():
        raise SemanticProtocolError("INVALID_SEMANTIC_PROTOCOL")

    known = {e.evidence_id for e in request.evidence}
    if (not request.context_id or not request.items or len(known) != len(request.evidence)
            or any(e.context_id != request.context_id for e in request.evidence)
            or any(not i.claim_id or not i.text or not i.evidence_ids or not set(i.evidence_ids) <= known
                   or len(set(i.evidence_ids)) != len(i.evidence_ids) for i in request.items)):
        invalid()
    if (not isinstance(response, dict) or set(response) != {"context_id", "decisions"}
            or response["context_id"] != request.context_id or not isinstance(response["decisions"], list)):
        invalid()
    expected = {i.claim_id: i for i in request.items}
    if len(expected) != len(request.items) or len(response["decisions"]) != len(expected):
        invalid()
    seen, results = set(), {}
    labels = {"entailment": SupportStatus.SUPPORTED, "contradiction": SupportStatus.CONTRADICTED,
              "neutral": SupportStatus.INSUFFICIENT_EVIDENCE, "uncertain": SupportStatus.INSUFFICIENT_EVIDENCE}
    for row in response["decisions"]:
        if not isinstance(row, dict) or set(row) != {"claim_id", "context_id", "label", "evidence_ids"}:
            invalid()
        claim_id = row["claim_id"]
        if not isinstance(claim_id, str) or claim_id not in expected or claim_id in seen or row["context_id"] != request.context_id:
            invalid()
        if not isinstance(row["label"], str) or row["label"] not in labels:
            invalid()
        refs = row["evidence_ids"]
        if (not isinstance(refs, list) or any(not isinstance(i, str) for i in refs)
                or len(set(refs)) != len(refs) or not set(refs) <= set(expected[claim_id].evidence_ids)
                or (row["label"] in ("entailment", "contradiction") and not refs)):
            invalid()
        seen.add(claim_id)
        results[claim_id] = AtomDecision(claim_id, request.context_id, labels[row["label"]], tuple(refs),
                                        "simulated_semantic", "SIMULATED_" + row["label"].upper(), simulated=True)
    return tuple(results[i.claim_id] for i in request.items)


class ScriptedSemanticVerifier:
    """Test double: fixed scripted labels; never interprets source or claim text."""
    def __init__(self, mode="entailment", labels=()):
        self.mode, self.labels, self.calls = mode, tuple(labels), 0

    def verify(self, request: SemanticRequest) -> object:
        self.calls += 1
        if self.mode == "timeout":
            raise TimeoutError("simulated timeout")
        if self.mode == "exception":
            raise RuntimeError("simulated backend failure")
        if self.mode == "malformed":
            return "not a semantic response"
        if self.mode == "confidence_only":
            return {"confidence": 1.0}
        labels = dict(self.labels)
        default = self.mode if self.mode in ("entailment", "contradiction", "neutral", "uncertain") else "entailment"
        rows = [dict(claim_id=i.claim_id, context_id=request.context_id,
                     label=labels.get(i.claim_id, default), evidence_ids=list(i.evidence_ids)) for i in request.items]
        response = dict(context_id=request.context_id, decisions=rows)
        if self.mode == "unknown_claim": rows[0]["claim_id"] = "unknown"
        if self.mode == "missing_claim": rows.pop()
        if self.mode == "missing_id": rows[0].pop("claim_id")
        if self.mode == "duplicate_claim": rows.append(dict(rows[0]))
        if self.mode == "wrong_context": rows[0]["context_id"] = "other-request"
        if self.mode == "invalid_evidence": rows[0]["evidence_ids"] = ["unknown-evidence"]
        if self.mode == "unknown_label": rows[0]["label"] = "SUPPORTED"
        if self.mode == "confidence": rows[0]["confidence"] = 1.0
        return response


MODEL_ID = 'MoritzLaurer/mDeBERTa-v3-base-mnli-xnli'
MODEL_REVISION = '8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c'
QUALIFIED_VERSIONS = {'torch': '2.7.1+cpu', 'transformers': '4.57.1',
                      'tokenizers': '0.22.2', 'safetensors': '0.6.2', 'sentencepiece': '0.2.1'}
QUALIFIED_FILES = {
    'config.json': '4e4430c95100d613df80fa01276f231931e1b535557cf62fbb3cc50323e50cca',
    'model.safetensors': '65af59b1ff4450b09ecbf13ca35c840dbf038b26ff8e10e5ea89ca724828ed1e',
    'spm.model': '13c8d666d62a7bc4ac8f040aab68e942c861f93303156cc28f5c7e885d86d6e3',
    'tokenizer_config.json': 'df9fd3a4482cc4a866788244824573fab8e74dadd1609d4f0e5997f9e96921dc',
    'special_tokens_map.json': '9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9',
}


def validate_local_response(request, response):
    # Same strict ID/reference protocol; validation does not authorize acceptance.
    return tuple(replace(d, method='qualified_local_nli', simulated=False,
                         reason_code=d.reason_code.replace('SIMULATED_', 'LOCAL_NLI_'))
                 for d in validate_simulated_response(request, response))


class QualifiedLocalNLI:
    """Pinned local-only CPU adapter. No downloads, cloud, or favorable fallback.

    F1_NLI_MODEL_PATH must explicitly name the already-qualified snapshot.
    A single bounded worker reuses the model and prevents queues after timeouts.
    A timed-out CPU operation may finish in that worker; its result is discarded.
    """
    def __init__(self, model_path=None, timeout_seconds=10.0):
        self.model_path = model_path if model_path is not None else os.environ.get('F1_NLI_MODEL_PATH', '')
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('INVALID_VERIFIER_DEADLINE')
        self.timeout_seconds = timeout_seconds
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='f1-nli')
        self._busy = threading.Lock()
        self._model = self._tokenizer = None

    def _load(self):
        if self._model is not None:
            return
        path = Path(self.model_path)
        if not self.model_path or path.name != MODEL_REVISION:
            raise RuntimeError('QUALIFIED_MODEL_UNAVAILABLE')
        for name, expected in QUALIFIED_FILES.items():
            digest = hashlib.sha256()
            with (path / name).open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise RuntimeError('QUALIFIED_MODEL_HASH_MISMATCH')
        for package, version in QUALIFIED_VERSIONS.items():
            if importlib.metadata.version(package) != version:
                raise RuntimeError('UNQUALIFIED_DEPENDENCY_VERSION')
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True,
                                                  trust_remote_code=False, use_fast=False)
        model, info = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True,
            trust_remote_code=False, use_safetensors=True, output_loading_info=True)
        expected = {0: 'entailment', 1: 'neutral', 2: 'contradiction'}
        if ({int(k): v for k, v in model.config.id2label.items()} != expected or
                model.config.label2id != {v: k for k, v in expected.items()} or
                any(info.get(k) for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs'))):
            raise RuntimeError('INVALID_QUALIFIED_MODEL_CONFIGURATION')
        model.to(device='cpu', dtype=torch.float32).eval()
        self._tokenizer, self._model = tokenizer, model

    def _infer(self, request):
        self._load()
        import torch
        evidence = {e.evidence_id: e for e in request.evidence}
        rows = []
        for item in request.items:
            # Only the citations bound to this assertion, never the whole context.
            premise = '\n'.join(evidence[i].text for i in item.evidence_ids)
            tokens = self._tokenizer(premise, item.text, return_tensors='pt', truncation=False)
            limit = min(self._model.config.max_position_embeddings, self._tokenizer.model_max_length)
            if tokens['input_ids'].shape[1] > limit:
                raise ValueError('VERIFIER_CONTEXT_OVERFLOW')
            with torch.inference_mode():
                logits = self._model(**tokens).logits
            if tuple(logits.shape) != (1, 3) or not torch.isfinite(logits).all().item():
                raise SemanticProtocolError('INVALID_MODEL_RESULT')
            label = self._model.config.id2label[int(logits.argmax(dim=-1).item())]
            rows.append(dict(claim_id=item.claim_id, context_id=request.context_id,
                             label=label, evidence_ids=list(item.evidence_ids)))
        return dict(context_id=request.context_id, decisions=rows)

    def warmup(self):
        """Bounded startup forward pass on the same CPU model/worker.

        Startup may hash/load the qualified artifact for up to 60 seconds;
        the per-request verification deadline remains unchanged.
        """
        from backend.algorithms.f1_claim_support import fingerprint
        text = "The local verifier is ready."
        evidence = Evidence("f1-startup", "health", "health", "v1",
            fingerprint(text), 1, 1, 1, text, fingerprint(text))
        request = SemanticRequest("f1-startup",
            (SemanticItem("health", text, ("health",)),), (evidence,))
        return self._execute(request, 60.0)

    def verify(self, request):
        return self._execute(request, self.timeout_seconds)

    def _execute(self, request, deadline):
        # Validate caller IDs before inference (without inventing a model verdict).
        probe = dict(context_id=request.context_id, decisions=[dict(claim_id=i.claim_id,
            context_id=request.context_id, label='neutral', evidence_ids=list(i.evidence_ids)) for i in request.items])
        validate_local_response(request, probe)
        if not self._busy.acquire(blocking=False):
            raise TimeoutError('VERIFIER_BUSY')
        try:
            future = self._worker.submit(self._infer, request)
        except BaseException:
            self._busy.release()
            raise
        future.add_done_callback(lambda _: self._busy.release())
        response = future.result(timeout=deadline)
        validate_local_response(request, response)
        return response


@lru_cache(maxsize=1)
def get_f1_semantic_verifier():
    return QualifiedLocalNLI()
