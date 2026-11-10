# WorkspaceAI — Frontend

Giao diện WorkspaceAI sử dụng **React, TypeScript và Vite**, kết nối với backend **FastAPI**. Các lệnh bên dưới dùng PowerShell trên Windows.

Thư mục trên máy hiện tại:

```text
H:\WorkSpaceAI\WorkSpaceAI\           ← thư mục gốc, chứa Start-Workspace.ps1
H:\WorkSpaceAI\WorkSpaceAI\frontend\  ← giao diện React, chứa README này
```

Nếu đặt dự án ở nơi khác, thay đường dẫn trong các lệnh bằng thư mục tương ứng.

## 1. Chạy nhanh trên máy hiện tại

Máy hiện tại đã có thư viện cần thiết. Mở PowerShell và chạy:

```powershell
Set-Location H:\WorkSpaceAI\WorkSpaceAI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Workspace.ps1 -Engine offline
```

Đợi xuất hiện **`WorkspaceAI is ready`**, sau đó mở:

**[http://127.0.0.1:5174/](http://127.0.0.1:5174/)**

Lệnh trên bật cả backend và frontend, kiểm tra kết nối và chạy hai dịch vụ dưới nền. Có thể đóng cửa sổ PowerShell sau khi nhận thông báo sẵn sàng; ứng dụng vẫn chạy.

| Địa chỉ | Mục đích |
| --- | --- |
| [127.0.0.1:5174](http://127.0.0.1:5174/) | Giao diện sử dụng hằng ngày |
| [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Tài liệu và công cụ thử API backend |
| [127.0.0.1:5174/api/runtime](http://127.0.0.1:5174/api/runtime) | Kiểm tra kết nối từ frontend đến backend |

Kết quả kiểm tra có `status: "ready"`, `engine_mode: "offline"` và `offline_only: true` nghĩa là backend sẵn sàng ở chế độ Offline.

**Offline** thực hiện đọc, tìm kiếm, trích dẫn và tổng hợp theo quy tắc trên máy. Chế độ này không cần API key hoặc cài mô hình Ollama. Lệnh trên chặn gọi Gemini và đặt email ở chế độ mô phỏng `local_mock`.

Lần sau cũng có thể nhấp đúp **`Start-Workspace.cmd`** ở thư mục gốc. File này dùng chế độ `auto`, theo lựa chọn engine đã lưu; cấu hình hiện tại là Offline. Dùng lệnh có `-Engine offline` phía trên để yêu cầu rõ chế độ Offline mỗi lần khởi động.

## 2. Cài đặt lần đầu trên máy mới

Nếu đã chạy được theo mục 1, bỏ qua phần này.

Chuẩn bị **Python 3.10 trở lên, Node.js 22 trở lên và pnpm**. Kiểm tra trong PowerShell:

```powershell
python --version
node --version
pnpm.cmd --version
```

Nếu chưa có pnpm, sau khi cài Node.js, chạy:

```powershell
npm.cmd install --global pnpm
```

Cài thư viện backend và frontend từ thư mục gốc:

```powershell
Set-Location H:\WorkSpaceAI\WorkSpaceAI
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location .\frontend
pnpm.cmd install --frozen-lockfile
```

Sau khi cài xong, thực hiện mục 1. Cài thư viện lần đầu cần Internet; launcher dùng lại các thư viện đã cài ở những lần chạy sau.

Không cần tạo `.env` hoặc nhập khóa Gemini để chạy Offline bằng launcher. Launcher ưu tiên `.venv` ở thư mục gốc; trên máy hiện tại còn hỗ trợ môi trường sẵn có ở `H:\WorkSpaceAI\.venv-schema-audit`.

## 3. Chạy riêng từng phần để xem lỗi

Cách này dùng `.venv` đã tạo ở mục 2. Mở **hai cửa sổ PowerShell** và giữ cả hai hoạt động để xem thông báo của từng dịch vụ trực tiếp. Nếu launcher đang chạy ứng dụng, tắt phiên cũ theo mục 7 trước để tránh trùng cổng.

### Cửa sổ 1 — Backend

```powershell
Set-Location H:\WorkSpaceAI\WorkSpaceAI
$env:LLM_PROVIDER = 'mock'
$env:WORKSPACE_OFFLINE_ONLY = 'true'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:EMAIL_DISPATCH_MODE = 'local_mock'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Đợi dòng **`Application startup complete`**.

### Cửa sổ 2 — Frontend

```powershell
Set-Location H:\WorkSpaceAI\WorkSpaceAI\frontend
$env:VITE_API_ENABLED = 'true'
$env:VITE_API_BASE_URL = '/api'
pnpm.cmd dev --port 5174 --strictPort
```

Mở **[http://127.0.0.1:5174/](http://127.0.0.1:5174/)**. Các biến `$env:...` chỉ áp dụng trong cửa sổ PowerShell đó và các chương trình được khởi động từ nó.

## 4. Sử dụng sau khi mở giao diện

1. Ở Home, dùng **New workspace** trong phần chính để tạo workspace, hoặc mở một workspace trong lịch sử ngay bên dưới.
2. Cột **Nguồn**: bấm **Thêm nguồn → Tải file → Chọn file từ thiết bị** để mở hộp chọn file của máy. Có thể chọn nhiều file hoặc hủy rồi mở lại; cũng có thể kéo file vào cột này, nhập liên kết công khai hoặc dán văn bản. Menu **Tải lại file gốc** mở cùng hộp thoại nhưng chỉ chọn một file để khôi phục nguồn tương ứng.
3. Tick nguồn cần dùng. Nguồn **Sẵn sàng** mới được chọn; bản mẫu hoặc bản xem trước cần tải file gốc lên backend.
4. Cột **Hội thoại**: nhập câu hỏi. Mỗi workspace có một hội thoại chung; bấm chip số để mở đoạn nguồn. Có thể sao chép, lưu ghi chú và đánh giá câu trả lời.
5. Cột **Studio**: chọn **Lên kế hoạch** hoặc **Soạn email**, điền tùy chọn và bấm **Tạo**. Kết quả lưu vào lịch sử bên dưới; có thể đổi tên, xem, chỉnh sửa, sao chép hoặc xuất file.
6. Thẻ **Kanban** trong Studio mở bảng rộng. Lần đầu chọn **Tạo bảng Kanban từ gợi ý của AI**, sửa/chọn nội dung trong bản xem trước rồi bấm **Xác nhận**. Mỗi workspace chỉ có một bảng; **Nhờ AI gợi ý thêm** chỉ nối các thẻ được duyệt. Có nút thử bản mẫu 8 thẻ. Hiện gợi ý dùng quy tắc Offline, không gọi mô hình AI.
7. Trong Kanban, **+ Thêm thẻ** rồi Enter để thêm nhanh. Kéo nút chấm để di chuyển thẻ/cột; bàn phím dùng Alt + mũi tên trên nút kéo. Bấm thẻ để sửa ngày, ưu tiên, nhãn, checklist, nguồn và ghi chú. Xóa thẻ có **Hoàn tác**; xóa cột yêu cầu chuyển thẻ sang cột khác. Bảng tự lưu trên trình duyệt, có thông báo **Đã lưu**. Dùng nút **Thu nhỏ** để trở lại ba cột.
8. **Bảng công việc** trong Studio giữ các mục Tasks, yêu cầu và đối soát hiện có. Thẻ Kanban liên kết Tasks qua task ID. Đề xuất task cần được xác nhận; email cần mở bản nháp và duyệt riêng trước khi gửi.

Backend hỗ trợ **PDF có văn bản, Word (.docx), PowerPoint (.pptx), TXT, MD và CSV**, tối đa 25 MB/file. PDF scan cần OCR trước. DOCX được đọc thành một trang văn bản; PPTX theo thứ tự slide. Nhập liên kết cần Internet và chỉ đọc nội dung công khai.

Khung chat trống đặt lời gợi mở và ô nhập ở giữa; có tin nhắn thì ô nhập nằm ở đáy. Desktop hiển thị ba cột, hai cột bên có thể thu gọn. Tablet dùng Chat và một cột chuyển giữa Nguồn/Studio. Điện thoại chuyển bằng ba tab ở cuối màn hình. Giao diện tự thích ứng kích thước thật, không còn nút Preview Desktop/Phone.

Giao diện vẫn giữ bảng màu cam và phông Be Vietnam Pro. Hai nút New workspace ở header và banner cuối Landing đã bỏ; nút trong phần chính vẫn hoạt động. [Bản thiết kế, wireframe và quyết định UX](WORKSPACE_DESIGN.md).

## 5. Kết nối frontend với backend

```text
Trình duyệt :5174 → /api → FastAPI :8000 → các service xử lý
```

| File | Vai trò |
| --- | --- |
| `src/api.ts` | Gọi API tài liệu, hỏi đáp, đối soát và duyệt email bằng `fetch` |
| `vite.config.ts` | Chuyển tiếp `/api` đến `http://127.0.0.1:8000` khi chạy Vite dev |
| `../Start-Workspace.ps1` | Khởi động hai dịch vụ và bật các biến kết nối |
| `../backend/main.py` | Đăng ký các route backend |

Launcher tự đặt `VITE_API_ENABLED=true` và `VITE_API_BASE_URL=/api`. Khi chạy riêng frontend, dùng các biến ở mục 3, hoặc tạo **`frontend/.env.local`** với nội dung:

```dotenv
VITE_API_ENABLED=true
VITE_API_BASE_URL=/api
```

Khởi động lại Vite sau khi sửa biến môi trường. File `.env.example` của frontend đặt `VITE_API_ENABLED=false` cho chế độ giao diện độc lập; cần đổi thành `true` nếu dùng file đó làm mẫu để kết nối backend. Khi API bị tắt, giao diện sử dụng dữ liệu cục bộ và dữ liệu mẫu.

Mỗi workspace gửi header `X-Workspace-ID` để tách thư viện tài liệu, lựa chọn nguồn và bản nháp email. Các API chính:

| Phương thức | Đường dẫn | Chức năng |
| --- | --- | --- |
| GET | `/api/runtime` | Trạng thái engine và chính sách Offline |
| GET | `/api/documents` | Danh sách tài liệu của workspace |
| POST | `/api/documents/upload` | Tải và xử lý file |
| POST | `/api/documents/select` | Lưu các tài liệu được chọn |
| DELETE | `/api/documents/{doc_id}` | Xóa tài liệu |
| POST | `/api/chat` | Hỏi đáp, yêu cầu đối soát hoặc tạo bản nháp email |
| POST | `/api/email/approve/{draft_id}` | Duyệt và thực hiện bước gửi theo chế độ backend |

API key chỉ thuộc cấu hình backend. Các biến `VITE_*` có thể xuất hiện trong mã gửi đến trình duyệt, vì vậy không đặt bí mật vào chúng. Hướng dẫn này giữ các luồng ở Offline; Gemini chỉ được bật khi người dùng chủ động cấu hình lại engine.

## 6. Dữ liệu và phạm vi tính năng hiện tại

| Phần | Hiện trạng |
| --- | --- |
| Tài liệu và hỏi đáp | Đã gọi backend; tìm kiếm theo các file được chọn và kiểm tra trích dẫn |
| Tasks / Requirements | Thêm, sửa và ánh xạ ở phía trình duyệt; chưa có API CRUD để đồng bộ các thay đổi này |
| Kanban | Một bảng/workspace, xem trước và xác nhận, kéo-thả, chi tiết và hoàn tác; lưu localStorage, đồng bộ các thẻ liên kết với Tasks; chưa có API cộng tác/SQL riêng |
| Đối soát | Gọi backend và lưu lịch sử báo cáo trên trình duyệt; tính từ dữ liệu phía server, chưa bao gồm chỉnh sửa Tasks/Requirements cục bộ |
| Email | Tạo bản nháp và duyệt qua backend; launcher dùng `local_mock`, kết quả gửi là mô phỏng. CC và đính kèm chưa được API gửi hiện tại hỗ trợ |
| Đăng nhập | Các màn hình xem trước; chưa xác thực tài khoản Google, Microsoft, Apple hoặc email/password |
| Cơ sở dữ liệu | `src/schema.ts` mô tả 12 bảng từ `database/schema.sql`; chưa có kết nối lưu trữ SQL đầy đủ |

Nơi lưu dữ liệu:

- **Trình duyệt:** workspace, hội thoại, task, requirement và lịch sử báo cáo trong localStorage `workspaceai-v2`. Dùng cùng địa chỉ `http://127.0.0.1:5174/` và cùng hồ sơ trình duyệt để truy cập lại. `localhost`, cổng khác và trình duyệt khác có vùng lưu riêng.
- **Backend:** metadata, nội dung đã lập chỉ mục và trạng thái chọn file tại `../.workspace_data/libraries/{workspaceId}.json`, khôi phục khi khởi động lại. Snapshot này không chứa file PDF gốc hoặc bản nháp email; giữ lại file gốc để có thể tải lại khi cần.
- **Nhật ký launcher:** `../.workspace_data/runtime/`, gồm `backend.out.log`, `backend.err.log`, `frontend.out.log`, `frontend.err.log` và các file PID. Thư mục này được bỏ qua khi đưa lên Git.

Các ví dụ có sẵn chứa người nhận `example.edu` và nội dung minh họa. Bản nháp bị sửa cần được tạo lại trên server và duyệt lại trước khi gọi API gửi; giao diện không tự xác nhận kết quả gửi khi yêu cầu thất bại hoặc hết thời gian chờ.

## 7. Tắt, chạy lại và xử lý lỗi

**Chạy bằng hai cửa sổ:** nhấn `Ctrl+C` trong từng cửa sổ để dừng backend và frontend. Chạy lại các lệnh ở mục 3 để bật lại.

**Chạy bằng launcher:** đóng tab hoặc cửa sổ PowerShell không dừng dịch vụ. Khi cần tắt, mở Task Manager, kiểm tra cột **Command line** để xác định đúng hai tiến trình WorkspaceAI: Python chạy `uvicorn backend.main:app` ở cổng 8000 và Node chạy `frontend\node_modules\vite\bin\vite.js` ở cổng 5174. Dừng đúng hai tiến trình này, sau đó chạy lại mục 1. Launcher sẽ dùng lại dịch vụ đang chạy nếu các cổng đã có WorkspaceAI hoạt động.

| Hiện tượng | Cách xử lý |
| --- | --- |
| `python`, `node` hoặc `pnpm` không được nhận diện | Cài công cụ còn thiếu, mở lại PowerShell rồi kiểm tra phiên bản theo mục 2 |
| PowerShell chặn `pnpm.ps1` | Dùng `pnpm.cmd` như các lệnh trong tài liệu |
| Không tìm thấy `.venv\Scripts\python.exe` | Thực hiện bước tạo môi trường ở mục 2, hoặc dùng launcher với môi trường sẵn có trên máy hiện tại |
| Thiếu module Python hoặc không tìm thấy Vite | Cài lại thư viện bằng các lệnh ở mục 2 |
| Không mở được trang hoặc frontend báo mất kết nối | Kiểm tra hai dịch vụ và mở `/api/runtime` qua địa chỉ ở mục 1; xem nhật ký hoặc chạy riêng theo mục 3 |
| Giao diện hiện dữ liệu mẫu thay vì gọi backend | Kiểm tra `VITE_API_ENABLED=true`, sau đó dừng và bật lại Vite |
| Báo cổng 8000 hoặc 5174 đã được sử dụng | Kiểm tra phiên ứng dụng đang chạy; dừng đúng phiên cũ trước khi chạy riêng từng phần |
| File có nhãn **Needs upload** / **Preview only** | Chọn **Sync server library**; nếu file vẫn thiếu, mở chi tiết nguồn và dùng **Re-upload to process** với file gốc |
| PDF không có nội dung để đọc | Dùng PDF có lớp văn bản hoặc OCR bản scan trước khi tải |
| Không thấy hội thoại cũ | Kiểm tra đúng địa chỉ `127.0.0.1:5174`, hồ sơ trình duyệt và workspace đã dùng trước đó |

Để xem phần cuối nhật ký backend từ thư mục frontend:

```powershell
Get-Content ..\.workspace_data\runtime\backend.err.log -Tail 40
```

## 8. Kiểm tra và build frontend

Chạy trong thư mục `frontend`:

```powershell
pnpm.cmd test
pnpm.cmd build
```

`test` kiểm tra các hợp đồng dữ liệu, chuyển đổi dữ liệu cũ, API, nguồn trích dẫn, Home và ranh giới duyệt email. `build` kiểm tra TypeScript và tạo thư mục `dist/`.

Kiểm tra riêng bộ chọn file trong trình duyệt, sau khi build:

```powershell
node tests/browser-file-picker.mjs
node tests/browser-kanban.mjs
```

Bài kiểm tra dùng Chrome/Edge và helper `../../.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs` đã có trên máy hiện tại. Nếu helper ở nơi khác, đặt biến `TASTE_CDP_PATH` bằng đường dẫn đầy đủ đến `cdp.mjs`. Bài kiểm tra chạy trên địa chỉ tạm riêng với file mẫu tự tạo, kiểm tra mở/hủy hộp chọn, bàn phím, nhiều file, tải lại, thử lại và kích thước điện thoại; không sửa workspace đang dùng. Kết quả nằm trong `.taste-skill/file-picker-v9/`.

Kiểm tra Kanban bao gồm xem trước/xác nhận, chuột/cảm ứng/bàn phím, cột, bộ lọc, hoàn tác, lưu lại, chip Chat và nguồn kiểm thử; ảnh/kết quả ở `.taste-skill/kanban-v10/`. [Phân tích UX, wireframe, màu sắc và giới hạn Kanban](KANBAN_DESIGN.md).

Xem trước bản build:

```powershell
pnpm.cmd preview --port 4173 --strictPort
```

Mở địa chỉ Vite thông báo, thường là `http://127.0.0.1:4173/`. Khi triển khai `dist/` lên máy chủ, cần cấu hình chuyển tiếp `/api` đến backend và giữ header `X-Workspace-ID`; cấu hình proxy của Vite dev không nằm trong các file build. Các biến `VITE_*` được lấy tại thời điểm build.

Kiểm định Python từ thư mục gốc, sau khi đã cài môi trường ở mục 2:

```powershell
Set-Location H:\WorkSpaceAI\WorkSpaceAI
.\.venv\Scripts\python.exe verify.py
```

## 9. Các file frontend chính

| File | Nội dung |
| --- | --- |
| `src/App.tsx` | Điều hướng và cập nhật trạng thái workspace |
| `src/Landing.tsx`, `src/landing.css` | Landing Home theo ảnh mẫu và lịch sử workspace hiện có |
| `src/Home.tsx`, `src/HomeOverview.tsx`, `src/home-model.ts` | Trang chủ, thống kê, khung hỏi đáp, lịch sử và bộ lọc workspace |
| `src/home.css`, `src/home-dashboard.css` | Màu workspace, bố cục Home ba cột và giao diện điện thoại |
| `src/Chat.tsx` | Khung hỏi đáp, câu trả lời và trích dẫn |
| `src/NotebookWorkspace.tsx`, `src/notebook.css` | Khung ba cột và responsive |
| `src/notebook-model.ts` | Gộp hội thoại, giữ bản lưu gốc và snapshot Studio |
| `src/Studio.tsx`, `src/studio-service.ts` | Tạo/lưu Plan và bản nháp Email |
| `src/Kanban.tsx`, `src/kanban-model.ts`, `src/kanban-service.ts`, `src/kanban.css` | Một bảng Kanban, gợi ý có duyệt, chỉnh sửa và responsive |
| `src/Sources.tsx` | Upload, link/văn bản, đổi tên, xóa và chọn nguồn |
| `src/Tasks.tsx`, `src/Requirements.tsx` | Task, yêu cầu và liên kết giữa chúng |
| `src/Reconciliation.tsx`, `src/report-model.ts` | Hiển thị và lưu kết quả đối soát |
| `src/Email.tsx` | Soạn, kiểm tra và duyệt bản nháp email |
| `src/api.ts`, `src/schema.ts`, `src/workflow-model.ts` | Gọi backend, kiểu dữ liệu SQL và chuyển đổi dữ liệu giao diện |
| `src/AISettings.tsx` | Trạng thái engine và cấu hình xử lý |
| `src/DocumentInspector.tsx` | Chi tiết trích dẫn và nội dung nguồn có sẵn |
| `src/Auth.tsx` | Màn hình đăng nhập/đăng ký xem trước |
| `src/AppTools.tsx` | Mục Display và giao diện sáng/tối; bố cục tự thích ứng kích thước thiết bị |
| `src/data.ts`, `src/styles.css` | Kiểu dữ liệu giao diện, dữ liệu mẫu và phong cách dùng chung |

Các file Python `app.py`, `state.py`, `styles.py` và `components/` trong cùng thư mục thuộc giao diện Streamlit trước đây. Các bước trong README này khởi động giao diện React tại cổng 5174.

## Docker (React + backend + Ollama)
From the project root run `docker compose up --build -d` and open http://localhost:8501. See the root README for model download and data persistence. Browser storage from port 5174 is a separate origin and is not migrated automatically.
