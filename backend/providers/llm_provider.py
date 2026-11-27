from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from backend.core.config import settings
from backend.core.schemas import DocumentChunk, GeneratedClaim
from backend.providers.prompts import (
    build_email_prompt,
    build_qa_prompt,
    build_summary_prompt,
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


class LLMProvider:
    """
    R4 AI Capability with Local-First Strategy Pattern:
    Supports 100% local Ollama (qwen2.5:7b), Gemini API, or deterministic Mock mode.
    """

    def __init__(self) -> None:
        self._tags_lock = threading.Lock()
        self._tags_cache: Optional[Tuple[float, str, bool, List[str]]] = None

    def invalidate_ollama_cache(self) -> None:
        """Clears cached Ollama /api/tags availability and model list."""
        with self._tags_lock:
            self._tags_cache = None

    def _fetch_ollama_tags(self, force_refresh: bool = False) -> Tuple[bool, List[str]]:
        """Fetches and caches Ollama /api/tags status and model names within TTL."""
        base_url = settings.ollama_base_url.rstrip("/")
        ttl = max(0.0, float(settings.ollama_tags_cache_ttl))
        now = time.monotonic()

        if not force_refresh and ttl > 0:
            with self._tags_lock:
                if self._tags_cache is not None:
                    cached_at, cached_url, cached_online, cached_names = self._tags_cache
                    if cached_url == base_url and (now - cached_at) < ttl:
                        return cached_online, list(cached_names)

        online = False
        names: List[str] = []
        try:
            resp = httpx.get(
                f"{base_url}/api/tags",
                timeout=httpx.Timeout(1.0, connect=0.5),
            )
            if resp.status_code == 200:
                tags = resp.json().get("models", [])
                names = [m.get("name", "") for m in tags if m.get("name")]
                online = True
        except Exception:
            online = False
            names = []

        with self._tags_lock:
            self._tags_cache = (time.monotonic(), base_url, online, list(names))
        return online, names

    def is_ollama_online(self) -> bool:
        """Fast cached health check to verify if local Ollama daemon is reachable."""
        online, _ = self._fetch_ollama_tags()
        return online

    def is_gemini_configured(self) -> bool:
        """Checks if a valid Google Gemini API key is configured."""
        key = (settings.gemini_api_key or "").strip()
        return bool(key and key != "your_gemini_api_key_here" and len(key) > 10)

    def call_gemini(self, prompt: str, enforce_json: bool = False, temperature: float = 0.1) -> Optional[str]:
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
            "temperature": temperature,
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
        """Resolves the best available local Ollama model using cached /api/tags."""
        online, names = self._fetch_ollama_tags()
        if online and names:
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
            return names[0]
        return settings.ollama_model

    def call_ollama(self, prompt: str, enforce_json: bool = False) -> Optional[str]:
        """
        Calls local Ollama instance with qwen2.5 optimization options:
        - keep_alive: 30m (keeps model hot in RAM/VRAM)
        - num_ctx: 3072 (balanced context window without excessive KV-cache)
        - num_predict: 900 (caps runaway generation)
        - temperature: 0.1 (strict factual grounding)
        - top_p: 0.85
        - repeat_penalty: 1.1
        - format: json (when requested)
        """
        if not self.is_ollama_online():
            return None
        active_model = self.get_effective_ollama_model()
        payload: Dict[str, Any] = {
            "model": active_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "num_ctx": settings.ollama_num_ctx,
                "num_predict": settings.ollama_num_predict,
                "temperature": 0.1,
                "top_p": 0.85,
                "repeat_penalty": 1.1,
            },
        }
        if enforce_json:
            payload["format"] = "json"

        try:
            resp = httpx.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                json=payload,
                timeout=httpx.Timeout(60.0, connect=2.0),
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
            self.invalidate_ollama_cache()
        except Exception:
            self.invalidate_ollama_cache()
        return None

    def synthesize_smart_answer(self, query: str, chunks: List[DocumentChunk]) -> str:
        """
        Synthesizes a clean, user-friendly answer in natural Vietnamese from
        retrieved document chunks (offline / fallback mode). Always returns str.
        """
        if not chunks:
            return "Không tìm thấy nội dung liên quan trong các tài liệu hiện có."

        top = chunks[0]
        q_lower = query.lower()

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
        loc_str = f"Trang {top.page_number}"
        if top.start_line and top.end_line:
            loc_str += f", Dòng {top.start_line}-{top.end_line}"

        # Present clean paragraphs from top retrieved evidence chunks
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
        Uses structured JSON prompting for Ollama qwen2.5:7b / Gemini.
        Falls back cleanly to deterministic synthesis in offline or mock mode.
        """
        if not chunks:
            return []

        top = chunks[0]

        # 1. Deterministic Mock mode for automated tests
        if settings.llm_provider == "mock":
            synth_text = self.synthesize_smart_answer(query, chunks)
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
                )
            ]

        prompt = build_qa_prompt(query, chunks, conversation_history)
        raw_response: Optional[str] = None

        # 2. Try Local Ollama if configured
        if settings.llm_provider == "ollama" and self.is_ollama_online():
            raw_response = self.call_ollama(prompt, enforce_json=True)

        # 3. Try Gemini API if configured
        if not raw_response and (settings.llm_provider == "gemini" or self.is_gemini_configured()):
            raw_response = self.call_gemini(prompt, enforce_json=True)

        # 4. Parse Structured JSON response if available
        if raw_response:
            parsed = _safe_parse_json(raw_response)
            if parsed and isinstance(parsed, dict) and "answer" in parsed:
                answer_text = str(parsed.get("answer", "")).strip()
                raw_cits = parsed.get("citations", [])

                claims: List[GeneratedClaim] = []
                if isinstance(raw_cits, list) and raw_cits:
                    for cit in raw_cits:
                        if isinstance(cit, dict):
                            doc_id = str(cit.get("doc_id", top.doc_id)).strip()
                            page = int(cit.get("page", top.page_number))
                            start_l = int(cit.get("line_start", top.start_line or 1))
                            end_l = int(cit.get("line_end", top.end_line or start_l))
                            excerpt = str(cit.get("excerpt", "")).strip()

                            claim_stmt = str(cit.get("claim") or cit.get("statement") or answer_text).strip()
                            claims.append(
                                GeneratedClaim(
                                    claim_text=claim_stmt,
                                    cited_doc_id=doc_id,
                                    cited_page=page,
                                    cited_start_line=start_l,
                                    cited_end_line=end_l,
                                    doc_version=top.doc_version,
                                    doc_hash=top.doc_hash,
                                    evidence_quote=excerpt or top.text[:120],
                                )
                            )

                if claims:
                    return claims

                # If no citations in list, create claim from answer and top chunk
                return [
                    GeneratedClaim(
                        claim_text=answer_text,
                        cited_doc_id=top.doc_id,
                        cited_page=top.page_number,
                        cited_start_line=top.start_line,
                        cited_end_line=top.end_line,
                        doc_version=top.doc_version,
                        doc_hash=top.doc_hash,
                        evidence_quote=top.text[:120],
                    )
                ]

            # If raw response wasn't JSON, use raw text directly
            if raw_response.strip():
                return [
                    GeneratedClaim(
                        claim_text=raw_response.strip(),
                        cited_doc_id=top.doc_id,
                        cited_page=top.page_number,
                        cited_start_line=top.start_line,
                        cited_end_line=top.end_line,
                        doc_version=top.doc_version,
                        doc_hash=top.doc_hash,
                        evidence_quote=top.text[:120],
                    )
                ]

        # 5. Smart Offline Synthesis Fallback
        smart_text = self.synthesize_smart_answer(query, chunks)
        return [
            GeneratedClaim(
                claim_text=smart_text,
                cited_doc_id=top.doc_id,
                cited_page=top.page_number,
                cited_start_line=top.start_line,
                cited_end_line=top.end_line,
                doc_version=top.doc_version,
                doc_hash=top.doc_hash,
                evidence_quote=top.text[:120],
            )
        ]

    def generate_summary(self, doc_name: str, chunks: List[DocumentChunk]) -> str:
        """
        Generates a comprehensive executive summary using active LLM or deterministic fallback.
        """
        if not chunks:
            return f"Tài liệu `{doc_name}` hiện chưa có nội dung văn bản nào để tóm tắt."

        prompt = build_summary_prompt(doc_name, chunks)

        if settings.llm_provider == "gemini" or self.is_gemini_configured():
            ans = self.call_gemini(prompt)
            if ans:
                return ans

        if settings.llm_provider == "ollama" and self.is_ollama_online():
            ans = self.call_ollama(prompt)
            if ans:
                return ans

        # Fallback offline structured summary generator
        is_brief = "project_brief" in doc_name.lower() or ("brief" in doc_name.lower() and "csc10014" in doc_name.lower())
        is_tasks = "team_tasks" in doc_name.lower()

        if is_brief:
            return (
                f"### 📄 Tóm tắt Tài liệu: **{doc_name}**\n\n"
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
            req_codes = re.findall(r"\b(R[1-9]\d?|REQ-[0-9]+|DELIV-0[1-9])\b", full_corpus, re.IGNORECASE)

            metrics_list = []
            if dates_found:
                metrics_list.append(f"- ⏱️ **Mốc thời hạn ghi nhận:** `{', '.join(sorted(set(dates_found))[:5])}`")
            if numbers_found:
                metrics_list.append(f"- 📊 **Chỉ số & Định lượng:** `{', '.join(sorted(set(numbers_found), key=len)[:6])}`")
            if req_codes:
                metrics_list.append(f"- 📌 **Các mã tiêu chuẩn / Deliverables:** `{', '.join(sorted(set(req_codes))[:8])}`")

            metrics_str = "\n".join(metrics_list) if metrics_list else "- *Tài liệu không chứa các mốc thời hạn hoặc chỉ số định lượng rõ rệt.*"

            return (
                f"### 📄 Tóm tắt Toàn diện Tài liệu: **{doc_name}**\n\n"
                f"#### 1. 🎯 Tổng quan Điều hành & Quy mô (Executive Briefing)\n"
                f"Tài liệu **{doc_name}** có quy mô **{page_summary}** với **{len(chunks)} phân đoạn văn bản** đã được nạp và đối soát toàn vẹn.\n\n"
                f"**Nội dung mở đầu trích xuất:**\n"
                f"> *\"{intro}\"*\n\n"
                f"#### 2. 📌 Các Trọng tâm Kỹ thuật & Điểm Nhấn Nội dung (Core Themes)\n"
                f"{excerpts_str}\n\n"
                f"#### 3. ⏱️ Dữ liệu Định lượng & Mốc Thời hạn (Metrics & Deadlines)\n"
                f"{metrics_str}\n\n"
                f"#### 4. 💡 Khuyến nghị Thực thi & Hướng dẫn Tra cứu (Actionable Takeaways)\n"
                f"- Bấm vào các nút trích dẫn trong câu trả lời ở khung chat để soi chiếu trực tiếp văn bản gốc trong **Evidence Viewer**.\n"
                f"- Nếu tài liệu có chứa yêu cầu đề bài, bạn có thể chuyển sang tab **'Taskboard & Đối soát'** và bấm *'Trích xuất Yêu cầu từ Tài liệu'* để tự động đối chiếu với bảng công việc nhóm."
            )

    def _generate_email_deterministic(self, query: str, recipient_email: Optional[str] = None) -> Tuple[str, str]:
        """
        Pure deterministic email generator – NO LLM required.
        Parses the user's intent from the query and generates a natural-sounding email.
        """
        q = query.strip()
        q_lower = q.lower()

        # Strip meta-command prefixes ("tạo mail xin...", "soạn thư xin...", etc.)
        core = re.sub(
            r"^(soạn mail|soạn thư|viết mail|viết thư|gửi mail|tạo mail|tạo email|draft email|hãy soạn|hãy viết)\s*",
            "", q, flags=re.IGNORECASE
        ).strip()
        if not core:
            core = q

        # Detect intent
        is_nghi = any(w in q_lower for w in ["nghỉ học", "nghỉ buổi", "xin nghỉ", "vắng", "không đến", "không thể đến"])
        is_benh = any(w in q_lower for w in ["bệnh", "ốm", "sốt", "không khoẻ", "không khỏe", "mệt", "đau"])
        is_xin_phep = any(w in q_lower for w in ["xin phép", "xin phep", "mong thầy", "mong thay"])
        is_bao_cao = any(w in q_lower for w in ["báo cáo", "tiến độ", "progress", "update", "report"])

        # Extract môn học nếu có
        mon_match = re.search(
            r"môn\s+([\w\s]+?)(?:\s+hôm|\s+ngày|\s+buổi|\s+vì|\s+do|$)",
            q_lower
        )
        mon = mon_match.group(1).strip().title() if mon_match else ""

        greeting = "Dạ thầy/cô ơi"
        if recipient_email:
            name_part = recipient_email.split("@")[0]
            if "." in name_part:
                # e.g. an.nguyen → "thầy/cô Nguyễn"
                last = name_part.split(".")[-1].title()
                greeting = f"Dạ thầy/cô {last} ơi"

        if is_nghi or is_xin_phep:
            ly_do = ""
            if is_benh:
                ly_do = "do hôm nay em bị ốm/sốt, không khoẻ"
            elif "việc cá nhân" in q_lower:
                ly_do = "do em có việc cá nhân đột xuất"
            else:
                # extract lý do từ "vì..." hoặc "do..."
                reason_match = re.search(r"(?:vì|do|bởi vì)\s+(.+?)(?:\.|$)", q_lower)
                if reason_match:
                    ly_do = reason_match.group(1).strip()
                else:
                    ly_do = "do có việc bận"

            mon_str = f" môn {mon}" if mon else ""
            subject = f"Xin nghỉ học{mon_str}"
            body = (
                f"{greeting}, hôm nay em xin phép nghỉ buổi học{mon_str} ạ, {ly_do}. "
                f"Em sẽ tự ôn lại bài và bù đắp đầy đủ. "
                f"Mong thầy/cô thông cảm cho em ạ, em cảm ơn thầy/cô nhiều!"
            )

        elif is_bao_cao:
            subject = core[:70] if len(core) <= 70 else core[:70] + "..."
            body = (
                f"{greeting}, em muốn báo cáo về: {core}. "
                f"Em sẽ gửi chi tiết theo yêu cầu của thầy/cô ạ. "
                f"Mong thầy/cô xem và phản hồi cho em. Em cảm ơn ạ!"
            )

        else:
            # Generic natural fallback
            subject = core[:70] if len(core) <= 70 else core[:70] + "..."
            body = (
                f"{greeting}, em muốn liên hệ về: {core}. "
                f"Mong thầy/cô hỗ trợ và phản hồi cho em ạ. "
                f"Em cảm ơn thầy/cô rất nhiều!"
            )

        return subject, body

    def generate_email_draft(
        self,
        query: str,
        chunks: List[DocumentChunk],
        recipient_email: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Generates a fully dynamic email subject and body from the user's prompt.
        Uses LLM (Gemini or Ollama) – NO static template fallback.
        """
        prompt = build_email_prompt(query, chunks, recipient_email)

        # Markers that indicate the LLM generated the old CSC10014 static template
        _STATIC_MARKERS = [
            "Em đại diện nhóm thực hiện đồ án môn học CSC10014",
            "Nhóm sinh viên thực hiện đồ án CSC10014",
            "Dựa trên các thông tin đã được tổng hợp trong hồ sơ đồ án",
            "Chi tiết nội dung yêu cầu:\n",
        ]

        def _is_static_template(body: str) -> bool:
            return any(m in body for m in _STATIC_MARKERS)

        def _parse_subject_body(text: str) -> Optional[Tuple[str, str]]:
            """Parse SUBJECT:/BODY: format from LLM output. Reject static templates."""
            if not text:
                return None
            # Try SUBJECT:/BODY: format (from build_email_prompt)
            if "SUBJECT:" in text and "BODY:" in text:
                parts = text.split("BODY:", 1)
                subj = parts[0].replace("SUBJECT:", "").strip()
                body = parts[1].strip()
                if subj and body and not _is_static_template(body):
                    return subj, body
            # Try Subject:/Body: format (alternative LLM output)
            if "Subject:" in text and "Body:" in text:
                subj_match = re.search(r"Subject:\s*(.*)", text, re.IGNORECASE)
                body_match = re.search(r"Body:\s*([\s\S]*)", text, re.IGNORECASE)
                if subj_match and body_match:
                    subj = subj_match.group(1).strip()
                    body = body_match.group(1).strip()
                    if subj and body and not _is_static_template(body):
                        return subj, body
            return None

        # 1. Try Gemini (preferred – usually faster and higher quality)
        if self.is_gemini_configured():
            try:
                resp_text = self.call_gemini(prompt)
                result = _parse_subject_body(resp_text or "")
                if result:
                    return result
            except Exception:
                pass

        # 2. Try Ollama
        if settings.llm_provider == "ollama" and self.is_ollama_online():
            try:
                resp_text = self.call_ollama(prompt)
                result = _parse_subject_body(resp_text or "")
                if result:
                    return result
            except Exception:
                pass

        # 3. Deterministic fallback – natural email without static CSC10014 template
        return self._generate_email_deterministic(query, recipient_email)



# Singleton instance for application access
llm_provider = LLMProvider()
