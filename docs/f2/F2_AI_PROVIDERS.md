# F2 — Gemini và Ollama trên UI thử

**Cập nhật 2026-11-12:** đã thêm lựa chọn **NVIDIA NIM** với ô key riêng; xem [hướng dẫn NVIDIA NIM và kết quả mới](F2_NVIDIA_NIM.md). Các số liệu bên dưới thuộc mốc Gemini/Ollama trước khi thêm NIM.

Ngày thực hiện: 2026-11-12. Branch `feat/f2-quiz-flashcards`; worktree `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards`.

Mở **http://127.0.0.1:8512**. UI có **Offline / Gemini / Ollama**; mặc định Offline để không tự gửi tài liệu ra ngoài. Browser hiện đã chọn Gemini và hiển thị ô key trống; chưa xác nhận cuộc gọi thật.

## Cách thử Gemini bằng tài liệu của bạn

1. Tải PDF có lớp chữ, TXT hoặc MD và bấm **Nạp tài liệu**; chọn một/nhiều nguồn.
2. Chọn Quiz/Flashcards và số lượng mong muốn (mặc định 10).
3. Chọn **Bộ sinh → Gemini**. Nhập **Gemini API key** trong ô ẩn trên UI; không gửi key vào chat. Có thể dùng key đã cấu hình ở biến server `GEMINI_API_KEY` thay vì nhập UI. Việc triển khai không ghi key vào source, logs hoặc file cấu hình; key nhập UI giữ trong session memory.
4. Kiểm tra **Model Gemini**. Ưu tiên `GEMINI_MODEL` trên server nếu có, nếu không là `gemini-3.5-flash-lite`. Có thể sửa tên model theo project của bạn. Tên mặc định dựa trên [catalog model chính thức](https://aistudio.google.com/docs/models); chưa kiểm tra availability/quota của project nào.
5. Bấm **Tạo bộ luyện tập** để gửi request thật. Chỉ các passages Q02 của các tài liệu đã chọn được gửi tới Google, kèm source IDs/locators để map citation; không gọi Files API để upload nguyên file. Nhãn model là **model yêu cầu**, không phải xác nhận resolved model version.
6. Nếu generation và Q05 chấp nhận, Quiz cho nộp bài/xem kết quả hoặc Flashcard cho lật/chuyển thẻ. API error/thiếu nguồn/Q05 không đủ support đều báo thật; không chuyển sang offline âm thầm.

Tạo/quản lý key theo [hướng dẫn chính thức của Google](https://aistudio.google.com/docs/api-key) và [Google AI Studio](https://aistudio.google.com/apikey). Có key trong ô chưa chứng minh key hoạt động: chỉ Google xác nhận khi gửi request. Không yêu cầu hoặc đọc key qua công cụ chat.

## Ollama và Offline

- **Ollama:** dùng adapters đã có từ Q03/Q04. Chọn model đã cài trong Ollama đang chạy; base URL lấy cấu hình server `OLLAMA_BASE_URL`, model mặc định từ `OLLAMA_MODEL`. Không nhập Gemini key cho Ollama. Chưa probe daemon, tải model hoặc gọi Ollama thật trong lần này.
- **Offline:** bộ sinh định nghĩa cũ, không network. Không có dữ liệu mẫu hoặc Quiz/Flashcard dựng sẵn trong UI. UI không báo kết quả offline là kết quả Gemini.

## Phần đã triển khai

`backend/providers/f2_gemini_provider.py` bổ sung `GeminiStudyProvider`, `GeminiQuizProvider`, `GeminiFlashcardProvider`; không sửa F1/F3 `llm_provider.py` hoặc shared settings.

Adapter sử dụng [Google generateContent REST API](https://aistudio.google.com/api-reference/generate-content): fixed `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, key trong `x-goog-api-key` header. Model ID được kiểm tra trước khi dựng path. Không custom Gemini origin, redirect, automatic retry, model fallback hoặc offline fallback.

Request dùng responseMimeType=application/json và responseJsonSchema cho wire shapes questions/options/key/explanation/source_ids hoặc cards/front/back/source_ids. Theo [hướng dẫn structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), JSON shape vẫn phải được ứng dụng kiểm tra; nó không chứng minh đáp án đúng.

Timeout read 60s/connect 2s; response body giới hạn 1,000,000 bytes trước khi tích lũy. Chỉ lấy một candidate có finishReason STOP, bỏ thought parts, nối text parts, từ chối output kind lạ. Trả raw inner JSON cho Q03/Q04 strict parser/source mapping. HTTP auth/quota/model errors, blocked/truncated/invalid/oversized output có typed sanitized errors; không in raw error body/key.

Luồng hiện tại:

```text
DocumentService → Q02 exact source preparation
→ provider được chọn → Q03/Q04 strict structural/source mapping
→ Q06 start → Q05 current source + content support
→ learner projection / submit / flip
```

**Giới hạn quan trọng:** Q05 vẫn chỉ chứng minh exact extractive definition templates. Gemini prompt được yêu cầu giữ nguyên term/body, ngôn ngữ/qualifiers/units và dùng templates mà Q05 đã hỗ trợ. Câu hỏi diễn giải, facts/general reasoning hoặc back thêm kiến thức có thể bị chặn dù Gemini HTTP thành công. Không thêm semantic judge hoặc nới gate để tạo thành quả dễ thành công. Vì vậy nối Gemini chưa đồng nghĩa mọi loại tài liệu đều sinh được bộ luyện tập.

Không thêm public study API/auth resolver, production session store, persistence/SQLite hoặc tuyên bố hoàn tất Q08. Data/practice vẫn session local; F1/F3 và toàn bộ Q00–Q06 code/tests/reports giữ nguyên.

## Kết quả kiểm tra thực tế

| Check | Kết quả |
| --- | --- |
| `python -m pytest tests/test_f2_ai_providers.py -v` | **43 passed**, exit 0; 8.35s theo pytest |
| `python verify.py` trước đổi nhãn provider/model | **503 passed, 1 warning**, exit 0; 13.95s theo pytest |
| `python verify.py` sau đổi nhãn cho chính xác | **503 passed, 1 warning**, exit 0; 15.80s theo pytest |
| AST / R2 | **70 files PASS / PASS** |
| Browser | Đã chọn Gemini; model field, masked key, thông báo chưa có key và nút tạo disabled hiển thị đúng; screenshot ngoài checkout |
| Scope/preservation audit | PASS; không staged/new commits; legacy index/diffs/branch/HEAD và 511 hashes giữ nguyên |

503 = 460 prior tests + 43 new tests. Tests cũ không sửa. CPython 3.12.14, pytest 9.2.0, Streamlit 1.66.1; full verify có local loopback cho AppTest/TestClient. Starlette/TestClient warning cũ còn nguyên; không sửa dependencies.

43 tests bao phủ fixed origin/header/schema/timeouts, no eager network, malformed config, auth/quota/redirect/server/transport errors, blocked/truncated/malformed/oversized output, thought/text parts, real ingestion→Gemini adapter→Q05/Q06, Q05 chặn wrong key/unsupported back và UI chọn đúng adapter/model, thiếu key hoặc API error không fallback. HTTP giả lập chỉ ở tests, không phải chế độ Gemini trên UI.

**Chưa live test Gemini:** workspace không có key lúc khảo sát. Không gọi Google bằng key thật, không xác nhận quota, model access hoặc accuracy/latency trên tài liệu thực tế. Người dùng nhập key và bấm tạo mới kiểm tra được các phần này. Không gửi tài liệu đang upload qua Google bằng công cụ của agent.

Tệp mới: provider, `tests/test_f2_ai_providers.py`, hướng dẫn này. Chỉnh sửa: hai tệp UI, map/changelog và pointer cập nhật đầu manual guide cũ. Không sửa core/service/algorithms/repository Q01–Q06 hoặc các báo cáo lịch sử. Không stage/commit/push/merge/reset/clean/stash/xóa code cũ.

Evidence:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-ai-providers-2026-11-12\
  gemini-ui.png
  evidence\baseline\focused.log / focused.json
  evidence\baseline\verify.log / verify.json
  evidence\baseline\verify-final.log / verify-final.json
  evidence\before\...
  evidence\before-files-sha256.json
  evidence\ai-providers-only.patch
  evidence\final-audit.json
  evidence\legacy-preservation.json
  evidence\status.txt
  evidence\worktrees.txt
```

Giữ nguyên manual test dữ liệu thật để người dùng thực hiện. Nếu có lỗi, ghi provider/model yêu cầu, thông báo và loại tài liệu; không đưa API key vào log/chat. Mở rộng semantic validation ra ngoài định nghĩa, full API/auth wiring, corpus evaluation và SQLite sau MVP vẫn là công việc riêng tiếp theo.
