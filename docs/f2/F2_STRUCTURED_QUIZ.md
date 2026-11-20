# F2 — Structured Quiz JSON và câu hỏi tương tác

Ngày: 2026-11-13. Branch `feat/f2-quiz-flashcards`, worktree `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards`. HEAD/origin/main vẫn `da40118de0adbda33c55200d30bd9915019d2619`; implementation chưa commit.

## Kết quả thực hiện

Trước đợt này đã có JSON generation và Q06 radio form cho học liệu đạt kiểm chứng, nhưng câu tự nhiên cần review chỉ hiện dưới dạng nội dung soạn. Đợt này thống nhất contract JSON ở core/prompt/provider/parser và thêm luồng tương tác riêng cho Quiz nháp chưa kiểm chứng.

- LLM nhận JSON Schema cố định, chỉ trả object `questions`, không Markdown/HTML/JavaScript hay prose ngoài JSON.
- Chế độ `Nội dung tài liệu` yêu cầu câu hỏi tự nhiên, đủ chủ thể/ngữ cảnh, phương án nhiễu hợp lý và giải thích bám nguồn. Bỏ ưu tiên chép nguyên văn rồi đục lỗ ở Quiz. Yêu cầu bỏ qua nếu thiếu tên hàm/chủ thể cần thiết; không đoán bằng kiến thức ngoài. Đây là chỉ dẫn prompt, chưa phải phép chứng minh chất lượng đầu ra.
- Backend parse JSON nghiêm ngặt, kiểm từng item theo typed contract và map source IDs do backend cấp; web dựng radio từ dữ liệu đã qua cấu trúc/nguồn.
- Quiz chưa đạt semantic support có thể được người dùng chủ động **làm thử nháp**. Giao diện ghi rõ chưa kiểm chứng và so lựa chọn với đáp án **AI đề xuất**. Không gắn VERIFIED hay đưa nháp vào Q06.
- Quiz đã đạt kiểm chứng tiếp tục đi vào Q06, giữ chính sách submit/reveal/score đã có. Flashcard generation/prompt và old definition mode giữ phạm vi cũ.

## Contract LLM phải trả

Ví dụ dưới minh họa hình dạng dữ liệu, không phải kết quả tạo từ tài liệu người dùng và không được seed vào UI:

```json
{
  "questions": [
    {
      "question": "<Câu hỏi đầy đủ chủ thể, điều kiện và ngữ cảnh từ nguồn>",
      "options": [
        {"option_id": "A", "text": "<Phương án A>"},
        {"option_id": "B", "text": "<Phương án B>"}
      ],
      "correct_option_id": "A",
      "explanation": "<Giải thích được nguồn hỗ trợ>",
      "source_ids": ["S1"]
    }
  ]
}
```

`question`/`explanation`/option text và IDs phải là string không rỗng; 2–4 options có ID và text khác nhau; key trỏ đúng một option có thật. Source aliases không trùng và phải có trong snapshot chuẩn bị nguồn. Không thêm `verified`, `question_id`, doc metadata hoặc `source_refs`; backend tạo question IDs và hydrate refs từ aliases. Khi thiếu nội dung, trả `{"questions": []}` hoặc ít câu hơn, không bịa đủ 10.

`LLMQuizQuestion`/`LLMQuizPayload` là frozen/extra-forbidden models tại `backend/core/f2_quiz_payload.py`; `quiz_response_schema()` tạo schema inline từ models, không giữ shared mutable mapping. Prompt Quiz và Gemini `responseJsonSchema` dùng cùng schema. NIM/Ollama được yêu cầu schema qua prompt; không khẳng định nhà cung cấp cưỡng chế JSON mode. Backend vẫn kiểm độc lập.

Untrusted JSON phải qua `parse_generation_items` trước typed item validation, để chặn duplicate keys, NaN, code fence, sai root/extras/response size. Có item sai thì Q03 giữ hành vi partial/omit/report; source alias lạ bị loại. Q01 models rộng hơn không bị đổi contract bởi giới hạn 2–4 của wire format mới.

## Web tương tác như thế nào

```text
Q02 passages → LLM JSON → strict parse → typed question → server source mapping
  → Q05 review
    → ready: Q06 practice hiện có
    → review-only: bản nháp
      → bấm Làm thử Quiz nháp (chưa kiểm chứng)
      → radio mỗi câu → Nộp bản nháp
      → so lựa chọn với đề xuất AI + explanation + citations
```

`F2StudyDraftService.preview_quiz(resource, *, context, submission=None)` đọc/kiểm nguồn lại mỗi lần render, submit và xem kết quả. Chặn resource bị REJECTED, global warning, source không MATCHED/không truy cập được, injection được nhận diện và yêu cầu tự giải Toán/Lý được nhận diện. REVIEW_REQUIRED về semantic support có thể preview với nhãn `UNVERIFIED_DRAFT`.

`DraftQuizPreview` chỉ có learner questions/options và `result=None` trước submit; không có key, explanation hay refs. Sau submit mới có `DraftQuizResult` với `matching_count`/`match_percent`, và `DraftQuizFeedback.proposed_option_id`/`matches_proposed`/explanation/refs. Đây là phép so với đề xuất AI, không phải điểm học tập đã xác minh. Dùng lại stdlib grading với denominator là actual_count, câu bỏ trống là chưa trả lời; chặn unknown/repeated answers.

UI tách màn làm thử khỏi panel soạn đáp án. Có nút làm lại (attempt ID mới, lựa chọn trống) và quay lại review; tạo bộ mới xóa preview cũ. Author review vốn có thể hiển thị đáp án đề xuất trước khi người dùng chọn làm thử; đây là công cụ soạn/test local, không phải chế độ thi kín. Không lưu official attempt/progress, không tạo Q06 session và không có nút bypass VERIFIED.

## File tạo/sửa trong đợt này

| Hành động | File |
|---|---|
| Tạo | `backend/core/f2_quiz_payload.py` |
| Tạo | `backend/core/f2_quiz_preview_schemas.py` |
| Tạo | `tests/test_f2_structured_quiz.py` |
| Tạo | `tests/test_f2_structured_quiz_ui.py` |
| Tạo | `docs/f2/F2_STRUCTURED_QUIZ.md` |
| Sửa | `backend/providers/f2_gemini_provider.py` — dùng shared Quiz schema |
| Sửa | `backend/providers/f2_quiz_provider.py` — JSON Schema trong prompt |
| Sửa | `backend/providers/f2_source_content_provider.py` — Quiz natural questions; Flashcards giữ prompt cũ |
| Sửa | `backend/services/f2_quiz_service.py` — typed wire validation mỗi item |
| Sửa | `backend/services/f2_study_draft_service.py` — preview/submission DTOs |
| Sửa | `frontend/components/f2_manual_panel.py` — draft radio/submit/results/retry/back |
| Sửa | `frontend/f2_manual_app.py` — mô tả UI đúng phạm vi |
| Sửa | `.skills/codebase_map.md`, `CHANGELOG.md` |

## Test và evidence

Runtime Python: `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe`. Cwd: worktree F2. Wrapper thực thi và lưu command/cwd/env/exit/log tại `output/f2-structured-quiz-2026-11-13/evidence/baseline/` ngoài checkout.

```powershell
rtk proxy 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe' -m pytest tests/test_f2_structured_quiz.py tests/test_f2_structured_quiz_ui.py tests/test_f2_source_content.py tests/test_f2_source_content_ui.py tests/test_f2_quiz_generation.py tests/test_f2_manual_ui.py tests/test_f2_ai_providers.py tests/test_f2_nvidia_nim_provider.py -v
rtk proxy 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe' verify.py
```

- Mới: **37 backend/HTTP + 7 AppTest = 44** cases. Contract/key/options/extras, strict malformed JSON, source hydration, Gemini/NIM request schema/prompt, preview hidden fields, actual-count comparison, invalid choices, source/scope/injection/math blocking, UI radio/submit/retry/review/regeneration.
- Focused đầu: **1 failed, 261 passed** — JSON Schema array có minLength/maxLength thay vì minItems/maxItems do thứ tự Pydantic Field/BeforeValidator. Đã sửa thứ tự constraints; failure log giữ tại `focused.log/.json`.
- Focused-final: **262 passed**, exit 0, `focused-final.log/.json`.
- Full verify: **653 passed, 1 warning**, AST **82**, R2 PASS; `verify.log/.json`. Sau khi bỏ nhánh Quiz prompt cũ không còn được dùng, full cuối lưu ở `verify-final.log/.json`.
- 609 test cũ giữ nguyên file và pass; warning Starlette/TestClient dùng httpx deprecated vẫn còn. Cloud calls là `httpx.MockTransport`; AppTest ingest TXT thật qua DocumentService rồi dùng actual generation/review/UI services. Không seed dữ liệu test vào sản phẩm.
- Browser: bản UI được Rerun trên `http://127.0.0.1:8512/`, xác nhận config/caption mới trong phiên trống. Ảnh `output/f2-structured-quiz-2026-11-13/evidence/ui-structured-quiz.png`. Không nhấn Generate, không upload/chạm key/PDF thật; form/submission được test bằng AppTest, chưa được manual live-model evaluation.
- Snapshot 52 file trước đợt sửa và bản copy 9 file dự kiến sửa nằm trong `evidence/before*`. Audit phạm vi/preservation, status, worktrees và patch cuối nằm trong `evidence/final-audit.json`, `legacy-preservation.json`, `status.txt`, `worktrees.txt`, `structured-quiz-only.patch`.

## Cách thử thủ công

1. Mở UI local. Nếu thấy `File change`, bấm **Rerun**; không cần deploy. Dùng lại tài liệu trong phiên nếu còn, hoặc nạp lại và chọn nguồn.
2. Chọn **Quiz** → Gemini/NVIDIA NIM/Ollama → **Nội dung tài liệu**. Nhập key/model phù hợp nếu cần. Bấm tạo **bộ mới** để dùng prompt mới, vì draft cũ giữ câu hỏi cũ.
3. Nếu có bản nháp và không có lỗi nguồn/rejection, bấm **Làm thử Quiz nháp (chưa kiểm chứng)**. Chọn một đáp án mỗi câu; có thể để trống để kiểm tra unanswered.
4. Bấm **Nộp bản nháp**, xem “Khớp đáp án AI đề xuất”, explanation và citations. Đối chiếu bản gốc, kiểm tra câu hỏi có tên hàm/chủ thể/ngữ cảnh đầy đủ. Thử **Làm lại Quiz nháp** và **Quay lại review bản nháp**.
5. Nếu bộ đủ điều kiện kiểm chứng và mở Q06 tự động, làm/nộp như luồng cũ. Không diễn giải điểm nháp thành điểm đã kiểm chứng.

## Giới hạn và bước tiếp

Đợt này hoàn thành structured JSON và interactive rendering cho Quiz, cùng thay đổi prompt chất lượng. Chưa có semantic judge tổng quát; Q05 definition/cloze gate giữ nguyên, vì vậy câu tự nhiên vẫn có thể REVIEW_REQUIRED. Preview cho phép kiểm trải nghiệm trong trạng thái đó mà không đổi trạng thái kiểm chứng.

Finding manual “this function” đã được đưa thành yêu cầu prompt rõ ràng, chưa được tái hiện/đánh giá lại với PDF và live model của người dùng. Vẫn cần manual evaluation câu tự nhiên/context, answer uniqueness/distractors và explanation grounding. Không bảo đảm mọi model tuân thủ prompt hoặc mọi JSON hợp lệ chứa kiến thức đúng. Không OCR, không full Q08 API/auth, không SQLite, không tự giải Toán/Lý. F1/F3, Q01/Q05/Q06 và code legacy được bảo toàn; không stage/commit/push/merge/reset/clean/xóa code.
