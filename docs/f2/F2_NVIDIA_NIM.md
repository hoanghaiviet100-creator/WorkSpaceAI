# F2 — NVIDIA NIM và nơi lấy Google API key

Ngày thực hiện: 2026-11-12. Branch `feat/f2-quiz-flashcards`, worktree `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards`; không commit/push/merge.

## Key Google ở đâu?

Lấy Gemini API key tại **[Google AI Studio](https://aistudio.google.com/apikey)**: đăng nhập Google, chọn **Create API key**, rồi chọn/tạo project theo giao diện. Nhập vào ô **Gemini API key** khi chọn Gemini trên UI. [Hướng dẫn chính thức của Google](https://aistudio.google.com/docs/api-key).

Key Google và key NVIDIA là hai loại khác nhau. Không cần gửi key vào chat hoặc đưa vào source/logs. Việc có key chưa chứng minh key/project có quyền/quota cho model; cần request thật để kiểm tra.

## Dùng NVIDIA NIM trên UI

Mở **http://127.0.0.1:8512** trên máy này:

1. Tải và **Nạp tài liệu** PDF có lớp chữ, TXT hoặc MD; chọn các nguồn của bạn.
2. Chọn Quiz hoặc Flashcards, số lượng mong muốn (mặc định 10).
3. Chọn **Bộ sinh → NVIDIA NIM**. Ô **NVIDIA API key** xuất hiện riêng; nhập key NVIDIA tại đây. Có thể dùng server `NVIDIA_API_KEY` thay cho ô nhập.
4. **Model NVIDIA NIM** lấy từ `NVIDIA_NIM_MODEL` nếu có, nếu không là `meta/llama-3.3-70b-instruct`, được liệt kê trong [API reference NVIDIA](https://docs.api.nvidia.com/nim/reference/meta-llama-3_3-70b-instruct-infer). Tên model có thể sửa theo quyền tài khoản; chưa xác nhận availability/quota với key thật.
5. Bấm **Tạo bộ luyện tập** mới gọi NVIDIA thật. Các passages Q02 của nguồn đã chọn được gửi tới NVIDIA. Nếu chưa có key, nút tạo bị vô hiệu hóa. UI không lấy key từ ô Gemini để gửi sang NVIDIA.

Key nhập UI chỉ giữ trong session memory, không ghi file; không có thay đổi `.env` trong lần này. [NVIDIA API Catalog Quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart) hướng dẫn lấy key tại [NVIDIA Build](https://build.nvidia.com/) bằng **Get API Key** trên trang model.

Đây là kết nối **NVIDIA-hosted NIM**, không phải triển khai NIM self-hosted. Không cài/tải model hoặc thêm custom endpoint. Lỗi key/quota/model, pending, timeout và nội dung không hợp lệ hiển thị từ service; không tự dùng Offline/Gemini thay thế để báo thành công.

## Những gì đã triển khai

Tệp mới:

- `backend/providers/f2_nvidia_nim_provider.py`: `NvidiaNimStudyProvider`, `NvidiaNimQuizProvider`, `NvidiaNimFlashcardProvider` theo protocols sẵn có.
- `backend/providers/f2_definition_prompts.py`: prompts định nghĩa dùng chung, policy được tách nguyên văn từ Gemini; không thay Q05.
- `tests/test_f2_nvidia_nim_provider.py`: 48 tests.
- Báo cáo/hướng dẫn này.

Chỉnh sửa: Gemini adapter chuyển sang gọi shared prompt helpers, hai tệp UI, map/changelog và pointers ở hai guides cũ. Gemini giữ cùng prompt text và HTTP behavior; không tuyên bố source Gemini byte-identical sau refactor. Các tests Gemini cũ giữ nguyên và đều PASS.

API theo [reference NVIDIA](https://docs.api.nvidia.com/nim/reference/meta-llama-3_3-70b-instruct-infer): fixed `https://integrate.api.nvidia.com/v1/chat/completions`, Bearer auth header, model/messages, stream=false, temperature=.1, max_tokens=4096. Không thêm OpenAI SDK hoặc dependency. Timeout read60/connect2, body cap 1,000,000 bytes; no redirects/retries/polling/proxy env/fallback.

NIM được yêu cầu JSON qua prompt; không giả định mọi hosted model hỗ trợ JSON Schema/response_format. Chỉ nhận một assistant text choice có finish_reason=stop, từ chối truncated/filter/refusal/tool/function output hoặc invalid envelope. Raw JSON tiếp tục qua Q03/Q04 strict parsers/source-ID mapping; không tự sửa fences/JSON để qua kiểm tra. HTTP202 là pending, không được báo thành công hoặc tạo bộ luyện tập; adapter không tự poll hoặc gửi lại request.

Q06 vẫn gọi Q05 trước practice và khi read/submit/flip/move. Q05 **chỉ hỗ trợ extractive definition templates**, nên general/paraphrased questions hoặc back ngoài định nghĩa có thể bị chặn dù API trả 200. Không có semantic judge mới, cờ VERIFIED từ model, câu mẫu, điểm giả hoặc validation bypass. Tài liệu scan vẫn không có OCR; insufficient content không được bù câu/thẻ cho đủ 10.

Không sửa Q00–Q06 code/tests/reports, F1/F3, shared config/provider, dependencies hoặc persistence. Chưa hoàn tất Q08 API/auth integration; SQLite tiếp tục sau MVP. Tài liệu/attempts vẫn local-session memory.

## Kết quả kiểm tra

| Lệnh/check | Kết quả thực tế |
| --- | --- |
| `python -m pytest tests/test_f2_nvidia_nim_provider.py -v` | **48 passed**, exit 0; 4.68s theo pytest |
| `python verify.py` | **551 passed, 1 warning**, exit 0; 14.63s theo pytest |
| AST / R2 | **73 files PASS / PASS** |
| Gemini regression | Toàn bộ 43 tests cũ không sửa, PASS trong full suite |
| Browser | Chọn NVIDIA NIM, thấy model và masked key riêng, warning thiếu key và nút tạo disabled; screenshot ngoài checkout |
| Scope/preservation audit | PASS; prior files ngoài phạm vi giữ nguyên; legacy branch/HEAD/index/diffs và 511 non-ignored hashes giữ nguyên |

551 = 503 prior +48 NIM. CPython3.12.14, pytest9.2.0, Streamlit1.66.1; tests chạy với local loopback cho AppTest/TestClient. Starlette/TestClient warning cũ giữ nguyên. Không stage/commit/push/merge/reset/clean/stash/xóa code cũ.

48 tests dùng **HTTP giả lập**, bao phủ endpoint/header/documented payload, config, auth/quota/model/redirect/202/server/transport errors, caps, finish reasons/refusal/tools, source scope (không gửi tài liệu chưa chọn), Q05 chặn sai key/unsupported back, không sửa fenced JSON/no fallback, UI chọn adapter/model thật và key NVIDIA không kế thừa từ Gemini. Ingestion/Q02/Q03/Q04/Q05/Q06 dùng service thật trong các integration tests.

**Chưa gọi NVIDIA thật hoặc kiểm key/quota/model accuracy/latency bằng tài liệu thực tế.** Browser xác nhận chưa có NVIDIA key trong ô cấu hình tại lúc kiểm tra. Model khác có thể có parameter/context/permission limits khác; không có automatic fallback để che sự khác biệt. Người dùng nhập key và bấm tạo mới kiểm tra được cuộc gọi thật.

Evidence ngoài checkout:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-nvidia-nim-2026-11-12\
  nvidia-nim-ui.png
  evidence\baseline\focused.log / focused.json
  evidence\baseline\verify.log / verify.json
  evidence\before\...
  evidence\before-files-sha256.json
  evidence\nvidia-nim-only.patch
  evidence\final-audit.json
  evidence\legacy-preservation.json
  evidence\status.txt
  evidence\worktrees.txt
```

Bước tiếp: manual test bằng key/tài liệu của bạn, ghi provider/model yêu cầu và thông báo khi lỗi; không đưa key vào log/chat. Mở rộng semantic validation, full API/auth wiring, release evaluation và SQLite sau MVP vẫn là công việc riêng.
