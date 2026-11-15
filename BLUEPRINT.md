# Blueprint công việc

Mỗi tác vụ có một mục với mã dễ nhận diện. Cập nhật mục đó qua các lần làm việc và giữ các mốc hoàn tất cần thiết để tiếp tục. Nếu nhiều tác vụ đang dở, dùng mục khớp với yêu cầu trong cuộc trò chuyện hiện tại.

## Cách ghi mốc

- Ghi tóm tắt prompt, các ràng buộc đã chốt và điều kiện hoàn thành. Lược bỏ thông tin bí mật.
- Dùng một trong bốn trạng thái `Chưa bắt đầu`, `Đang làm`, `Bị chặn`, `Đã xong`. Ghi bước cụ thể đang thực hiện và cập nhật khi có kết quả.
- Ở `Code đã cập nhật tới`, ghi nhánh hoặc worktree khi có, các tệp đã sửa và thay đổi chính. Ghi rõ thay đổi còn nằm trong working tree hay đã có commit. Khi tiếp tục, kiểm tra lại trạng thái Git và nội dung các tệp liên quan để nhận ra thay đổi phát sinh sau mốc.
- Ghi lệnh kiểm tra đã chạy và kết quả. Nếu chưa kiểm tra, ghi `Chưa chạy`. Nếu bị chặn, ghi nguyên nhân và điều kiện để tiếp tục.
- Viết `Bước tiếp theo` thành một hành động cụ thể có thể làm ngay khi tiếp tục. Khi hoàn thành, ghi `Không còn` sau khi đối chiếu với điều kiện hoàn thành.

## Mẫu mục tác vụ

```markdown
### <mã tác vụ> · <tên ngắn>

- **Prompt và ràng buộc** — …
- **Điều kiện hoàn thành** — …
- **Trạng thái** — …
- **Bước hiện tại** — …
- **Mốc đã hoàn tất** — …
- **Code đã cập nhật tới** — …
- **Kiểm tra** — …
- **Vướng mắc** — …
- **Bước tiếp theo** — …
```

## Các tác vụ đã ghi nhận

### create-full-project-branch · Tạo nhánh riêng cho toàn bộ dự án

- **Prompt và ràng buộc** — Chạy `git switch -c Pgkhiem31_UpdateProject/full-project`. Phạm vi lần này là tạo và chuyển nhánh. Yêu cầu loại tệp env áp dụng khi commit và push.
- **Điều kiện hoàn thành** — Nhánh hiện tại là `Pgkhiem31_UpdateProject/full-project`, bắt đầu tại `da08f91`.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã tạo và chuyển sang nhánh riêng.
- **Mốc đã hoàn tất** — Đã chạy `git switch -c Pgkhiem31_UpdateProject/full-project` từ `khiêm`.
- **Code đã cập nhật tới** — `Pgkhiem31_UpdateProject/full-project` tại `da08f91`. Các thay đổi dự án còn trong working tree.
- **Kiểm tra** — `git branch --show-current` và `git rev-parse --short HEAD` khớp điều kiện hoàn thành. Index chưa có thay đổi staged.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### push-full-project-guide · Hướng dẫn đẩy toàn bộ dự án lên nhánh riêng

- **Prompt và ràng buộc** — Hướng dẫn đưa toàn bộ dự án lên `origin/Pgkhiem31_UpdateProject/full-project`. Loại các tệp env, kể cả tệp mẫu, và ba thư mục `.agents/`, `.claude/`, `.codex/`.
- **Điều kiện hoàn thành** — Có lệnh stage loại đúng phạm vi và lệnh kiểm tra các đường dẫn bị loại trên nhánh mới.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất xác minh phạm vi stage.
- **Mốc đã hoàn tất** — Xác nhận đang ở `Pgkhiem31_UpdateProject/full-project`. Ba thư mục skill là untracked và không xuất hiện trong các đối tượng Git chưa có ở remote theo các ref cục bộ.
- **Code đã cập nhật tới** — Chỉ ghi mốc vào blueprint.
- **Kiểm tra** — `.env` và `frontend/.env.local` đã bị ignore. Hai tệp `.env.example` đang được theo dõi. Các commit chưa đẩy chỉ tham chiếu bản mẫu đã có trên remote theo dữ liệu cục bộ. Chạy thử với index tạm, xác nhận bỏ theo dõi hai tệp mẫu và lệnh stage không chọn tệp env hay tệp nào trong ba thư mục bị loại.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### push-frontend-guide · Hướng dẫn đẩy toàn bộ frontend

- **Prompt và ràng buộc** — Hướng dẫn đưa toàn bộ thư mục `frontend/` lên Git, kể cả các tệp đã theo dõi và không có sửa đổi.
- **Điều kiện hoàn thành** — Giải thích phạm vi của `git add`, commit và push dựa trên trạng thái hiện tại của nhánh.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất hướng dẫn Git.
- **Mốc đã hoàn tất** — Đã xác định phạm vi frontend, tệp mới và hai commit sẵn có. Đã xác định cách xuất riêng snapshot frontend qua nhánh mới từ `origin/khiêm` nếu cần.
- **Code đã cập nhật tới** — Chỉ ghi mốc vào blueprint.
- **Kiểm tra** — Git ghi nhận 85 tệp frontend đang theo dõi và hai tệp mới. Bản lưu cục bộ của `origin/khiêm` có 83 tệp frontend. Hai commit chưa đẩy có thay đổi ngoài `frontend/`.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### remove-chat-email-button · Gỡ nút soạn email khỏi câu trả lời

- **Prompt và ràng buộc** — Gỡ nút “Draft an email” được chỉ trong ảnh.
- **Điều kiện hoàn thành** — Câu trả lời trong Chat không hiển thị nút này và Studio vẫn mở được trình soạn email.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất.
- **Mốc đã hoàn tất** — Đã gỡ nút, callback cùng CSS chỉ phục vụ nút. Đã xác nhận câu trả lời vẫn hiển thị và có thể mở trình soạn email từ Studio.
- **Code đã cập nhật tới** — Working tree nhánh `khiêm`. Đã sửa `Chat.tsx`, `NotebookWorkspace.tsx`, `EmailWorkspace.tsx`, `styles.css` và `notebook.css`.
- **Kiểm tra** — TypeScript và Vite build thành công. 33 kiểm thử frontend đạt. Kiểm tra trình duyệt bằng dữ liệu mẫu ở 1440 px và 390 px xác nhận nút đã biến mất và mở được trình soạn từ Studio.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### setup-blueprint · Lưu tiến độ để tiếp tục sau gián đoạn

- **Prompt và ràng buộc** — Tạo blueprint ghi lại trạng thái prompt, bước đang làm và tiến độ cập nhật code để agent đọc khi tiếp tục.
- **Điều kiện hoàn thành** — Có mẫu cập nhật tiến độ và quy tắc trong `AGENTS.md` để agent đọc blueprint khi bắt đầu hoặc tiếp tục công việc.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất.
- **Mốc đã hoàn tất** — Đã tạo mẫu ghi mốc, thêm quy tắc đọc và cập nhật trong `AGENTS.md`, kiểm tra liên kết và các trường của mẫu.
- **Code đã cập nhật tới** — Đã chỉnh hai tệp Markdown trong working tree của nhánh `khiêm`. Các thay đổi ứng dụng đã có từ trước khi ghi mốc này.
- **Kiểm tra** — Đã xác nhận liên kết trong `AGENTS.md` trỏ tới tệp hiện có và mẫu cùng mục tác vụ đều có đủ 9 trường.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### check-gemini-provider · Xác nhận cấu hình Gemini

- **Prompt và ràng buộc** — Xác nhận dự án có đang dùng API key Gemini. Không ghi giá trị khóa.
- **Điều kiện hoàn thành** — Đối chiếu cấu hình và đường gọi model để xác định backend sử dụng provider nào.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất đối chiếu cấu hình và cách khởi động.
- **Mốc đã hoàn tất** — `.env` chọn Ollama, có khóa Gemini và cấu hình model `gemini-3.5-flash`. Script khởi động chế độ `auto` ưu tiên Gemini khi có khóa và không bật offline.
- **Code đã cập nhật tới** — Chỉ cập nhật mục này trong blueprint.
- **Kiểm tra** — Đã đọc cấu hình, mã gọi model và script khởi động. API trạng thái cục bộ trên cổng 8000 và 8001 không phản hồi để xác nhận engine đang chạy.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### plan-openai-provider · Hướng dẫn chuyển sang OpenAI API

- **Prompt và ràng buộc** — Giải thích cách chuyển dự án từ Gemini sang OpenAI API.
- **Điều kiện hoàn thành** — Xác định cấu hình, đường gọi model và các điểm chọn engine cần cập nhật. Đối chiếu với tài liệu OpenAI.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất hướng dẫn chuyển sang OpenAI API.
- **Mốc đã hoàn tất** — Xác định đường gọi Chat và tóm tắt, adapter Study riêng, cấu hình runtime, giao diện chọn engine và cấu hình khởi động PowerShell/Docker.
- **Code đã cập nhật tới** — Chỉ cập nhật mục này trong blueprint.
- **Kiểm tra** — Đã đối chiếu mã với OpenAI Developer Quickstart, Structured Outputs và danh mục model.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### explain-docker-compose · Giải thích cấu hình Docker Compose

- **Prompt và ràng buộc** — Giải thích cấu hình Compose hiện tại.
- **Điều kiện hoàn thành** — Nêu vai trò các dịch vụ, cổng, dữ liệu và quan hệ khởi động.
- **Trạng thái** — Đã xong.
- **Mốc đã hoàn tất** — Đã đối chiếu ba dịch vụ, cổng, cấu hình mặc định, thứ tự khởi động và nơi lưu dữ liệu.
- **Kiểm tra** — Cổng Swagger trên máy là 8001 theo ánh xạ 8001:8000.
- **Bước tiếp theo** — Không còn.

### check-running-model · Xác định model đang chạy

- **Trạng thái** — Đang làm.
- **Bước hiện tại** — Kiểm tra API runtime và cấu hình model.

- **Mốc đã hoàn tất** — API runtime trên cổng 8001 trả model gemini-3.5-flash. Cấu hình .env chọn Ollama với qwen3.5:9b-q4_K_M.
- **Trạng thái cuối** — Đã xong.
