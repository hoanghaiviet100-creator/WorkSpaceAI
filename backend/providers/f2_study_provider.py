"""Shared evidence framing and bounded Ollama JSON transport for F2 study."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json

import httpx

from backend.core.f2_study_schemas import SourceRef


MAX_STUDY_RESPONSE_BYTES = 1_000_000


@dataclass(frozen=True)
class StudyEvidence:
    source_id: str
    kind: str
    source_ref: SourceRef


class StudyProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def format_study_evidence(evidence: tuple[StudyEvidence, ...]) -> str:
    """Frame verbatim source text as escaped, line-labelled untrusted data."""
    blocks = []
    for item in evidence:
        ref = item.source_ref
        lines = "\n".join(
            f"[Dòng {ref.start_line + index}] {escape(line, quote=False)}"
            for index, line in enumerate(ref.evidence_quote.splitlines())
        )
        blocks.append(
            f'<untrusted_document_data source_id="{escape(item.source_id, quote=True)}" '
            f'doc_id="{escape(ref.doc_id, quote=True)}" page="{ref.page_number}" '
            f'lines="{ref.start_line}-{ref.end_line}" kind="{escape(item.kind, quote=True)}">\n'
            f"{lines}\n</untrusted_document_data>"
        )
    return "\n".join(blocks)


class OllamaStudyProvider:
    """Common transport; no network request until generate_from_prompt runs."""

    name = "ollama"

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b",
        *, transport: httpx.BaseTransport | None = None,
    ):
        url = httpx.URL(base_url)
        if url.scheme not in ("http", "https") or not url.host or url.query or url.fragment or url.userinfo:
            raise ValueError("expected a server-configured HTTP(S) Ollama base URL")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be blank")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transport = transport

    def generate_from_prompt(self, prompt: str) -> str:
        payload = {
            "model": self.model, "prompt": prompt, "stream": False, "format": "json",
            "options": {"num_ctx": 8192, "temperature": 0.1, "top_p": 0.85, "repeat_penalty": 1.1},
        }
        try:
            with httpx.Client(
                timeout=httpx.Timeout(60.0, connect=2.0), transport=self.transport,
                follow_redirects=False,
            ) as client:
                with client.stream("POST", self.base_url + "/api/generate", json=payload) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for part in response.iter_bytes():
                        if len(body) + len(part) > MAX_STUDY_RESPONSE_BYTES:
                            raise StudyProviderError("PROVIDER_RESPONSE_TOO_LARGE", "Phản hồi sinh học liệu quá lớn.")
                        body.extend(part)
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("done") is not True or not isinstance(data.get("response"), str):
                raise ValueError("incomplete Ollama response")
            return data["response"]
        except httpx.TimeoutException as error:
            raise StudyProviderError("PROVIDER_TIMEOUT", "Hết thời gian chờ sinh học liệu. Vui lòng thử lại.") from error
        except httpx.HTTPError as error:
            raise StudyProviderError("PROVIDER_UNAVAILABLE", "Không kết nối được dịch vụ sinh học liệu. Vui lòng thử lại.") from error
        except (ValueError, UnicodeError) as error:
            raise StudyProviderError("PROVIDER_RESPONSE_INVALID", "Dịch vụ sinh học liệu trả phản hồi không hợp lệ.") from error


__all__ = [
    "MAX_STUDY_RESPONSE_BYTES", "StudyEvidence", "StudyProviderError",
    "format_study_evidence", "OllamaStudyProvider",
]
