# F2 — UI tạm để test thủ công

**Cập nhật 2026-11-12:** UI hiện có **Offline / Gemini / NVIDIA NIM / Ollama**. Xem [hướng dẫn Gemini](F2_AI_PROVIDERS.md) và [hướng dẫn NVIDIA NIM/kết quả mới](F2_NVIDIA_NIM.md). Phần mô tả và số liệu bên dưới ghi lại mốc UI ban đầu, trước khi nối các API; không dùng các giới hạn về lựa chọn provider tại mốc đó để suy ra hiện trạng mới.

Ngày: 2026-11-12. Branch `feat/f2-quiz-flashcards`, worktree `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards`.

Mở **http://127.0.0.1:8512** trên máy này. UI đã được khởi chạy riêng với Streamlit, chỉ bind loopback. F1/F3 và màn hình chính cũ không sửa.

## Cách thử

1. Tải một hoặc nhiều PDF có lớp chữ, TXT hoặc MD của bạn lên và bấm **Nạp tài liệu**.
2. Chọn các nguồn vừa nạp. Chọn **Quiz** hoặc **Flashcards**, mặc định 10 câu/thẻ.
3. Bấm **Tạo bộ luyện tập**. UI giữ thông báo thiếu nội dung hoặc lỗi từ service; không bù câu/thẻ để đủ số lượng.
4. Quiz: chọn đáp án và **Nộp bài**. Sau đó mới thấy điểm, đáp án, giải thích và trích dẫn. Câu bỏ trống tính chưa trả lời theo Q06.
5. Flashcards: **Lật thẻ**, **Ẩn đáp án**, chuyển trước/sau. Back và nguồn chỉ hiển thị khi đã lật.

Tài liệu và lượt làm chỉ nằm trong bộ nhớ của phiên trình duyệt; chưa lưu SQLite. Tạo bộ luyện tập mới sẽ thay bộ đang hiển thị. Mở lại phiên mới/restart có thể mất dữ liệu thử.

## Giới hạn giữ nguyên

UI chỉ gọi những gì đã có:

```text
DocumentService.ingest_file
→ Q02 F2SourceService.prepare_sources
→ Q03 F2QuizService / Q04 F2FlashcardService (default deterministic)
→ Q06 F2PracticeService (tự gọi Q05)
```

Không có tài liệu mẫu, Quiz/Flashcard dựng sẵn, đáp án/điểm giả hoặc override VERIFIED. Test fixtures chỉ ở file test, không được nạp vào UI. Không sửa backend Q01–Q06 để tạo kết quả dễ thành công hơn.

Bộ sinh default hiện chỉ tạo từ định nghĩa rõ ràng. Quiz cần ít nhất hai terms đủ rõ để có lựa chọn; Flashcard có thể bắt đầu từ một định nghĩa. PDF scan chưa có OCR. Tài liệu nhiều văn xuôi/sự kiện nhưng không có định nghĩa phù hợp có thể trả không đủ nội dung. Đây là giới hạn thực tế của Q03/Q04, không phải lỗi UI cần che bằng nội dung mẫu.

Q05 chỉ xác minh mẫu extractive definition hiện có và có thể chặn nội dung chưa được hỗ trợ. UI không bỏ qua gate hoặc nhận cờ kiểm chứng do người dùng tự khai. Không thêm live Ollama mode, LLM judge, auth resolver, API, persistence hoặc chức năng backend mới. Đây **không phải tuyên bố Q08 hoàn thành**.

## Chạy lại khi server đã tắt

Chạy trong worktree bằng PowerShell, với môi trường Python hiện có:

```powershell
rtk proxy '..\tmp\workspaceai-audit-venv\Scripts\python.exe' -m streamlit run frontend/f2_manual_app.py --server.address 127.0.0.1 --server.port 8512 --server.headless true --browser.gatherUsageStats false
```

Không chạy thêm bản thứ hai khi port 8512 đang dùng. Không mở server này ra mạng ngoài: identity/context hiện là session local do server tạo, chưa phải auth/workspace resolver cho sản phẩm.

## Kiểm tra đã thực hiện

- `python -m pytest tests/test_f2_manual_ui.py -v`: **9 passed**, exit 0, 6.12s theo pytest.
- `python verify.py`: **460 passed, 1 warning**, exit 0, 12.76s theo pytest; AST **68 files PASS**, R2 PASS. Gồm nguyên 451 tests Q01–Q06/F1/F3 và 9 UI tests.
- AppTest thực hiện Quiz generation/submission/score/reveal, Flashcard flip/navigation, thiếu nguồn, injection, stale sources và session isolation qua service thật. AppTest không điều khiển file picker: test nạp TXT bytes qua DocumentService thật vào cùng UI runtime, sau đó chọn nguồn/thao tác bằng widgets.
- Browser thật đã mở và kiểm tra trạng thái rỗng, bố cục, default 10, disabled controls khi chưa có tài liệu. Local `/_stcore/health` trả `ok`. Chưa tự động upload tệp qua browser picker hoặc chạy corpus/Ollama thật.
- Lần AppTest trong môi trường giới hạn bị kẹt ở Windows asyncio socketpair/loopback, đã dừng. Lần chạy có loopback đầu tiên có 7 failed/2 passed do test chưa chọn nguồn qua widget sau ingestion; đã sửa helper test để chọn thật qua multiselect. Log thất bại được giữ; final focused/full suite đều PASS.
- Starlette/TestClient warning cũ còn nguyên. Không sửa dependencies hoặc build frontend React vì không thay đổi nó.
- Scope/preservation audit PASS: Q00–Q06 prior files byte-identical; chỉ map/changelog tracked thay đổi. Legacy branch/HEAD/index/diffs và 511 non-ignored tracked/untracked hashes giữ nguyên. Không stage/commit/push/merge/reset/clean/stash/xóa code cũ.

Chỉ thêm hai file UI, một test file và hướng dẫn này, cộng map/changelog. Evidence ở:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-manual-ui-2026-11-12\
  server.json
  server.stdout.log
  server.stderr.log
  evidence\baseline\focused-final.log / focused-final.json  # lần fail, giữ nguyên
  evidence\baseline\focused-pass.log / focused-pass.json
  evidence\baseline\verify.log / verify.json
  evidence\before-files-sha256.json
  evidence\manual-ui-only.patch
  evidence\final-audit.json
  evidence\legacy-preservation.json
  evidence\status.txt
  evidence\worktrees.txt
```

Bạn có thể thử tài liệu thực tế ngay và ghi lại tên tệp, loại học liệu, số lượng yêu cầu, thông báo và thao tác gặp lỗi. Q08 API/runtime integration đầy đủ và SQLite sau MVP vẫn là các phần việc tiếp theo.
