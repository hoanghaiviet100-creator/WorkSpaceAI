"""NVIDIA-hosted NIM Chat Completions adapters; no tools or hidden fallback.

Use documented hosted request fields and prompt-based JSON output. Do not
assume every catalog model supports response_format or guided JSON schemas.
Existing F2 services strictly validate JSON and source IDs after this adapter.
"""
from __future__ import annotations

import json
import re

import httpx

from backend.providers.f2_definition_prompts import build_definition_flashcard_prompt, build_definition_quiz_prompt
from backend.providers.f2_study_provider import MAX_STUDY_RESPONSE_BYTES, StudyEvidence, StudyProviderError


DEFAULT_NVIDIA_NIM_MODEL = "meta/llama-3.3-70b-instruct"
_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"


class NvidiaNimStudyProvider:
    name = "nvidia_nim"

    def __init__(self, api_key: str, model: str = DEFAULT_NVIDIA_NIM_MODEL,
                 *, transport: httpx.BaseTransport | None = None):
        if (not isinstance(api_key, str) or not api_key.strip()
            or api_key.strip() == "your_nvidia_api_key_here" or any(c.isspace() for c in api_key.strip())):
            raise StudyProviderError("PROVIDER_NOT_CONFIGURED", "Hãy nhập NVIDIA API key trong ô cấu hình NVIDIA NIM.")
        if (not isinstance(model, str) or len(model) > 200
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?", model)):
            raise StudyProviderError("PROVIDER_CONFIGURATION_INVALID", "Tên model NVIDIA NIM không hợp lệ.")
        self._api_key = api_key.strip()
        self.model = model
        self.transport = transport

    def generate_from_prompt(self, prompt: str) -> str:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "temperature": 0.1, "max_tokens": 4096}
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=2.0), transport=self.transport,
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", _ENDPOINT, headers={"Authorization": f"Bearer {self._api_key}",
                                   "Accept": "application/json"}, json=payload) as response:
                    status = response.status_code
                    if status in (401, 403):
                        raise StudyProviderError("PROVIDER_AUTH_FAILED", f"NVIDIA NIM từ chối key hoặc quyền truy cập (HTTP {status}); hãy kiểm tra NVIDIA key/tài khoản.")
                    if status == 429:
                        raise StudyProviderError("PROVIDER_RATE_LIMITED", f"NVIDIA NIM đã hết hạn mức hoặc đang giới hạn lượt gọi (HTTP {status}); hãy kiểm tra quota.")
                    if status == 404:
                        raise StudyProviderError("PROVIDER_MODEL_NOT_FOUND", f"Không tìm thấy model NVIDIA NIM hoặc tài khoản chưa được dùng model này (HTTP {status}).")
                    if status == 202:
                        raise StudyProviderError("PROVIDER_RESPONSE_PENDING", "NVIDIA NIM chưa trả kết quả đồng bộ. Hãy kiểm tra dịch vụ hoặc thử model khác.")
                    if 300 <= status < 500:
                        raise StudyProviderError("PROVIDER_REQUEST_REJECTED", f"NVIDIA NIM từ chối yêu cầu (HTTP {status}); hãy kiểm tra model/cấu hình và quyền sử dụng.")
                    if status >= 500:
                        raise StudyProviderError("PROVIDER_UNAVAILABLE", f"Dịch vụ NVIDIA NIM gặp lỗi (HTTP {status}); hãy thử lại sau.")
                    response.raise_for_status()
                    if status != 200:
                        raise StudyProviderError("PROVIDER_RESPONSE_INVALID", "NVIDIA NIM trả trạng thái phản hồi không hợp lệ.")
                    body = bytearray()
                    for part in response.iter_bytes():
                        if len(body) + len(part) > MAX_STUDY_RESPONSE_BYTES:
                            raise StudyProviderError("PROVIDER_RESPONSE_TOO_LARGE", "Phản hồi NVIDIA NIM quá lớn; hãy giảm số lượng hoặc nguồn đã chọn.")
                        body.extend(part)
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or len(data["choices"]) != 1:
                raise ValueError("missing or ambiguous choices")
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError("invalid choice")
            reason = choice.get("finish_reason")
            if reason == "content_filter":
                raise StudyProviderError("PROVIDER_BLOCKED", "NVIDIA NIM đã chặn nội dung; hãy kiểm tra hoặc chọn lại nguồn.")
            if reason != "stop":
                raise StudyProviderError("PROVIDER_RESPONSE_INCOMPLETE", "NVIDIA NIM chưa hoàn tất phản hồi; hãy giảm số lượng hoặc thử lại.")
            message = choice.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise ValueError("invalid message")
            if message.get("refusal"):
                raise StudyProviderError("PROVIDER_BLOCKED", "NVIDIA NIM từ chối tạo nội dung từ yêu cầu này.")
            if message.get("tool_calls") or message.get("function_call"):
                raise ValueError("unexpected tool output")
            raw = message.get("content")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("empty or invalid content")
            return raw  # Never repair JSON, remove fences, grade or mark VERIFIED.
        except httpx.TimeoutException:
            raise StudyProviderError("PROVIDER_TIMEOUT", "Hết thời gian chờ NVIDIA NIM; hãy giảm số lượng hoặc thử lại.") from None
        except httpx.HTTPError:
            raise StudyProviderError("PROVIDER_UNAVAILABLE", "Không kết nối được NVIDIA NIM; hãy kiểm tra mạng và thử lại.") from None
        except (ValueError, UnicodeError, RecursionError):
            raise StudyProviderError("PROVIDER_RESPONSE_INVALID", "NVIDIA NIM trả phản hồi không hợp lệ; đã dừng sử dụng.") from None


class NvidiaNimQuizProvider(NvidiaNimStudyProvider):
    def generate(self, evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
        return self.generate_from_prompt(build_definition_quiz_prompt(evidence, requested_count))


class NvidiaNimFlashcardProvider(NvidiaNimStudyProvider):
    def generate(self, evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
        return self.generate_from_prompt(build_definition_flashcard_prompt(evidence, requested_count))
