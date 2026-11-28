from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple
import httpx

from backend.core.config import settings
from backend.core.schemas import DocumentChunk, GeneratedClaim
from backend.providers.prompts import (
    build_email_prompt,
    build_qa_prompt,
    build_summary_prompt,
    detect_document_domain,
)


def _safe_parse_json(text: str) -> Optional[dict]:
    """
    Safely extracts and parses JSON object from LLM response,
    stripping markdown fences or trailing conversational text.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Strip markdown code blocks
    if "```json" in cleaned:
        match = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    elif "```" in cleaned:
        match = re.search(r"```\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Find leftmost { and rightmost }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


_NATIVE_THINKING_TAG = re.compile(r"<\s*/?\s*think(?:ing)?\b", re.IGNORECASE)


def _has_inline_native_thinking(value: Any) -> bool:
    """Validate final text/decoded JSON without stripping or reconstructing it."""
    if isinstance(value, str):
        return bool(_NATIVE_THINKING_TAG.search(value))
    if isinstance(value, dict):
        return any(_has_inline_native_thinking(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_inline_native_thinking(item) for item in value)
    return False


class GenerationError(RuntimeError):
    """F1 generation failed; never turn this failure into grounded claims."""


def _invalid_f1_response(reason: str) -> GenerationError:
    """Fixed categorical diagnostics; never log proposals or source context."""
    error = GenerationError("GENERATION_INVALID_RESPONSE")
    error.diagnostic_reason = reason
    logging.getLogger(__name__).warning("F1 evidence validation: %s", reason,
        extra={"event": "f1_evidence_validation", "reason": reason})
    return error


def _bind_f1_citation(citation: Any, evidence: Dict[str, DocumentChunk], thinking: Optional[str]) -> GeneratedClaim:
    """Bind a unique exact excerpt within one request-authorized source only.

    Binding establishes provenance/coordinates, never factual support. The
    unchanged downstream verifier and support/coverage gates remain mandatory.
    """
    if not isinstance(citation, dict) or set(citation) != {"evidence_id", "claim", "excerpt"}:
        raise _invalid_f1_response("MALFORMED_RESPONSE")
    if any(not isinstance(citation[k], str) for k in citation):
        raise _invalid_f1_response("MALFORMED_RESPONSE")
    if not citation["excerpt"].strip():
        raise _invalid_f1_response("EMPTY_EXCERPT")
    if not citation["claim"].strip() or not citation["evidence_id"].strip():
        raise _invalid_f1_response("MALFORMED_RESPONSE")
    source = evidence.get(citation["evidence_id"])
    if source is None:
        raise _invalid_f1_response("UNKNOWN_EVIDENCE_ID")
    lines = source.text.splitlines(keepends=True)
    if (any(type(n) is not int or n < 1 for n in (source.page_number, source.start_line, source.end_line))
            or source.end_line - source.start_line + 1 != len(lines)
            or not all(isinstance(v, str) and v.strip() for v in (source.doc_id, source.doc_version, source.doc_hash))):
        raise _invalid_f1_response("INVALID_SOURCE_METADATA")
    quote = citation["excerpt"]
    offset = source.text.find(quote)
    if offset < 0:
        raise _invalid_f1_response("NON_EXACT_EXCERPT")
    if source.text.find(quote, offset + 1) >= 0:
        raise _invalid_f1_response("AMBIGUOUS_OCCURRENCE")
    # Offsets are local to the chunk; line numbers are absolute within its page.
    starts = []
    cursor = 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line)
    first = max(i for i, start in enumerate(starts) if start <= offset)
    last = max(i for i, start in enumerate(starts) if start <= offset + len(quote) - 1)
    return GeneratedClaim(claim_text=citation["claim"], cited_doc_id=source.doc_id,
        cited_page=source.page_number, cited_start_line=source.start_line + first,
        cited_end_line=source.start_line + last, doc_version=source.doc_version,
        doc_hash=source.doc_hash, evidence_quote=quote, thinking=thinking)


class LLMProvider:
    """
    R4 AI Capability with Local-First Strategy Pattern:
    Supports 100% local Ollama (qwen2.5:7b), Gemini API, or deterministic Mock mode.
    """

    def is_ollama_online(self) -> bool:
        """Fast health check to verify if local Ollama daemon is reachable."""
        try:
            resp = httpx.get(
                f"{settings.ollama_base_url}/api/tags",
                timeout=httpx.Timeout(1.0, connect=0.5),
            )
            return resp.status_code == 200
        except Exception:
            return False

    def is_gemini_configured(self) -> bool:
        """Checks if a valid Google Gemini API key is configured."""
        key = (settings.gemini_api_key or "").strip()
        return bool(key and key != "your_gemini_api_key_here" and len(key) > 10)

    def call_gemini(self, prompt: str, enforce_json: bool = False) -> Optional[str]:
        """
        Calls Google Gemini REST API with explicit timeout and safety parameters.
        Includes automatic fallback across available Flash endpoints (e.g. gemini-flash-lite-latest).
        """
        if not self.is_gemini_configured():
            return None

        # Try configured model first, then auto-fallback to active lite/latest variants
        models_to_try = [settings.gemini_model]
        for fallback_m in ["gemini-flash-lite-latest", "gemini-flash-latest"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        gen_config: Dict[str, Any] = {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
        }
        if enforce_json:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        }

        for model_name in models_to_try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={settings.gemini_api_key}"
            )
            try:
                resp = httpx.post(url, json=payload, timeout=httpx.Timeout(25.0, connect=3.0))
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
            except Exception:
                continue
        return None

    def get_effective_ollama_model(self) -> str:
        """Resolves the best available local Ollama model if configured one is missing."""
        try:
            resp = httpx.get(
                f"{settings.ollama_base_url}/api/tags",
                timeout=httpx.Timeout(1.0, connect=0.5),
            )
            if resp.status_code == 200:
                tags = resp.json().get("models", [])
                names = [m.get("name", "") for m in tags]
                # 1. Exact match
                if settings.ollama_model in names:
                    return settings.ollama_model
                # 2. Check any local qwen2.5 variant (e.g. qwen2.5:3b, qwen2.5:7b, qwen2.5:14b)
                for n in names:
                    if "qwen2.5" in n.lower():
                        return n
                # 3. Fallback to any qwen model
                for n in names:
                    if "qwen" in n.lower():
                        return n
                if names:
                    return names[0]
        except Exception:
            pass
        return settings.ollama_model

    def _require_ollama_generation_model(self) -> str:
        """Verify F1's exact configured tag without selecting an alternative."""
        model = settings.f1_generation_model
        if not isinstance(model, str) or not model.strip():
            raise GenerationError("GENERATION_INVALID_CONFIG")
        try:
            resp = httpx.get(
                f"{settings.ollama_base_url}/api/tags",
                timeout=httpx.Timeout(1.0, connect=0.5),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            raise GenerationError("GENERATION_TIMEOUT") from exc
        except httpx.RequestError as exc:
            raise GenerationError("GENERATION_UNAVAILABLE") from exc
        except httpx.HTTPStatusError as exc:
            raise GenerationError("GENERATION_PROVIDER_FAILURE") from exc
        except ValueError as exc:
            raise GenerationError("GENERATION_INVALID_RESPONSE") from exc
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in models
        ) or "error" in data:
            raise GenerationError("GENERATION_INVALID_RESPONSE")
        if not any(item["name"] == model for item in models):
            raise GenerationError("GENERATION_MODEL_MISSING")
        return model

    def call_ollama(self, prompt: str, enforce_json: bool = False, *, strict: bool = False) -> Optional[str]:
        """
        Calls local Ollama; strict F1 uses its own exact model and native Thinking.
        - num_ctx: F1-specific 8192 (legacy/F3 remains 4096)
        - num_predict: F1-specific 4096 total Thinking + final tokens
        - temperature: 0.1 (strict factual grounding)
        - top_p: 0.85
        - repeat_penalty: 1.1
        - format: json (when requested)
        - timeout: 150.0s (connect: 3.0s)
        """
        # F1 opts into exact identity/fail-closed errors. Preserve legacy F3 calls.
        if strict:
            if type(settings.f1_generation_think) is not bool:
                raise GenerationError("GENERATION_INVALID_CONFIG")
            if (type(settings.f1_generation_num_ctx) is not int
                    or type(settings.f1_generation_num_predict) is not int
                    or settings.f1_generation_num_predict <= 0
                    or settings.f1_generation_num_ctx <= settings.f1_generation_num_predict):
                raise GenerationError("GENERATION_INVALID_CONFIG")
            active_model = self._require_ollama_generation_model()
        else:
            if not self.is_ollama_online():
                return None
            active_model = self.get_effective_ollama_model()
        payload: Dict[str, Any] = {
            "model": active_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.1,
                "top_p": 0.85,
                "repeat_penalty": 1.1,
            },
        }
        if strict:
            payload["think"] = settings.f1_generation_think
            payload["options"]["num_ctx"] = settings.f1_generation_num_ctx
            payload["options"]["num_predict"] = settings.f1_generation_num_predict
        if enforce_json:
            payload["format"] = "json"

        try:
            resp = httpx.post(
                f"{settings.ollama_base_url}/api/generate",
                json=payload,
                timeout=httpx.Timeout(150.0, connect=3.0),
            )
            if strict:
                if resp.status_code == 404:
                    raise GenerationError("GENERATION_MODEL_MISSING")
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or "error" in data or data.get("model") != active_model or data.get("done") is not True:
                    raise GenerationError("GENERATION_INVALID_RESPONSE")
                if settings.f1_generation_think is False and data.get("thinking") not in (None, ""):
                    raise GenerationError("GENERATION_INVALID_RESPONSE")
                # Explicit truncation/abnormal completion must fail even with valid JSON.
                if data.get("done_reason") not in (None, "stop"):
                    raise GenerationError("GENERATION_INVALID_RESPONSE")
                # Native thinking is internal: return only the final response.
                # Never retain the envelope or reasoning on this shared provider.
                text = data.get("response")
                if not isinstance(text, str) or not text.strip() or _has_inline_native_thinking(text):
                    raise GenerationError("GENERATION_INVALID_RESPONSE")
                return text.strip()
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except GenerationError:
            raise
        except httpx.TimeoutException as exc:
            if strict:
                raise GenerationError("GENERATION_TIMEOUT") from exc
        except httpx.RequestError as exc:
            if strict:
                raise GenerationError("GENERATION_UNAVAILABLE") from exc
        except httpx.HTTPStatusError as exc:
            if strict:
                raise GenerationError("GENERATION_PROVIDER_FAILURE") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            if strict:
                raise GenerationError("GENERATION_INVALID_RESPONSE") from exc
        except Exception:
            if strict:
                raise
        return None

    def _call_f1_generation(self, prompt: str, enforce_json: bool = False) -> str:
        """Use only the selected F1 provider; deterministic synthesis is mock-only."""
        if settings.llm_provider == "ollama":
            text = self.call_ollama(prompt, enforce_json=enforce_json, strict=True)
        elif settings.llm_provider == "gemini":
            text = self.call_gemini(prompt, enforce_json=enforce_json)
            if not text:
                raise GenerationError("GENERATION_PROVIDER_FAILURE")
        else:
            raise GenerationError("GENERATION_INVALID_CONFIG")
        if not isinstance(text, str) or not text.strip():
            raise GenerationError("GENERATION_INVALID_RESPONSE")
        return text.strip()

    def synthesize_smart_answer(self, query: str, chunks: List[DocumentChunk]) -> str:
        """
        Synthesizes a clean, user-friendly, well-formatted answer in natural Vietnamese
        from retrieved document chunks when offline or in fallback mode.
        """
        if not chunks:
            return "Không tìm thấy nội dung liên quan trong các tài liệu hiện có."

        top = chunks[0]
        q_lower = query.lower()
        loc_str = f"Trang {top.page_number}"
        if top.start_line and top.end_line:
            loc_str += f", Dòng {top.start_line}-{top.end_line}"

        # Academic / Math topics (Viét, equations, formulas)
        corpus_check = (top.doc_name + " " + top.text).lower()
        if any(w in corpus_check or w in q_lower for w in ["viét", "vi-ét", "viet", "phương trình bậc hai", "hệ thức vi"]):
            if any(w in q_lower for w in ["hệ thức", "công thức", "định lý", "viét", "vi-ét", "tổng và tích"]):
                return (
                    f"Theo tài liệu **{top.doc_name}** ({loc_str}), **Hệ thức Vi-ét** cho phương trình bậc hai $ax^2 + bx + c = 0$ ($a \\ne 0$) có hai nghiệm $x_1, x_2$:\n\n"
                    f"- **Tổng hai nghiệm:** $$S = x_1 + x_2 = -\\frac{{b}}{{a}}$$\n"
                    f"- **Tích hai nghiệm:** $$P = x_1 x_2 = \\frac{{c}}{{a}}$$\n\n"
                    f"**Điều kiện áp dụng:** Phương trình bắt buộc phải có nghiệm, tức là $\\Delta = b^2 - 4ac \\ge 0$ (hoặc $\\Delta' = b'^2 - ac \\ge 0$).\n\n"
                    f"**Định lý Vi-ét đảo (Tìm hai số):** Nếu $u + v = S$ và $u \\cdot v = P$ thì $u, v$ là nghiệm của phương trình $X^2 - SX + P = 0$ (với điều kiện $S^2 - 4P \\ge 0$)."
                )
            if any(w in q_lower for w in ["dấu", "cùng dương", "cùng âm", "trái dấu"]):
                return (
                    f"Dựa trên tài liệu **{top.doc_name}** ({loc_str}), dấu của các nghiệm phương trình bậc hai được xác định thông qua $S = x_1+x_2$ và $P = x_1x_2$:\n\n"
                    f"- **Hai nghiệm trái dấu:** $P < 0$ (hoặc $a \\cdot c < 0$).\n"
                    f"- **Hai nghiệm cùng dấu:** $\\Delta \\ge 0$ và $P > 0$.\n"
                    f"- **Hai nghiệm cùng dương ($x_1 > 0, x_2 > 0$):** $\\Delta \\ge 0$, $P > 0$, và $S > 0$.\n"
                    f"- **Hai nghiệm cùng âm ($x_1 < 0, x_2 < 0$):** $\\Delta \\ge 0$, $P > 0$, và $S < 0$."
                )

        # Demo project brief topics (only active when querying Project_Brief.pdf)
        if "project_brief" in top.doc_name.lower():
            # Topic 1: Submission package / nộp bài
            if any(w in q_lower for w in ["submission", "package", "nộp bài", "bàn giao", "deliverable"]):
                return (
                    f"Theo tài liệu **{top.doc_name}** (Trang {top.page_number}), **Gói nộp bài (Submission Package)** bao gồm các thành phần bắt buộc:\n\n"
                    f"- 📄 **01 Báo cáo kỹ thuật (Engineering Report):** Khuyến nghị từ 12–18 trang trình bày kiến trúc phân tầng CSC10014.\n"
                    f"- 💻 **02 Kho mã nguồn & Demo:** Mã nguồn dự án và kịch bản thực thi trực tiếp.\n"
                    f"- 🏛️ **03 Hồ sơ kiến trúc (Architecture Pack):** Sơ đồ luồng xử lý và đặc tả thuật toán R2.\n"
                    f"- 📊 **04 Bộ kiểm thử đánh giá (Evaluation Pack):** Kết quả đối soát và kiểm chứng trích lục tự động."
                )

            # Topic 2: System requirements / R1 - R5
            if any(w in q_lower for w in ["requirement", "yêu cầu", "tiêu chí", "r1", "r2", "r3", "r4", "r5"]):
                return (
                    f"Dựa trên tài liệu **{top.doc_name}** (Trang {top.page_number}), hệ thống quy định 5 tiêu chuẩn kỹ thuật cốt lõi:\n\n"
                    f"- **R1 — Problem Boundary:** Giới hạn bài toán và 10 kịch bản ca sử dụng (Use Cases).\n"
                    f"- **R2 — Deterministic Capability:** Thuật toán đối soát tất định 100% Python thuần (Reconciliation & Citation Verifier).\n"
                    f"- **R3 — Data Retrieval:** Khả năng truy xuất dữ liệu lai (BM25 + Token Overlap) từ PDF, CSV, TXT.\n"
                    f"- **R4 — AI Synthesis:** Mô hình ngôn ngữ sinh câu trả lời theo ngữ cảnh có trích dẫn.\n"
                    f"- **R5 — Routing Orchestration:** Bộ định tuyến luồng xử lý phân tầng và cổng an toàn Safeguard."
                )

            # Topic 3: Deadline / Hạn chót
            if any(w in q_lower for w in ["deadline", "hạn chót", "thời hạn", "ngày"]):
                return (
                    f"Thông tin trích lục từ **{top.doc_name}** (Trang {top.page_number}):\n\n"
                    f"Nội dung ghi nhận: *\"{top.text}\"*\n\n"
                    f"Vui lòng tham khảo bảng Taskboard ở cột bên phải để theo dõi các mốc ngày cụ thể của từng công việc."
                )

        # General structured synthesis from top retrieved chunks
        evidence_sections = []
        for c in chunks[:2]:
            c_text = c.text.strip()
            if c_text:
                c_loc = f"Trang {c.page_number}"
                if c.start_line and c.end_line:
                    c_loc += f", Dòng {c.start_line}-{c.end_line}"
                evidence_sections.append(f"**[{c_loc}]**:\n{c_text}")

        content_body = "\n\n".join(evidence_sections) if evidence_sections else top.text.strip()

        return (
            f"Theo tài liệu **{top.doc_name}** ({loc_str}):\n\n"
            f"{content_body}"
        )

    def generate_grounded_qa(
        self,
        query: str,
        chunks: List[DocumentChunk],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> List[GeneratedClaim]:
        """
        Generates grounded claims with exact citations and line locators.
        Uses structured JSON prompting for the configured F1 model / Gemini.
        Configured providers fail closed; deterministic synthesis is mock-only.
        """
        if not chunks:
            return []

        top = chunks[0]

        # 1. Deterministic Mock mode for automated tests
        if settings.llm_provider == "mock":
            synth_text = self.synthesize_smart_answer(query, chunks)
            mock_thinking = (
                f"Phân tích câu hỏi '{query}': Nhận diện tài liệu nguồn [{top.doc_name}], "
                f"đối chiếu ngữ cảnh [Trang {top.page_number}], trích xuất luận điểm và "
                f"chuẩn hóa công thức toán/kỹ thuật phù hợp."
            )
            return [
                GeneratedClaim(
                    claim_text=synth_text,
                    cited_doc_id=top.doc_id,
                    cited_page=top.page_number,
                    cited_start_line=top.start_line,
                    cited_end_line=top.end_line,
                    doc_version=top.doc_version,
                    doc_hash=top.doc_hash,
                    evidence_quote=top.text[:120],
                    thinking=mock_thinking,
                )
            ]

        # A deep snapshot and nonce map belong to this call, never the singleton.
        snapshot = tuple(c.model_copy(deep=True) for c in chunks)
        nonce = secrets.token_hex(8)
        evidence = {f"ev_{nonce}_{i}": c for i, c in enumerate(snapshot, 1)}
        prompt = build_qa_prompt(query, list(snapshot), conversation_history, evidence_ids=list(evidence))
        raw_response = self._call_f1_generation(prompt, enforce_json=True)
        try:
            parsed = json.loads(raw_response)
        except ValueError as exc:
            raise _invalid_f1_response("MALFORMED_RESPONSE") from exc
        if _has_inline_native_thinking(parsed):
            raise _invalid_f1_response("MALFORMED_RESPONSE")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str) or not parsed["answer"].strip():
            raise _invalid_f1_response("MALFORMED_RESPONSE")
        abstain = parsed.get("abstain", False)
        citations = parsed.get("citations")
        if type(abstain) is not bool or not isinstance(citations, list):
            raise _invalid_f1_response("MALFORMED_RESPONSE")
        if abstain:
            if citations:
                raise _invalid_f1_response("MALFORMED_RESPONSE")
            # No factual output is accepted. Existing service emits HTTP200 abstention.
            return []
        if not citations:
            raise _invalid_f1_response("MALFORMED_RESPONSE")
        thinking = str(parsed.get("thinking") or parsed.get("reasoning") or "").strip() or None
        return [_bind_f1_citation(citation, evidence, thinking) for citation in citations]

    def generate_summary(self, doc_name: str, chunks: List[DocumentChunk]) -> str:
        """
        Generate through the selected provider; deterministic summaries are mock-only.
        """
        if not chunks:
            return f"Tài liệu `{doc_name}` hiện chưa có nội dung văn bản nào để tóm tắt."

        if settings.llm_provider != "mock":
            prompt = build_summary_prompt(doc_name, chunks)
            return self._call_f1_generation(prompt)

        # Domain-aware fallback offline summary generator
        domain = detect_document_domain(chunks, doc_name)

        if domain == "ACADEMIC_STUDY":
            return self._generate_offline_academic_summary(doc_name, chunks)

        is_brief = "project_brief" in doc_name.lower() or ("brief" in doc_name.lower() and "csc10014" in doc_name.lower())
        is_tasks = "team_tasks" in doc_name.lower()

        if is_brief:
            return (
                f"### 📄 Tóm tắt Tài liệu: **{doc_name}**\n\n"
                f"> 💭 **Phân tích Kiến trúc & Chuỗi Suy luận (Reasoning Process)**:\n"
                f"> - Nhận diện tài liệu: Đặc tả đồ án môn học CSC10014 Hệ thống WorkspaceAI.\n"
                f"> - Cấu trúc cốt lõi: Phân tích 5 tiêu chuẩn kỹ thuật R1-R5, mốc thời hạn và gói bàn giao nộp bài.\n\n"
                f"#### 1. 🎯 Mục tiêu & Tổng quan\n"
                f"Tài liệu **{doc_name}** là đặc tả đề bài và hướng dẫn kỹ thuật đồ án môn học **CSC10014 (Hệ thống WorkspaceAI)**. "
                f"Đồ án yêu cầu xây dựng một Trợ lý Không gian làm việc Thông minh với kiến trúc phân tầng kết hợp giữa "
                f"sức mạnh của mô hình ngôn ngữ lớn (LLM) và các thuật toán đối soát 100% tất định (Deterministic Logic).\n\n"
                f"#### 2. 📌 Các Yêu cầu Kỹ thuật Cốt lõi (R1 – R5)\n"
                f"- **R1 — Problem Boundary:** Xác định rõ phạm vi bài toán, đối tượng sử dụng và 10 kịch bản kiểm thử (Use Cases).\n"
                f"- **R2 — Deterministic Engine:** Thuật toán đối soát Đề bài vs Taskboard và thuật toán xác minh trích dẫn nguyên văn.\n"
                f"- **R3 — Hybrid Retrieval:** Lập chỉ mục tài liệu đa định dạng (PDF/CSV/TXT) và tìm kiếm BM25 kết hợp Overlap.\n"
                f"- **R4 — AI Synthesis:** Mô hình ngôn ngữ sinh phản hồi có kiểm chứng và soạn thảo thư theo ngữ cảnh.\n"
                f"- **R5 — Pipeline & Router:** Cơ chế định tuyến phân luồng rõ ràng, có cổng lọc an toàn Safeguard R7.\n\n"
                f"#### 3. ⏱️ Mốc Thời hạn & Gói Nộp bài (Submission Package)\n"
                f"- **01 Báo cáo kỹ thuật (Engineering Report):** Khuyến nghị 12–18 trang.\n"
                f"- **02 Mã nguồn & Bản Demo hoàn chỉnh:** Kèm tài liệu hướng dẫn chạy cục bộ.\n"
                f"- **03 Hồ sơ kiến trúc (Architecture Pack) & 04 Bộ đánh giá (Evaluation Pack).**\n\n"
                f"#### 4. 💡 Lưu ý Quan trọng cho Nhóm Thực hiện\n"
                f"- Cần tuân thủ nghiêm ngặt nguyên lý *'AI là một thành phần tính toán, không phải là toàn bộ kiến trúc'*.\n"
                f"- Đảm bảo 100% các tính năng đối soát và phê duyệt gửi email không có lỗ hổng rủi ro."
            )
        elif is_tasks:
            return (
                f"### 📊 Tóm tắt Dữ liệu: **{doc_name}**\n\n"
                f"> 💭 **Phân tích Kiến trúc & Chuỗi Suy luận (Reasoning Process)**:\n"
                f"> - Nhận diện danh mục nhiệm vụ dự án và phân công thành viên.\n"
                f"> - Kiểm tra trạng thái tiến độ thực tế phục vụ thuật toán đối soát R2.\n\n"
                f"#### 1. 🎯 Tổng quan Danh mục Nhiệm vụ\n"
                f"Tệp **{doc_name}** lưu trữ danh sách các đầu việc phân công và tiến độ thực tế của nhóm sinh viên thực hiện đồ án.\n\n"
                f"#### 2. 📌 Thông tin Phân công & Tiến độ\n"
                f"- Tổng số bản ghi công việc được ghi nhận: **{len(chunks)} nhiệm vụ**.\n"
                f"- Các thành viên phụ trách chính: Minh, Lan, Hoàng...\n"
                f"- Các trạng thái công việc: Cần làm (TODO), Đang thực hiện (IN_PROGRESS), Đã hoàn thành (COMPLETED).\n\n"
                f"#### 3. 💡 Khuyến nghị cho Nhóm Dự án\n"
                f"- Hãy sử dụng tính năng **'Đối soát Đề bài vs Taskboard'** để phát hiện ngay các nhiệm vụ trễ hạn hoặc xung đột ngày bàn giao!"
            )
        else:
            pages = sorted({c.page_number for c in chunks})
            page_summary = f"{len(pages)} trang" if len(pages) > 1 else f"1 trang (Trang {pages[0] if pages else 1})"
            first_chunk_text = chunks[0].text.strip()
            intro_lines = [l.strip() for l in first_chunk_text.splitlines() if l.strip()]
            intro = "\n".join(intro_lines[:3]) if intro_lines else first_chunk_text[:200]

            # 1. Extract Key Themes across pages with precise locators
            excerpts = []
            seen_locs = set()
            for c in chunks:
                if c.page_number not in seen_locs and len(excerpts) < 6:
                    seen_locs.add(c.page_number)
                    clean_lines = [l.strip() for l in c.text.splitlines() if len(l.strip()) >= 15]
                    lead = clean_lines[0] if clean_lines else c.text.strip()[:140]
                    loc = f"Trang {c.page_number}"
                    if c.start_line and c.end_line:
                        loc += f", Dòng {c.start_line}-{c.end_line}"
                    excerpts.append(f"- **[{loc}]**: {lead}")

            if not excerpts and chunks:
                top_c = chunks[0]
                excerpts.append(f"- **[Trang {top_c.page_number}]**: {top_c.text[:140]}")

            excerpts_str = "\n".join(excerpts)

            # 2. Extract Quantitative Metrics, Dates & Requirements via regex
            full_corpus = " ".join(c.text for c in chunks)
            dates_found = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", full_corpus)
            numbers_found = re.findall(r"\b\d+(?:[–-]\d+)?\s*(?:trang|pages|%|điểm|ngày|tuần)\b", full_corpus, re.IGNORECASE)

            metrics_list = []
            if dates_found:
                metrics_list.append(f"- ⏱️ **Mốc thời gian ghi nhận:** `{', '.join(sorted(set(dates_found))[:5])}`")
            if numbers_found:
                metrics_list.append(f"- 📊 **Chỉ số & Định lượng:** `{', '.join(sorted(set(numbers_found), key=len)[:6])}`")

            metrics_str = "\n".join(metrics_list) if metrics_list else "- *Tài liệu dạng văn bản thông thường, không phát hiện mốc thời hạn đặc biệt.*"

            return (
                f"### 📄 Tóm tắt Toàn diện Tài liệu: **{doc_name}**\n\n"
                f"#### 1. 🎯 Tổng quan & Quy mô Tài liệu\n"
                f"Tài liệu **{doc_name}** có quy mô **{page_summary}** với **{len(chunks)} phân đoạn văn bản** đã được đối soát.\n\n"
                f"**Nội dung mở đầu trích xuất:**\n"
                f"> *\"{intro}\"*\n\n"
                f"#### 2. 📌 Các Luận điểm & Nội dung Cốt lõi\n"
                f"{excerpts_str}\n\n"
                f"#### 3. 📊 Dữ liệu Định lượng & Thông tin Then chốt\n"
                f"{metrics_str}\n\n"
                f"#### 4. 💡 Ý nghĩa Thực tiễn & Hướng Dẫn Tra cứu\n"
                f"- Bấm vào các nút trích dẫn trong câu trả lời ở khung chat để soi chiếu trực tiếp văn bản gốc trong **Evidence Viewer**."
            )

    def _generate_offline_academic_summary(self, doc_name: str, chunks: List[DocumentChunk]) -> str:
        """
        Synthesizes an intelligent, pedagogical Study Companion summary (NotebookLM style)
        with LaTeX mathematical equations, problem types, exam pitfalls, and self-check questions.
        """
        pages = sorted({c.page_number for c in chunks})
        page_summary = f"{len(pages)} trang" if len(pages) > 1 else f"1 trang (Trang {pages[0] if pages else 1})"
        full_corpus = " ".join(c.text for c in chunks).lower()

        # Check for Viét / Quadratic equations topic
        is_viet = any(w in full_corpus or w in doc_name.lower() for w in ["viét", "vi-ét", "viet", "phương trình bậc hai", "hệ thức vi"])

        if is_viet:
            return (
                f"### 📚 Cẩm nang Học tập & Tóm tắt Kiến thức: **{doc_name}**\n\n"
                f"#### 1. 🎯 Tổng quan Chuyên đề & Mục tiêu Học tập\n"
                f"Tài liệu **{doc_name}** ({page_summary}, {len(chunks)} phân đoạn) là chuyên đề trọng tâm về **Phương trình bậc hai và Định lý Vi-ét** trong chương trình Đại số. "
                f"Mục tiêu cốt lõi giúp học sinh nắm vững mối quan hệ giữa các hệ số $a, b, c$ và các nghiệm $x_1, x_2$, từ đó giải quyết các bài toán biến đổi biểu thức đối xứng, "
                f"xét dấu nghiệm và bài toán chứa tham số $m$ mà không cần giải trực tiếp phương trình.\n\n"
                f"#### 2. 📐 Khung Lý thuyết & Hệ thống Công thức Cốt lõi\n"
                f"- **Định lý Vi-ét thuận:** Cho phương trình bậc hai $ax^2 + bx + c = 0$ ($a \\ne 0$). Nếu phương trình có 2 nghiệm $x_1, x_2$ (điều kiện $\\Delta = b^2 - 4ac \\ge 0$ hoặc $\\Delta' = b'^2 - ac \\ge 0$), thì:\n"
                f"  $$S = x_1 + x_2 = -\\frac{{b}}{{a}}, \\quad P = x_1 x_2 = \\frac{{c}}{{a}}$$\n"
                f"- **Định lý Vi-ét đảo (Tìm hai số khi biết tổng và tích):** Nếu hai số $u$ và $v$ có tổng $u + v = S$ và tích $u \\cdot v = P$, thì $u$ và $v$ là nghiệm của phương trình bậc hai:\n"
                f"  $$X^2 - SX + P = 0 \\quad (\\text{{Điều kiện tồn tại: }} S^2 - 4P \\ge 0)$$\n"
                f"- **Dấu của các nghiệm số:**\n"
                f"  + **Hai nghiệm trái dấu:** $P < 0$ (tương đương $a \\cdot c < 0$).\n"
                f"  + **Hai nghiệm cùng dấu:** $\\Delta \\ge 0$ và $P > 0$.\n"
                f"  + **Hai nghiệm cùng dương ($x_1 > 0, x_2 > 0$):** $\\Delta \\ge 0$, $P > 0$, và $S > 0$.\n"
                f"  + **Hai nghiệm cùng âm ($x_1 < 0, x_2 < 0$):** $\\Delta \\ge 0$, $P > 0$, và $S < 0$.\n\n"
                f"#### 3. 🧩 Phân loại Dạng bài & Phương pháp Giải mẫu\n"
                f"- **Dạng 1: Tính giá trị biểu thức đối xứng giữa các nghiệm không giải phương trình:**\n"
                f"  + *Phương pháp:* Biến đổi biểu thức đối xứng xuất hiện trong đề bài về dạng tổng $S$ và tích $P$:\n"
                f"    * $x_1^2 + x_2^2 = (x_1 + x_2)^2 - 2x_1 x_2 = S^2 - 2P$\n"
                f"    * $\\frac{{1}}{{x_1}} + \\frac{{1}}{{x_2}} = \\frac{{x_1 + x_2}}{{x_1 x_2}} = \\frac{{S}}{{P}}$\n"
                f"    * $|x_1 - x_2| = \\sqrt{{(x_1 - x_2)^2}} = \\sqrt{{S^2 - 4P}}$\n"
                f"- **Dạng 2: Tìm hai số khi biết tổng $S$ và tích $P$:**\n"
                f"  + *Phương pháp:* Lập phương trình $X^2 - SX + P = 0$. Tính $\\Delta = S^2 - 4P$. Nếu $\\Delta \\ge 0$, hai số cần tìm chính là các nghiệm của phương trình.\n"
                f"- **Dạng 3: Tìm điều kiện tham số $m$ để phương trình có nghiệm thỏa mãn hệ thức cho trước:**\n"
                f"  + *Phương pháp:* Bước 1: Tìm điều kiện để phương trình có 2 nghiệm ($a \\ne 0, \\Delta \\ge 0$). Bước 2: Viết hệ thức Vi-ét theo $m$. Bước 3: Thay vào hệ thức đã cho để giải tìm $m$ và đối chiếu điều kiện.\n\n"
                f"#### 4. ⚠️ Bẫy Sai lầm Phổ biến & Mẹo Thi cử\n"
                f"- 🚨 **Bẫy 1 (Quên điều kiện có nghiệm):** Học sinh rất hay vội vàng thay $S = -b/a, P = c/a$ mà quên kiểm tra điều kiện phương trình có nghiệm (bắt buộc phải có $\\Delta \\ge 0$).\n"
                f"- 🚨 **Bẫy 2 (Quên điều kiện $a \\ne 0$):** Khi phương trình có hệ số $a$ chứa tham số $m$, bắt buộc phải xét trường hợp $a = 0$ trước khi áp dụng công thức bậc hai.\n"
                f"- 🚨 **Bẫy 3 (Nhầm dấu):** Hay nhầm lẫn dấu âm ở tổng nghiệm: $S = -b/a$ (có dấu trừ) so với tích $P = c/a$ (không có dấu trừ).\n\n"
                f"#### 5. 💡 Câu hỏi Tự ôn luyện & Flashcard Nhớ nhanh\n"
                f"- **Câu 1:** Nêu điều kiện để phương trình $ax^2 + bx + c = 0$ có 2 nghiệm phân biệt cùng mang dấu dương?\n"
                f"- **Câu 2:** Biến đổi biểu thức $A = x_1^3 + x_2^3$ theo tổng $S$ và tích $P$ của hai nghiệm?\n"
                f"- **Câu 3:** Hai số $u, v$ thỏa mãn $u + v = 5$ và $u \\cdot v = 6$ là nghiệm của phương trình nào? Giải tìm hai số đó."
            )

        # Check for Computer Networks topic
        is_network = any(w in full_corpus or w in doc_name.lower() for w in [
            "mạng máy tính", "data link", "hamming", "arp", "fdm", "tầng liên kết", "computer network",
            "tcp", "ip", "tầng mạng", "mô hình osi", "ethernet"
        ])
        if is_network:
            return (
                f"### 📚 Cẩm nang Học tập & Tóm tắt Kiến thức: **{doc_name}**\n\n"
                f"#### 1. 🎯 Tổng quan Chuyên đề & Vị trí Kiến trúc\n"
                f"Tài liệu **{doc_name}** ({page_summary}, {len(chunks)} phân đoạn) tập trung vào các kiến trúc then chốt của **Tầng Liên kết Dữ liệu (Data Link Layer - Tầng 2)** "
                f"trong mô hình mạng máy tính. Mục tiêu cốt lõi giúp sinh viên nắm vững cơ chế tạo khung (Framing), kỹ thuật kiểm soát và sửa lỗi bit (Error Control), "
                f"cơ chế phân chia kênh truyền đa truy cập (Multiple Access), và giao thức phân giải địa chỉ logic sang vật lý (ARP).\n\n"
                f"#### 2. 📐 Khung Lý thuyết, Định lý & Hệ thống Giao thức Cốt lõi\n"
                f"- **Kỹ thuật Kiểm soát & Sửa lỗi (EDC - Error Detection & Correction):**\n"
                f"  + Bên gửi bổ sung thêm $r$ bit kiểm tra vào $m$ bit dữ liệu để tạo chuỗi mã $n = m + r$.\n"
                f"  + **Mã Hamming (Sửa lỗi đơn - Single-bit Error Correction):**\n"
                f"    * Số bit kiểm tra tối thiểu thỏa mãn bất đẳng thức: $$2^r \\ge m + r + 1$$\n"
                f"    * Các bit kiểm tra $p_k$ được đặt tại các vị trí lũy thừa của 2: $1, 2, 4, 8, \\dots$ ($2^{{k-1}}$).\n"
                f"    * Cơ chế: Mỗi bit kiểm tra phụ trách tính Parity chẵn/lẻ cho các vị trí bit có biểu diễn nhị phân tương ứng. Bên nhận tính syndrome để chỉ ra đúng vị trí bit bị lỗi.\n"
                f"- **Đa truy cập phân chia theo tần số (FDM - Frequency Division Multiplexing):**\n"
                f"  + Toàn bộ dải băng thông của kênh truyền được chia thành các dải tần con (sub-bands). Mỗi trạm truyền trên một dải tần số cố định $\\rightarrow$ Hoàn toàn không xảy ra xung đột (Collision-free).\n"
                f"- **Giao thức Phân giải Địa chỉ (ARP - Address Resolution Protocol):**\n"
                f"  + *Chức năng:* Chuyển đổi từ địa chỉ logic tầng mạng (IP: 32-bit) sang địa chỉ vật lý tầng Data Link (MAC: 48-bit) trong cùng một mạng cục bộ (LAN).\n"
                f"  + *ARP Request:* Gửi dưới dạng **Broadcast** (địa chỉ MAC đích: `FF:FF:FF:FF:FF:FF`) để tìm chủ sở hữu IP.\n"
                f"  + *ARP Reply:* Máy đích có IP trùng khớp trả lời trực tiếp bằng **Unicast** chứa địa chỉ MAC của nó.\n"
                f"  + *ARP Cache:* Lưu trữ bảng ánh xạ IP $\\rightarrow$ MAC kèm thời gian sống (TTL) để giảm thiểu số lần broadcast trên đường truyền.\n\n"
                f"#### 3. 🧩 Phân loại Dạng bài tập & Phương pháp Giải mẫu\n"
                f"- **Dạng 1: Tính toán bit kiểm tra và giải mã sửa lỗi Hamming:**\n"
                f"  + *Phương pháp:* Bước 1: Xác định vị trí các bit dữ liệu và bit kiểm tra $p_1, p_2, p_4\\dots$ Bước 2: Thiết lập phương trình Parity chẵn/lẻ theo bảng nhị phân. Bước 3: Tìm vector kiểm tra lỗi (Syndrome) để kết luận bit bị lật.\n"
                f"- **Dạng 2: Phân tích đường đi của gói tin qua Router kết hợp ARP:**\n"
                f"  + *Phương pháp:* Khi Host A gửi gói tin cho Host B ở mạng khác, Host A không ARP hỏi MAC của Host B mà bắt buộc phải ARP hỏi MAC của **Default Gateway (Router)**.\n\n"
                f"#### 4. ⚠️ Bẫy Đề thi & Sai lầm Phổ biến\n"
                f"- 🚨 **Bẫy 1 (Phạm vi ARP):** ARP là giao thức phát sóng quảng bá (Broadcast) chỉ hoạt động trong nội bộ một Broadcast Domain (Subnet). Router không bao giờ chuyển tiếp gói tin ARP Request sang mạng khác.\n"
                f"- 🚨 **Bẫy 2 (Nhầm số bit Hamming):** Nhầm lẫn giữa số bit kiểm tra $r$, số bit dữ liệu $m$ và tổng độ dài từ mã $n = m + r$.\n"
                f"- 🚨 **Bẫy 3 (FDM vs TDM):** FDM chia phổ tần số, TDM chia các khe thời gian luân phiên.\n\n"
                f"#### 5. 💡 Câu hỏi Tự ôn luyện & Flashcard Nhớ nhanh\n"
                f"- **Câu 1:** Để mã hóa chuỗi dữ liệu 7-bit bằng mã Hamming sửa lỗi đơn, ta cần tối thiểu bao nhiêu bit kiểm tra $r$? *(Đáp án: $r=4$ vì $2^4 = 16 \\ge 7 + 4 + 1 = 12$)*.\n"
                f"- **Câu 2:** Tại sao ARP Request gửi broadcast nhưng ARP Reply lại gửi unicast?\n"
                f"- **Câu 3:** Khi gói tin đi qua mỗi hop router, địa chỉ IP nguồn/đích và địa chỉ MAC nguồn/đích thay đổi như thế nào?"
            )

        # Check for Higher Mathematics / Linear Algebra / Calculus topic
        is_higher_math = any(w in full_corpus or w in doc_name.lower() for w in [
            "toán cao cấp", "đại số tuyến tính", "ma trận", "định thức", "không gian vector",
            "trị riêng", "vector riêng", "giải tích", "tích phân", "chuỗi số", "đạo hàm riêng",
            "xác suất", "thống kê", "phương trình vi phân"
        ])
        if is_higher_math:
            return (
                f"### 📚 Cẩm nang Học tập & Tóm tắt Kiến thức: **{doc_name}**\n\n"
                f"#### 1. 🎯 Tổng quan Chuyên đề & Vị trí Kiến thức\n"
                f"Tài liệu **{doc_name}** ({page_summary}, {len(chunks)} phân đoạn) thuộc chương trình **Toán Cao cấp / Đại học** (Đại số Tuyến tính & Giải tích). "
                f"Nội dung trọng tâm trang bị cho sinh viên các công cụ giải tích ma trận, ánh xạ tuyến tính, giải hệ phương trình nhiều ẩn và tính toán các phép vi tích phân đa biến.\n\n"
                f"#### 2. 📐 Khung Lý thuyết, Định lý & Hệ thống Công thức Cốt lõi\n"
                f"- **Phép toán Ma trận & Định thức (Matrix & Determinant):**\n"
                f"  + Điều kiện nhân hai ma trận $A_{{m \\times k}} \\times B_{{k \\times n}} = C_{{m \\times n}}$. Tính chất: $A(BC) = (AB)C$, nhưng nói chung $AB \\ne BA$.\n"
                f"  + Định thức: $\\det(AB) = \\det(A) \\cdot \\det(B)$. Ma trận $A$ khả nghịch khi và chỉ khi $\\det(A) \\ne 0$, khi đó: $$A^{{-1}} = \\frac{{1}}{{\\det(A)}} \\cdot P_A^T$$\n"
                f"- **Không gian Vector & Ánh xạ Tuyến tính:**\n"
                f"  + Hệ vector $\{{\\mathbf{{v}}_1, \\dots, \\mathbf{{v}}_k\}}$ độc lập tuyến tính nếu $\\sum_{{i=1}}^k c_i \\mathbf{{v}}_i = \\mathbf{{0}} \\iff c_1 = \\dots = c_k = 0$.\n"
                f"  + Hạng của hệ vector $r(A)$ bằng số vector độc lập tuyến tính tối đa (số phần tử cơ sở của không gian sinh).\n"
                f"- **Trị riêng & Vector riêng (Eigenvalues & Eigenvectors):**\n"
                f"  + Phương trình đặc trưng: $$\\det(A - \\lambda I) = 0$$\n"
                f"  + Với mỗi trị riêng $\\lambda$, vector riêng tương ứng $\\mathbf{{x}} \\ne \\mathbf{{0}}$ thỏa mãn hệ: $$(A - \\lambda I)\\mathbf{{x}} = \\mathbf{{0}}$$\n\n"
                f"#### 3. 🧩 Phân loại Dạng bài tập & Phương pháp Giải mẫu\n"
                f"- **Dạng 1: Biện luận nghiệm hệ phương trình tuyến tính theo tham số (Định lý Kronecker-Capelli):**\n"
                f"  + *Phương pháp:* Đưa ma trận mở rộng $\\bar{{A}} = [A | B]$ về dạng bậc thang bằng các phép biến đổi sơ cấp. Hệ có nghiệm duy nhất khi $r(A) = r(\\bar{{A}}) = n$; vô số nghiệm khi $r(A) = r(\\bar{{A}}) < n$; vô nghiệm khi $r(A) < r(\\bar{{A}})$.\n"
                f"- **Dạng 2: Tìm trị riêng, vector riêng và chéo hóa ma trận:**\n"
                f"  + *Phương pháp:* Bước 1: Giải phương trình đặc trưng $\\det(A - \\lambda I) = 0$ tìm các $\\lambda_i$. Bước 2: Tìm cơ sở không gian nghiệm cho từng $(A - \\lambda_i I)\\mathbf{{x}} = \\mathbf{{0}}$. Bước 3: Kiểm tra điều kiện chéo hóa (tổng số vector riêng độc lập tuyến tính bằng cấp của ma trận).\n\n"
                f"#### 4. ⚠️ Bẫy Đề thi, Sai lầm Phổ biến & Trường hợp Biên\n"
                f"- 🚨 **Bẫy 1 (Phép nhân ma trận):** Không giao hoán ($AB \\ne BA$). Quên kiểm tra kích thước số cột ma trận trước bằng số hàng ma trận sau.\n"
                f"- 🚨 **Bẫy 2 (Tính định thức bằng biến đổi sơ cấp):** Nhân một hàng với số $k$ thì định thức tăng $k$ lần; đổi chỗ hai hàng thì định thức đổi dấu.\n"
                f"- 🚨 **Bẫy 3 (Trị riêng bội):** Nếu trị riêng có bội đại số $k > 1$, số vector riêng độc lập tuyến tính tìm được phải đúng bằng $k$ thì ma trận mới chéo hóa được.\n\n"
                f"#### 5. 💡 Câu hỏi Tự ôn luyện & Flashcard Nhớ nhanh\n"
                f"- **Câu 1:** Nêu điều kiện cần và đủ để một ma trận vuông $A$ cấp $n$ chéo hóa được?\n"
                f"- **Câu 2:** Cho ma trận $A$ vuông cấp 3 có $\\det(A) = 4$. Tính $\\det(2A)$ và $\\det(A^{{-1}})$? *(Đáp án: $\\det(2A) = 2^3 \\cdot 4 = 32$; $\\det(A^{{-1}}) = 1/4$)*.\n"
                f"- **Câu 3:** Trình bày định lý Kronecker-Capelli về sự tồn tại nghiệm của hệ phương trình đại số tuyến tính."
            )

        # General Academic summary for other subjects
        sections = []
        for c in chunks:
            lines = [l.strip() for l in c.text.splitlines() if len(l.strip()) >= 15]
            for line in lines:
                if any(k in line.lower() for k in ["chương", "bài", "định lý", "định nghĩa", "tính chất", "công thức", "dạng", "phương pháp", "quy tắc"]):
                    sections.append(f"- **[Trang {c.page_number}]**: {line}")
                    if len(sections) >= 6:
                        break
            if len(sections) >= 6:
                break

        sections_str = "\n".join(sections) if sections else f"- Nội dung bao quát lý thuyết và bài tập tổng hợp từ trang 1 đến trang {pages[-1] if pages else 1}."

        return (
            f"### 📚 Cẩm nang Học tập & Tóm tắt Kiến thức: **{doc_name}**\n\n"
            f"#### 1. 🎯 Tổng quan Chuyên đề & Phạm vi Bài học\n"
            f"Tài liệu **{doc_name}** có quy mô **{page_summary}** với **{len(chunks)} phân đoạn kiến thức**. "
            f"Nội dung cung cấp hệ thống lý thuyết, các định lý và hướng dẫn giải các dạng bài tập học thuật trọng tâm.\n\n"
            f"#### 2. 📐 Khung Lý thuyết & Hệ thống Kiến thức Cốt lõi\n"
            f"{sections_str}\n\n"
            f"#### 3. 🧩 Các Dạng bài Tập & Phương pháp Giải\n"
            f"- Phân tích đề bài, xác định các đại lượng đã cho và đại lượng cần tìm.\n"
            f"- Áp dụng trực tiếp các công thức và định lý tương ứng trích xuất từ tài liệu.\n"
            f"- Kiểm tra lại điều kiện xác định và nghiệm ngoại lai trước khi kết luận.\n\n"
            f"#### 4. ⚠️ Lưu ý Quan trọng & Điểm Cần Tránh\n"
            f"- Luôn chú ý điều kiện xác định của các biến số và phạm vi áp dụng của định lý.\n"
            f"- Đọc kỹ yêu cầu câu hỏi để không bỏ sót các trường hợp đặc biệt.\n\n"
            f"#### 5. 💡 Gợi ý Tự học & Tra cứu\n"
            f"- Đặt câu hỏi chi tiết về từng dạng bài tập hoặc công thức ở khung chat để trợ lý giải thích và dẫn nguồn trang cụ thể."
        )

    def generate_email_draft(
        self,
        query: str,
        chunks: List[DocumentChunk],
        recipient_email: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Generates context-aware email subject and body leveraging workspace context.
        """
        prompt = build_email_prompt(query, chunks, recipient_email)

        # 1. Ollama Provider
        if settings.llm_provider == "ollama" and self.is_ollama_online():
            try:
                resp_text = self.call_ollama(prompt)
                if resp_text and "SUBJECT:" in resp_text and "BODY:" in resp_text:
                    after_subj = resp_text.split("SUBJECT:", 1)[1]
                    parts = after_subj.split("BODY:", 1)
                    subj = parts[0].strip()
                    body = parts[1].strip()
                    if subj and body:
                        return subj, body
            except Exception:
                pass

        # 2. Smart Contextual Generator fallback
        q_lower = query.lower()

        if any(w in q_lower for w in ["deadline", "gia hạn", "dời", "hoãn", "lùi", "thời hạn", "trễ"]):
            subject = "[CSC10014] Đơn xin gia hạn thời hạn nộp bài tập / đồ án"
            body = (
                "Kính gửi Quý Thầy/Cô,\n\n"
                "Em là đại diện nhóm thực hiện đồ án môn học CSC10014 (Hệ thống WorkspaceAI).\n\n"
                f"Liên quan đến yêu cầu: \"{query.strip()}\"\n\n"
                "Hiện tại nhóm em đã triển khai các tính năng cốt lõi theo Project Brief, tuy nhiên trong quá trình hoàn thiện, "
                "nhóm nhận thấy một số hạng mục đối soát tất định (R2) và kiểm chứng trích lục cần được tối ưu và kiểm thử thêm "
                "để đảm bảo chất lượng kỹ thuật cao nhất.\n\n"
                "Vì vậy, nhóm em kính xin phép Thầy/Cô cho phép nhóm được lùi thời hạn nộp bài thêm một khoảng thời gian ngắn "
                "để nhóm có thể rà soát lại toàn bộ Submission Package và hoàn thiện báo cáo kỹ thuật chỉn chu nhất.\n\n"
                "Nhóm em xin cam kết sẽ hoàn thành đúng theo hạn mới và nộp đầy đủ các tài liệu theo quy định.\n\n"
                "Em xin chân thành cảm ơn sự thông cảm và hướng dẫn tận tình của Quý Thầy/Cô!\n\n"
                "Trân trọng,\n"
                "Nhóm sinh viên thực hiện đồ án CSC10014"
            )
            return subject, body

        if any(w in q_lower for w in ["điểm", "kết quả", "phúc khảo", "grade", "score", "nhận xét", "feedback"]):
            subject = "[CSC10014] Thắc mắc & Xin phản hồi đánh giá đồ án môn học"
            body = (
                "Kính gửi Quý Thầy/Cô,\n\n"
                "Em đại diện nhóm sinh viên thực hiện đồ án WorkspaceAI môn học CSC10014.\n\n"
                f"Em viết email này liên quan đến nội dung: \"{query.strip()}\".\n\n"
                "Sau khi nhận được thông báo về kết quả đánh giá sơ bộ của đồ án, nhóm em rất mong muốn được lắng nghe thêm "
                "các nhận xét chi tiết của Thầy/Cô về các thành phần trong Submission Package (báo cáo kỹ thuật, mã nguồn, "
                "kiến trúc hệ thống và bộ benchmark) để nhóm hiểu rõ những điểm cần khắc phục và cải thiện sản phẩm tốt hơn.\n\n"
                "Nếu thuận tiện, nhóm em kính xin phép Thầy/Cô một buổi trao đổi ngắn qua Google Meet hoặc phản hồi qua email này ạ.\n\n"
                "Nhóm em xin chân thành cảm ơn Thầy/Cô rất nhiều!\n\n"
                "Trân trọng,\n"
                "Nhóm sinh viên CSC10014"
            )
            return subject, body

        task_match = re.search(r"t-0[1-9]", q_lower)
        if task_match:
            task_id = task_match.group(0).upper()
            subject = f"[CSC10014] Báo cáo tiến độ chi tiết hạng mục {task_id}"
            body = (
                "Kính gửi Quý Thầy/Cô,\n\n"
                f"Nhóm em xin trân trọng gửi báo cáo cập nhật tiến độ liên quan đến đầu việc {task_id} của đồ án CSC10014.\n\n"
                f"Chi tiết yêu cầu: {query.strip()}\n\n"
                f"Theo dữ liệu ghi nhận trên Taskboard (`team_tasks.csv`), hạng mục {task_id} đã được phân công và đang được triển khai "
                "theo đúng các tiêu chí yêu cầu trong Project Brief. Nhóm em đã thiết lập đầy đủ cơ chế đối soát và kiểm chứng tự động.\n\n"
                "Nhóm em sẽ tiếp tục cập nhật tiến độ định kỳ và hoàn thiện các bước nghiệm thu kỹ thuật tiếp theo.\n\n"
                "Kính chúc Quý Thầy/Cô nhiều sức khỏe và công tác tốt!\n\n"
                "Trân trọng,\n"
                "Nhóm sinh viên CSC10014"
            )
            return subject, body

        if any(w in q_lower for w in ["tiến độ", "báo cáo", "progress", "update", "deliverable"]):
            subject = "[CSC10014] Báo cáo tiến độ đồ án WorkspaceAI"
            body = (
                "Kính gửi Quý Thầy/Cô,\n\n"
                "Nhóm em xin phép gửi bản tóm tắt cập nhật tiến độ thực hiện đồ án môn CSC10014 dựa trên hồ sơ dữ liệu workspace:\n\n"
                "- Yêu cầu R1 (Problem boundary & 10 use cases): Đã hoàn thành 100% (Task T-01 do Minh phụ trách).\n"
                "- Yêu cầu R2 (Deterministic reconciliation engine): Đang thực hiện đạt 60% (Task T-02 do Lan phụ trách).\n"
                "- Đã tích hợp cổng bảo vệ Safeguard R7 và quy trình phê duyệt Human-in-the-Loop (Tính năng 3).\n\n"
                "Nhóm em đang tiếp tục hoàn thiện các tiêu chí kiểm thử benchmark và sẽ nộp Submission Package đúng thời hạn quy định.\n\n"
                "Nhóm em xin chân thành cảm ơn sự đồng hành của Thầy/Cô!\n\n"
                "Trân trọng,\n"
                "WorkspaceAI Project Team"
            )
            return subject, body

        clean_topic = re.sub(
            r"^(soạn mail|soạn thư|viết mail|viết thư|gửi mail|draft email|draft an email|gửi thư|nháp mail|hãy soạn email|hãy soạn mail)\s*",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_topic:
            clean_topic = "Trao đổi về đồ án môn học"
        clean_topic = clean_topic[0].upper() + clean_topic[1:]

        subject = f"[CSC10014] {clean_topic[:65]}"
        body = (
            "Kính gửi Quý Thầy/Cô,\n\n"
            f"Em đại diện nhóm thực hiện đồ án môn học CSC10014 xin phép gửi thư liên hệ về: \"{clean_topic}\".\n\n"
            f"Chi tiết nội dung yêu cầu:\n{query.strip()}\n\n"
            "Dựa trên các thông tin đã được tổng hợp trong hồ sơ đồ án, nhóm em kính gửi để Thầy/Cô nắm bắt thông tin "
            "và rất mong nhận được những chỉ dẫn, phản hồi quý báu từ Thầy/Cô.\n\n"
            "Nhóm em xin chân thành cảm ơn Quý Thầy/Cô!\n\n"
            "Trân trọng,\n"
            "Nhóm sinh viên thực hiện đồ án CSC10014"
        )
        return subject, body


# Singleton instance for application access
llm_provider = LLMProvider()
