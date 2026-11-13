"""Explicit F2 Gemini adapters. No shared F1/F3 provider or silent fallback.

Uses Google's generateContent REST endpoint with JSON Schema output. Keys go
only in the auth header to the fixed Google origin, never in URLs or messages.
Requests happen only when generate() is called; Q01/Q05 remain independent.
"""
from __future__ import annotations

import json
import re

import httpx

from backend.core.f2_quiz_payload import quiz_response_schema
from backend.providers.f2_definition_prompts import build_definition_flashcard_prompt, build_definition_quiz_prompt
from backend.providers.f2_study_provider import MAX_STUDY_RESPONSE_BYTES, StudyEvidence, StudyProviderError


DEFAULT_GEMINI_STUDY_MODEL = "gemini-3.5-flash-lite"
_API_ORIGIN = "https://generativelanguage.googleapis.com"


def _schema(study_format: str) -> dict:
    if study_format == "quiz":
        return quiz_response_schema()
    text = {"type": "string"}
    source_ids = {"type": "array", "items": text, "minItems": 1}
    fields = {"front": text, "back": text, "source_ids": source_ids}
    root = "cards"
    item = {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}
    return {"type": "object", "properties": {root: {"type": "array", "items": item}},
            "required": [root], "additionalProperties": False}


class GeminiStudyProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_STUDY_MODEL,
                 *, transport: httpx.BaseTransport | None = None):
        if (not isinstance(api_key, str) or not api_key.strip()
            or api_key.strip() == "your_gemini_api_key_here" or any(c.isspace() for c in api_key.strip())):
            raise StudyProviderError("PROVIDER_NOT_CONFIGURED", "Hãy nhập Gemini API key hợp lệ trong ô cấu hình.")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
            raise StudyProviderError("PROVIDER_CONFIGURATION_INVALID", "Tên model Gemini không hợp lệ.")
        self._api_key = api_key.strip()
        self.model = model
        self.transport = transport

    def generate_from_prompt(self, prompt: str, study_format: str) -> str:
        if study_format not in ("quiz", "flashcards"):
            raise ValueError("expected quiz or flashcards")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": _schema(study_format),
                                 "candidateCount": 1, "maxOutputTokens": 8192},
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0), transport=self.transport,
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", f"{_API_ORIGIN}/v1beta/models/{self.model}:generateContent",
                                   headers={"x-goog-api-key": self._api_key}, json=payload) as response:
                    status = response.status_code
                    if status in (401, 403):
                        raise StudyProviderError("PROVIDER_AUTH_FAILED", f"Gemini từ chối API key hoặc quyền truy cập (HTTP {status}); hãy kiểm tra key/project.")
                    if status == 429:
                        raise StudyProviderError("PROVIDER_RATE_LIMITED", f"Gemini đã hết hạn mức hoặc đang giới hạn lượt gọi (HTTP {status}); hãy kiểm tra quota và thử lại.")
                    if status == 404:
                        raise StudyProviderError("PROVIDER_MODEL_NOT_FOUND", f"Không tìm thấy model Gemini hoặc project chưa được dùng model này (HTTP {status}).")
                    if 300 <= status < 500:
                        raise StudyProviderError("PROVIDER_REQUEST_REJECTED", f"Gemini từ chối yêu cầu (HTTP {status}); hãy kiểm tra model và cấu hình API.")
                    if status >= 500:
                        raise StudyProviderError("PROVIDER_UNAVAILABLE", f"Dịch vụ Gemini gặp lỗi (HTTP {status}); hãy thử lại sau.")
                    response.raise_for_status()
                    body = bytearray()
                    for part in response.iter_bytes():
                        if len(body) + len(part) > MAX_STUDY_RESPONSE_BYTES:
                            raise StudyProviderError("PROVIDER_RESPONSE_TOO_LARGE", "Phản hồi Gemini quá lớn; hãy giảm số lượng hoặc nguồn đã chọn.")
                        body.extend(part)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("invalid envelope")
            feedback = data.get("promptFeedback", {})
            if isinstance(feedback, dict) and feedback.get("blockReason"):
                raise StudyProviderError("PROVIDER_BLOCKED", "Gemini đã chặn nội dung yêu cầu; hãy kiểm tra tài liệu hoặc chọn nguồn khác.")
            candidates = data.get("candidates")
            if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
                raise ValueError("missing or ambiguous candidate")
            candidate = candidates[0]
            reason = candidate.get("finishReason")
            if reason in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION", "SPII"):
                raise StudyProviderError("PROVIDER_BLOCKED", "Gemini không trả học liệu do bộ lọc nội dung; hãy kiểm tra nguồn.")
            if reason != "STOP":
                raise StudyProviderError("PROVIDER_RESPONSE_INCOMPLETE", "Gemini chưa hoàn tất phản hồi; hãy giảm số lượng hoặc thử lại.")
            content = candidate.get("content")
            if not isinstance(content, dict):
                raise ValueError("missing content")
            parts = content.get("parts")
            if not isinstance(parts, list) or not parts:
                raise ValueError("missing parts")
            chunks = []
            for part in parts:
                if not isinstance(part, dict):
                    raise ValueError("invalid part")
                if part.get("thought") is True:
                    continue
                if not isinstance(part.get("text"), str) or set(part) - {"text", "thought", "thoughtSignature"}:
                    raise ValueError("unexpected output kind")
                chunks.append(part["text"])
            raw = "".join(chunks)
            if not raw.strip():
                raise ValueError("empty output")
            return raw  # Existing services perform strict inner JSON/source mapping.
        except httpx.TimeoutException:
            raise StudyProviderError("PROVIDER_TIMEOUT", "Hết thời gian chờ Gemini; hãy thử lại hoặc giảm số lượng.") from None
        except httpx.HTTPError:
            raise StudyProviderError("PROVIDER_UNAVAILABLE", "Không kết nối được Gemini; hãy kiểm tra mạng và thử lại.") from None
        except (ValueError, UnicodeError, RecursionError):
            raise StudyProviderError("PROVIDER_RESPONSE_INVALID", "Gemini trả phản hồi không hợp lệ; đã dừng sử dụng.") from None


class GeminiQuizProvider(GeminiStudyProvider):
    def generate(self, evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
        return self.generate_from_prompt(build_definition_quiz_prompt(evidence, requested_count), "quiz")


class GeminiFlashcardProvider(GeminiStudyProvider):
    def generate(self, evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
        return self.generate_from_prompt(build_definition_flashcard_prompt(evidence, requested_count), "flashcards")
