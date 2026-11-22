# F2-Q03 — Quiz Generation

Trạng thái: **DONE trong phạm vi Q03**. Ngày 2026-11-12, Asia/Bangkok. Map **FR2.03**, dùng contracts Q01 và nguồn đã chuẩn bị Q02. Chưa tích hợp study API/UI hoặc kiểm chứng semantic ở Q05.

## 1. Git, phạm vi tệp và preservation

```text
Branch: feat/f2-quiz-flashcards
HEAD/base: da40118de0adbda33c55200d30bd9915019d2619
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
Legacy: D:\Projects\WorkSpaceAI
Legacy branch/HEAD: feat/f2-document-task-management @ 730dc75f57a517adc322ec243fed66eaa47825b9
```

Tệp mới:

- `backend/services/f2_quiz_service.py`
- `backend/providers/f2_quiz_provider.py`
- `backend/algorithms/f2_quiz_generation.py`
- `tests/test_f2_quiz_generation.py`
- Báo cáo này.

Cập nhật `.skills/codebase_map.md`, `CHANGELOG.md`. Provider và thuật toán riêng được thêm để giữ nguyên provider QA/email và ranh giới stdlib của algorithms. Không sửa contracts/source layer/tests Q01–Q02, shared parser/repository, F1/F3, frontend, requirements/lockfiles hoặc database.

Không commit, push, merge, reset, clean, stash hoặc thay staging. HEAD/local main không đổi; tài liệu/code mới vẫn unstaged/untracked. Audit cuối Q03 đối chiếu hash Q01/Q02 và preservation legacy: branch/HEAD/status/index/staged+unstaged diff cùng manifest 511 tracked/untracked files giữ nguyên.

## 2. Luồng đã triển khai

```text
PreparedStudySources (Q02, trusted caller)
  -> revalidate selection + source snapshots / require Quiz format
  -> assign source aliases S1, S2, ...
  -> provider: deterministic offline OR explicitly configured Ollama
  -> parse strict JSON + validate individual questions
  -> resolve source_ids using backend snapshot
  -> drop invalid/duplicate questions + enforce requested count
  -> internal QuizSet + issues/source_issues/status
```

Interface chính:

```python
F2QuizService(provider=None, *, fallback_provider=None).generate_quiz(
    prepared: PreparedStudySources,
) -> QuizGenerationResult
```

Không có nguồn thì không gọi provider. Request format Flashcards bị từ chối ở service Quiz. Selection và SourceRefs được revalidate để không tin các instances đã bỏ qua validation bằng model_copy; nguồn ngoài selection, version/hash mâu thuẫn hoặc span sai bị chặn trước provider.

Đây là boundary cho dữ liệu nội bộ đã chuẩn bị, không phải cơ chế authentication/capability. Không nhận dict client chunks thay cho kết quả Q02 và không tự xác minh quyền workspace hoặc live document freshness.

### Provider contract và provenance

Provider nhận tuple `QuizEvidence(source_id, kind, source_ref)` và requested_count; trả string JSON có đúng root field `questions`. Mỗi item có đúng:

```json
{
  "question": "Nội dung câu hỏi",
  "options": [{"option_id": "A", "text": "Lựa chọn A"}, {"option_id": "B", "text": "Lựa chọn B"}],
  "correct_option_id": "A",
  "explanation": "Giải thích dựa trên nguồn",
  "source_ids": ["S1"]
}
```

Service gán question_id/quiz_set_id và gắn **nguyên SourceRef từ snapshot Q02**. Provider không được trả source_refs, doc/version/hash, question_id hoặc cờ verified; fields thừa bị từ chối. source_ids lạ/trùng, options/key/content không hợp lệ làm item bị bỏ với issue rõ ràng. Không sửa hoặc bịa citation để hợp thức hóa output.

Parser từ chối JSON sai, code fences/prose kèm theo, duplicate JSON keys, NaN/Infinity, root shape sai và response quá lớn. Question stems trùng sau gộp whitespace/casefold bị loại. Chỉ giữ tối đa requested_count; thiếu câu hợp lệ không được padding cho đủ 10.

### Offline default

`DeterministicQuizProvider` không gọi network. Thuật toán thuần stdlib nhận diện term–definition rõ ràng, dựng câu hỏi chọn khái niệm theo mô tả; các options là các thuật ngữ khác có trong nguồn.

- Mặc định count=10 lấy từ selection; explicit count được giữ.
- Sử dụng 2–4 options tùy nội dung sẵn có. Đây là cách triển khai adapter hiện tại, không thay contract Q01 thành bắt buộc 4 options.
- Loại term lặp có định nghĩa mâu thuẫn, term đồng nghĩa có cùng định nghĩa theo chuẩn hóa literal, và duplicate definitions.
- Không đủ hai định nghĩa phân biệt thì không tạo Quiz giả; trả insufficient. Có ít hơn count yêu cầu thì trả số câu thực tế và cảnh báo.
- Không sinh offline từ arbitrary fact/example/procedure. Những mẫu này cần provider phù hợp; không giả lập hiểu nghĩa để che thiếu dữ liệu.

Việc lọc mâu thuẫn/synonyms là literal heuristic, không phải semantic verifier. Câu hỏi/đáp án vẫn cần kiểm chứng Q05.

### Ollama adapter

`OllamaQuizProvider(base_url='http://localhost:11434', model='qwen2.5:7b', *, transport=None)` dùng endpoint `/api/generate`, `format='json'`, `stream=False`. HTTP read timeout 60s, connect timeout 2s; không theo redirect hoặc tự retry; giới hạn body phản hồi 1,000,000 bytes. Đây là cap kỹ thuật của transport/parser, không phải một giới hạn count sản phẩm đã được người dùng chốt.

Prompt đưa mỗi nguồn vào `<untrusted_document_data>` có source alias và nhãn dòng. Nội dung và attributes được HTML-escape để closing tags/role markup trong nguồn không thoát khung dữ liệu. Prompt yêu cầu một key đúng, giải thích có căn cứ, source_ids hợp lệ và trả ít câu hơn khi thiếu dữ liệu.

Timeout/unavailable/outer response sai/incomplete/oversized có typed error. Adapter **đã được kiểm thử với httpx.MockTransport; chưa gọi model thật hoặc đo chất lượng corpus**. Không đổi shared llm_provider/config và không tự chọn model fallback khác.

### Fallback, status và issues

Fallback chỉ chạy khi caller cấu hình `fallback_provider` và primary báo PROVIDER_TIMEOUT hoặc PROVIDER_UNAVAILABLE. Kết quả ghi FALLBACK_USED và provider_name thực tế; không dùng fallback để che invalid JSON/items. Mặc định service chỉ dùng offline provider, không tự liên hệ Ollama.

`QuizGenerationResult` là dataclass frozen với workspace_id, selection, quiz, provider_name, issues, source_issues, failed; `.status` và `.message` được suy ra:

| Status | Ý nghĩa thực tế |
| --- | --- |
| COMPLETE | Đủ số câu yêu cầu và không có issues; chỉ nói về cấu trúc/count, không nói semantic đã verified |
| PARTIAL | Có Quiz nhưng thiếu câu hoặc có generation/source/fallback warnings |
| INSUFFICIENT_CONTENT | Nguồn rỗng hoặc provider trả [] vì không tạo được câu phân biệt; quiz=None |
| ERROR | Provider/JSON lỗi hoặc mọi item đều invalid; quiz=None |

Original source_issues từ Q02 được giữ. Generated SourceRefs đều **UNVERIFIED**. Internal QuizSet chứa answer key và không phải learner DTO; không được đưa thẳng ra API trước submit/reveal.

## 3. Acceptance và kiểm thử thực tế

| Nhóm | Bằng chứng trong tests/test_f2_quiz_generation.py |
| --- | --- |
| Thành công/count | Offline 12 definitions tạo đúng 10 câu/key/refs; override count=3; options và keys xoay vị trí |
| Thiếu/ambiguous content | 2/3 definitions trả số câu tương ứng; 0/1 definition hoặc non-definition offline → insufficient; duplicate/conflicting terms bị loại |
| Source integration | DocumentService thật → Q02 → Q03; multi-document version/hash mapping giữ nguyên; source warnings không mất |
| Structured output | Invalid JSON/root/fences/trailing prose/duplicate keys/NaN/bytes/oversized đều bị từ chối |
| Item validation | Key sai/nhiều key/bool, option IDs/text trùng, nội dung rỗng, source IDs thiếu/lạ/trùng, fields giả mạo bị loại; all-invalid khác empty [] |
| Dedup/count limit | Duplicate stems bị bỏ; câu vượt yêu cầu bị bỏ; backend gán IDs liên tục cho câu đã chấp nhận |
| Trust boundary | Raw dict, wrong format, unsafe copied selection/ref, foreign source, conflicting version, fake verified, wrong span/kind bị chặn trước provider |
| Prompt/transport | XML framing/attribute escaping; JSON mode, finite timeouts, no redirect/retry; HTTP failure, connect/read timeout, invalid/incomplete/oversized response |
| Fallback/isolation | Explicit fallback được ghi nhận; không che invalid JSON; default offline không gửi email/network; algorithm subprocess chỉ stdlib và không external I/O |
| Contracts | Internal quiz JSON round-trip và frozen result/models |

Kết quả đo:

| Lệnh/check | Kết quả |
| --- | --- |
| `python -m pytest tests/test_f2_quiz_generation.py -v` | **60 passed**, exit 0; 1.20s theo pytest |
| `python verify.py` | **226 passed**, exit 0; 4.58s theo pytest |
| AST qua verify | **49 Python files PASS** |
| R2 gate + subprocess test thuật toán mới | **PASS** |
| Regression | 30 baseline F1/F3/pipeline + 81 Q01 + 55 Q02 đều PASS |
| Scope/preservation audit | PASS; prior source/tests/report hashes và legacy 511 file hashes/index/diffs khớp |

Một warning Starlette/TestClient deprecation vẫn tồn tại từ baseline. Không sửa dependency hoặc F1/F3 để xử lý warning. Không build lại frontend vì không thay frontend/dependencies. Full suite dùng mock modes; Ollama requests được giả lập, không có live model call/email dispatch.

Logs/command metadata nằm ở:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q03-2026-11-12\evidence\baseline\focused.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q03-2026-11-12\evidence\baseline\focused.json
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q03-2026-11-12\evidence\baseline\verify.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q03-2026-11-12\evidence\baseline\verify.json
```

Diff riêng Q03 kể cả untracked, final audit, prior hashes và legacy preservation ở cùng evidence/. Tự review đã thực hiện; chưa có independent review hoặc browser/user E2E. Người dùng tiếp tục kiểm thử thủ công toàn bộ vào cuối chuỗi F2-Q0x theo quyết định đã chốt.

## 4. Giới hạn / chưa hoàn thành

- Semantic correctness của answer key, distractors, explanations và supporting references chưa được chứng minh bởi Q03. Q05 phải kiểm chứng trước khi coi học liệu là đã verified. COMPLETE không thay thế kiểm chứng này.
- Adapter offline chỉ xử lý định nghĩa literal, có thể bỏ sót hoặc hiểu sai mẫu diễn đạt phức tạp; không có số liệu accuracy/latency trên corpus thật. Ollama adapter mới có transport tests, chưa có live quality evaluation.
- Input PreparedStudySources là trusted-caller contract, không chứng minh auth/quyền workspace. Service không đọc lại live repository hoặc raw source bytes; snapshots có thể stale sau Q02. Q05/Q08 cần giải quyết freshness/authorization tại boundary phù hợp.
- Escaped prompt framing không chứng minh miễn nhiễm mọi prompt injection. Provider vẫn là nguồn output không tin cậy; semantic/grounding gate chưa làm.
- Không có persistence, idempotent save, grading, learner projection, study routes/UI, Flashcards generator hoặc release evaluation.
- Không đăng ký service singleton/router hoặc tự sửa default app flow. F1/F3 giữ nguyên; toàn bộ study implementation vẫn nằm trong working tree chưa commit.

## 5. Bàn giao tiếp theo — F2-Q04 Flashcard Generation

Q04 chưa triển khai trong lần này. Làm cùng worktree/branch; giữ code và tests Q00–Q03 cùng mọi thay đổi chưa commit.

- Goal/FR: tạo FlashcardDeck/Flashcard dựa trên nguồn Q02 theo **FR2.04**; front là prompt, back là đáp án ngắn; default count=10 từ selection.
- Tệp theo kế hoạch: `backend/services/f2_flashcard_service.py`, `tests/test_f2_flashcard_generation.py`; thêm provider/algorithm riêng khi cần và ghi rõ scope. Nếu tách helper chung F2 từ Q03, phải giữ behavior và regression tests Q03.
- Dùng cùng nguyên tắc source aliases → exact SourceRefs do backend kiểm soát, không nhận metadata tự khai từ provider; refs tiếp tục UNVERIFIED.
- Có offline/deterministic path để kiểm thử; xử lý duplicate cards, thiếu nguồn, provider malformed/timeout, partial results, không bịa để đủ 10. Giữ source warnings.
- Không tự mở rộng spaced repetition/lịch sử học/grading hoặc SQLite. Q05 validation, Q06 interaction, Q08 API/UI và Q09 evaluation vẫn ở task sau; Q07 SQLite sau MVP.
- Baseline trước Q04: **226 tests PASS**, AST 49 files, R2 PASS. Chạy focused tests rồi full verify; manual E2E của người dùng để cuối chuỗi.
