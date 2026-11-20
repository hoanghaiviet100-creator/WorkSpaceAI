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

### fix-slide-topic-overview · Sửa tổng quan chủ đề slide

- **Prompt và ràng buộc** — Câu hỏi chủ đề chính của Chapter_2_v8.2.pptx trả chi tiết netcinema.com và t0. Sửa luồng tổng quan và kiểm tra với tệp thật.
- **Điều kiện hoàn thành** — Câu hỏi nguyên văn trả các chủ đề chính có dẫn nguồn, không lấy chi tiết rời rạc làm chủ đề.
- **Trạng thái** — Đang làm.
- **Bước hiện tại** — Kiểm tra định tuyến và cấu trúc PPTX đã nhập.
- **Mốc đã hoàn tất** — Đã đọc blueprint và thấy biểu thức nhận diện còn hẹp.
- **Code đã cập nhật tới** — Chỉ ghi mốc.
- **Kiểm tra** — Chưa chạy.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Tái hiện định tuyến và đối chiếu slide tổng quan.

### prepare-chapter2-test-questions · Câu hỏi thử với slide tầng ứng dụng

- **Prompt và ràng buộc** — Soạn câu hỏi thử hệ thống theo Chapter_2_v8.2.pptx do người dùng cung cấp.
- **Điều kiện hoàn thành** — Câu hỏi bám nội dung thật, có mốc slide và tiêu chí chấm, gồm ca thiếu nguồn và hỏi nối tiếp.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất bộ câu hỏi dựa trên văn bản trích xuất từ 125 slide.
- **Mốc đã hoàn tất** — Đọc chủ đề HTTP, DNS, P2P, DASH/CDN, socket và timeout, đối chiếu số slide.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Đã đọc nội dung XML PPTX, chưa chạy câu hỏi trên ứng dụng và chưa đối chiếu hình ảnh trong slide.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### start-workspace-20261120 · Khởi động WorkspaceAI

- **Prompt và ràng buộc** — Khởi động mọi dịch vụ để sử dụng trên trình duyệt.
- **Điều kiện hoàn thành** — Frontend, backend, research, Ollama và database sẵn sàng. Địa chỉ trình duyệt phản hồi.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Các dịch vụ sẵn sàng và đã yêu cầu mở notebook trong trình duyệt mặc định.
- **Mốc đã hoàn tất** — Bật Docker Desktop, khởi động Compose chính và Compose MySQL bằng tệp cấu hình cục bộ.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — App, frontend, research và MySQL healthy; Ollama đang chạy và có qwen3.5:9b-q4_K_M. Frontend HTTP 200, API runtime ready với engine Ollama.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### integrate-notebook-research · Tích hợp truy xuất vào Chat WorkspaceAI

- **Prompt và ràng buộc** — Tích hợp trực tiếp trong WorkspaceAI. Bỏ tên và thao tác mở ứng dụng riêng khỏi giao diện. Giữ phạm vi notebook và trích dẫn gốc.
- **Điều kiện hoàn thành** — Chat hiện có dùng dịch vụ truy xuất nội bộ, nút/tab riêng biến mất, trích dẫn vẫn mở tài liệu gốc, Studio vẫn hoạt động.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Bản mới đã triển khai và xác minh qua API cùng trình duyệt trên ba kích thước.
- **Mốc đã hoàn tất** — Bỏ nút và API sao chép cũ, dừng container công khai cổng 4929. Compose chính chạy dịch vụ research trong mạng nội bộ. Chat gọi khi tìm kiếm ban đầu thiếu bằng chứng, truyền đoạn đã chọn và lấy lại ID đoạn để ánh xạ trang/dòng từ nguồn gốc.
- **Code đã cập nhật tới** — Working tree: bỏ nút và route cũ, Compose mặc định, adapter tìm kiếm, phần mở rộng API upstream, bộ lọc nguồn và kiểm chứng trực tiếp cho ví dụ nguyên văn.
- **Kiểm tra** — 170 test backend, 33 test frontend, TypeScript, build Docker, Ruff và diff check đạt. Câu mẫu có điểm tìm kiếm ban đầu 0,1838, dùng chỉ mục nội bộ và trả đúng tài liệu trang 1 dòng 1. Câu Git dẫn trang 11 dòng 97 và trang 27 dòng 69. Ca ngoài phạm vi và không chọn nguồn từ chối đúng. Không còn nhãn cũ trong UI ở 1440/1024/390 px, API riêng trả 404 và cổng 4929 không kết nối được.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### integrate-full-surfsense · Kết nối toàn bộ backend SurfSense

- **Prompt và ràng buộc** — Dùng toàn bộ backend SurfSense kết hợp với WorkspaceAI và đánh giá việc dùng mã quiz, flashcard.
- **Điều kiện hoàn thành** — Có phiên bản SurfSense xác định, chạy được cùng WorkspaceAI, tích hợp một luồng qua backend và xác minh tác động lên dữ liệu notebook/Studio.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — WorkspaceAI và toàn bộ SurfSense 2.3.1 chạy cùng nhau trên Docker.
- **Mốc đã hoàn tất** — Clone toàn bộ mã nguồn 2.3.1, 2.142 tệp trong backend desktop. Dùng image chính thức cố định theo digest. Nối nút SurfSense và API sao chép nguồn được chọn, dùng Ollama qua mạng Docker nội bộ. Quiz/flashcard WorkspaceAI vẫn là lựa chọn có dẫn trang/dòng.
- **Code đã cập nhật tới** — Working tree: Compose bổ sung, API nối, nút notebook, tài liệu và script checkout nguồn. SurfSense giữ dữ liệu riêng trong volume.
- **Kiểm tra** — 33 test frontend, 169 test backend, build frontend và Compose healthy, Ruff và diff check đạt. Nút hiển thị ở 1440/1024/390 px. Copy chỉ có một nguồn được chọn, lặp không nhân bản, lập chỉ mục `ready`, Chat Qwen trích đúng đoạn mẫu, tạo ba flashcard thành công. API từ chối ID giả 404, chọn rỗng 422, hostname không được phép 403.
- **Vướng mắc** — Giao diện chọn notebook theo tên. Chỉ sao chép văn bản trích xuất, không mang tệp gốc hay lịch sử sang. Quiz SurfSense với Qwen 3.5 9B thất bại cả lần thử lại do phản hồi không phải JSON hợp lệ. Container hiện dùng image upstream, chưa dựng lại từ checkout.
- **Bước tiếp theo** — Không còn trong phạm vi tích hợp và quyết định giữ Studio WorkspaceAI.

### fix-standalone-topic-example · Hỏi giải thích và ví dụ theo chủ đề

- **Prompt và ràng buộc** — Câu “Giải thích thêm về remote và cho ví dụ” có một nguồn được chọn nhưng báo thiếu bằng chứng. Sửa theo cơ chế chung, giữ phạm vi nguồn.
- **Điều kiện hoàn thành** — Câu nguyên văn trả ví dụ thật từ PDF Git, kể cả khi chưa có lịch sử. Câu ngoài nguồn và không chọn nguồn vẫn bị từ chối.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Backend Docker mới healthy, đã xác minh câu nguyên văn qua cổng 8501.
- **Mốc đã hoàn tất** — Tái hiện với đúng PDF và lịch sử rỗng. Câu đầy đủ chỉ đạt điểm truy xuất 0,1885, dưới 0,35. Tách chủ đề đưa đoạn định nghĩa trang 11 và ví dụ trang 27 vào ngữ cảnh.
- **Code đã cập nhật tới** — Working tree: nhận diện câu hỏi về chủ đề trực tiếp, ưu tiên dòng đủ ngữ cảnh, đưa phần giải thích cho model và lấy nguyên dòng lệnh mẫu qua bộ kiểm chứng trích dẫn. Có ca hồi quy với tài liệu chủ đề khác.
- **Kiểm tra** — 169 test liên quan và `git diff --check` đạt. API với lịch sử rỗng và chỉ chọn PDF Git trả định nghĩa trang 11 dòng 97 và ví dụ `git remote add upstream` trang 27 dòng 69, cả hai `SUPPORTED`. Ca ngoài tài liệu và ca không chọn nguồn đều từ chối.
- **Vướng mắc** — Kiểm tra qua API giao diện, không thao tác trình duyệt trong lượt này.
- **Bước tiếp theo** — Không còn.

### fix-git-qa-example-answers · Kiểm tra bốn câu hỏi Git trong ảnh

- **Prompt và ràng buộc** — Kiểm tra bốn câu hỏi mẫu bị báo thiếu bằng chứng. Sửa nguyên nhân trong luồng chung và giữ phạm vi nguồn cùng kiểm chứng trích dẫn.
- **Điều kiện hoàn thành** — Xác minh bản đang chạy, tái hiện các câu với nguồn Git thật, sửa và đo lại cả ca ngoài phạm vi.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã triển khai backend Docker và thử lại bốn câu với PDF Git thật qua cổng 8501.
- **Mốc đã hoàn tất** — Docker cũ chưa có mã trích dẫn SurfSense. Khi chọn PDF Git, ca 1, 3 và 4 trong ảnh tái hiện, ca 2 trả được một ý. Đã tìm được đoạn `git remote -v` trang 26 dòng 92. Luồng hỏi chi tiết còn dùng định dạng JSON cũ của Ollama.
- **Code đã cập nhật tới** — Working tree: tra cứu bằng thuật ngữ kỹ thuật, định tuyến câu hỏi theo chương, tìm đúng câu hỏi trước theo chủ đề được nhắc, thêm định dạng Ollama có `source_id` và hướng dẫn trả phần có bằng chứng.
- **Kiểm tra** — 168 test và `git diff --check` đạt. File provider và QA trong container khớp SHA-256 với mã hiện tại. Bốn câu qua cổng 8501 đều `ANSWER_VERIFIED`: câu 1 và 2 dẫn trang 26 dòng 92, Chương 8 đủ 9 tiểu mục ở trang 26–27, câu tiếp theo dẫn trang 11 và 27. Hỏi đạo hàm khi chỉ chọn tài liệu Git bị từ chối. Bỏ chọn tất cả nguồn trả `ABSTAINED_NO_SOURCE_SELECTED`.
- **Vướng mắc** — PDF thiếu ví dụ `git remote` chạy riêng nên câu so sánh chỉ trả phần minh họa `git remote -v`. Câu cuối có một diễn giải nhắc HTTPS, ví dụ được dẫn dùng SSH.
- **Bước tiếp theo** — Không còn.

### integrate-surfsense-backend · Tích hợp mã backend SurfSense

- **Prompt và ràng buộc** — Dùng mã nguồn backend SurfSense trong WorkspaceAI, theo ngữ cảnh hỏi đáp có trích dẫn. Giữ hợp đồng API và dữ liệu notebook.
- **Điều kiện hoàn thành** — Mã upstream có nguồn và giấy phép rõ, được gọi từ luồng hỏi đáp hiện có và qua kiểm thử.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất tích hợp mã vào luồng Chat Feature 1 và kiểm chứng với Ollama cục bộ.
- **Mốc đã hoàn tất** — Điều chỉnh mã đánh số, phân giải nguồn và bảo vệ tag của SurfSense tại `b764f28`. Dùng ID đoạn trong JSON để backend xác định trang/dòng từ trích đoạn. Đã bỏ nhãn dòng trong văn bản đưa cho model sau khi thấy Qwen chép nhãn vào đoạn trích.
- **Code đã cập nhật tới** — Working tree: module và giấy phép Apache 2.0, prompt QA, bộ đọc phản hồi, bảo toàn tọa độ trích dẫn hợp lệ và kiểm thử đường `/api/chat`.
- **Kiểm tra** — 166 test liên quan đạt, Ruff và `git diff --check` đạt. Qwen cục bộ trả `source_id: 1`, trích `guide.txt` trang 7 dòng 2, kết quả `VERIFIED_EXACT` và `SUPPORTED` khi bật xác minh ngữ nghĩa.
- **Vướng mắc** — Bản chạy thử đọc mã trong working tree. Chưa dựng lại image Docker của WorkspaceAI.
- **Bước tiếp theo** — Không còn trong phạm vi tích hợp mã nguồn.

### feature1-prompt-dataset · Bổ sung bộ câu mẫu Feature 1

- **Prompt và ràng buộc** — Chọn nội dung liên quan đến WorkspaceAI từ ba hướng dẫn đã giới thiệu: Microsoft CLU, Dialogflow CX Agent Design và Dialogflow CX No-match.
- **Điều kiện hoàn thành** — Có bộ câu mẫu lưu trong repo, nguồn tham khảo và kiểm thử chạy qua luồng thật; xử lý ca thiếu phạm vi.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã cập nhật backend Docker và xác minh luồng hỏi lại qua API.
- **Mốc đã hoàn tất** — Đã tìm đúng ba liên kết trong chat Feature 1 và đối chiếu tài liệu chính thức. Đã thêm 32 ca câu hỏi có nhãn thao tác, phạm vi nguồn, ngữ cảnh và hành vi mong đợi.
- **Code đã cập nhật tới** — Working tree: fixture JSON, test pytest, hướng dẫn trong README và nhận diện câu tổng quan/hỏi tiếp theo chương trong QA.
- **Kiểm tra** — 171 test liên quan qua và app/frontend Docker healthy. Qua API, hai câu thiếu ngữ cảnh yêu cầu làm rõ, tham chiếu Chương 999 báo đúng mục không tồn tại, và “Tóm tắt phần đó” với ngữ cảnh Chương 8 trả đúng phần “Working with GitHub” từ trang 26.
- **Vướng mắc** — Bộ câu mẫu kiểm tra định tuyến, phạm vi và ngữ cảnh; chưa đánh giá chất lượng sinh câu trả lời của model trên toàn bộ 32 ca.
- **Bước tiếp theo** — Không còn.

### database-create · Tạo database MySQL cho WorkspaceAI

- **Prompt và ràng buộc** — Tạo database dựa trên khung WorkspaceAI đã thảo luận, gồm tài khoản, phạm vi notebook và các bảng nghiệp vụ hiện có. Giữ dữ liệu đang lưu.
- **Điều kiện hoàn thành** — Có schema chạy được và lệnh khởi tạo trong Docker. Kiểm tra các bảng, quan hệ và lưu dữ liệu qua lần khởi động lại.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Database `workspace_ai` chạy trên MySQL 8.4.13 tại `127.0.0.1:3307`.
- **Mốc đã hoàn tất** — Khởi tạo 11 bảng, thêm khóa ghép phạm vi notebook, cấp tài khoản MySQL cục bộ và xác nhận volume giữ dữ liệu qua lần restart. Đã dọn các hàng thử.
- **Code đã cập nhật tới** — Working tree trên `Pgkhiem31_UpdateProject/full-project` có DDL, Compose MySQL, hợp đồng frontend, kiểm thử hợp đồng và hướng dẫn chạy. Backend và trình duyệt vẫn dùng cơ chế lưu hiện tại, chưa chuyển dữ liệu hoặc triển khai đăng nhập.
- **Kiểm tra** — Compose config hợp lệ, 33 test frontend và build đạt. MySQL thật chấp nhận cùng nguồn ở hai notebook, từ chối trùng trong một notebook và liên kết chéo notebook, chặn xóa nguồn đang được trích dẫn. Container healthy sau restart và hàng thử tồn tại qua restart.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### database-users · Tài khoản và quyền truy cập notebook

- **Prompt và ràng buộc** — Giải thích database sẽ lưu người dùng thế nào trong khung WorkspaceAI. Bổ sung thiết kế, chưa triển khai đăng nhập.
- **Điều kiện hoàn thành** — Có trường dữ liệu tài khoản, quan hệ quyền với notebook và ví dụ. Nêu phần cần ngay và phần phụ thuộc phương thức đăng nhập.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất mô hình tài khoản và quyền trong notebook.
- **Mốc đã hoàn tất** — Mô tả `users`, khóa ghép và vai trò trong `workspace_members`, `auth_identities` theo phương thức đăng nhập và ví dụ cấp quyền.
- **Code đã cập nhật tới** — Cập nhật `database/DESIGN.md` và mốc này trong working tree. Chưa có migration hoặc luồng đăng nhập mới.
- **Kiểm tra** — Đối chiếu hiện trạng `X-Workspace-ID`, xác minh 14 liên kết trong tài liệu và chạy `git diff --check` cho blueprint.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### database-framework · Khung database WorkspaceAI

- **Prompt và ràng buộc** — Lên khung database, giải thích ý nghĩa và mức độ cần thiết của từng thành phần. Đối chiếu với dữ liệu dự án đang lưu.
- **Điều kiện hoàn thành** — Có mô hình quan hệ, bảng ưu tiên và phạm vi triển khai tối thiểu, kèm phân biệt giữa hiện trạng và đề xuất.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất khung database và kiểm tra tài liệu.
- **Mốc đã hoàn tất** — Đối chiếu tám bảng MySQL với các điểm lưu hiện tại. Chốt bảy bảng MVP, ERD, ràng buộc phạm vi notebook và tọa độ bằng chứng, cùng thứ tự bổ sung Studio và email.
- **Code đã cập nhật tới** — Working tree có `database/DESIGN.md` và mốc này trong `BLUEPRINT.md`. Chưa áp dụng migration.
- **Kiểm tra** — Đối chiếu schema, Docker và mã nguồn. Xác minh đủ 11 liên kết Markdown và chạy `git diff --check` cho blueprint. Đây là kiểm tra tài liệu thiết kế.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### feature1-detailed-chapter · Bao phủ chương khi người dùng yêu cầu nêu chi tiết

- **Prompt và ràng buộc** — Sửa câu “Hãy nêu chi tiết những gì trong chương 8” trong ảnh. Giữ giới hạn tài liệu đã chọn, khoảng dòng và kiểm chứng ngữ nghĩa.
- **Điều kiện hoàn thành** — Nhận diện yêu cầu nêu chi tiết chương cụ thể, bao phủ các tiểu mục có trong dàn ý và kiểm chứng nguyên văn trên Docker.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã triển khai backend Docker và kiểm tra nguyên văn câu hỏi qua API.
- **Mốc đã hoàn tất** — Chương 8 Git có 9 tiểu mục. Câu trong ảnh không khớp định tuyến theo dàn ý nên rơi vào truy xuất vài đoạn.
- **Code đã cập nhật tới** — Working tree: nhận diện yêu cầu nêu chi tiết chương, giữ các phần có nguồn riêng qua nhiều trang, hiển thị quy trình dòng lệnh và bảng tag theo nguyên văn, thêm test hồi quy.
- **Kiểm tra** — 130 test liên quan qua, git diff --check qua. Docker healthy. PDF thật trả đủ 8.1–8.9, dẫn trang 26–28, đủ tám mốc tag và phân biệt lệnh `git remote -v` với đầu ra. Lượt cuối 13,91 giây.
- **Vướng mắc** — Các ví dụ terminal và lưu ý đi kèm giữ tiếng Anh gốc. Chưa chạy lại toàn bộ test ngoài phạm vi liên quan.
- **Bước tiếp theo** — Không còn.

### feature1-outline-subsection-question · Câu hỏi chương kèm yêu cầu giải thích

- **Prompt và ràng buộc** — Sửa câu 2 nguyên văn trong ảnh, bám các tiểu mục và giữ kiểm chứng nguồn. Kiểm tra lại câu 8 và 9.
- **Điều kiện hoàn thành** — Câu ghép đi đúng luồng theo chương, có giải thích hoặc trích đoạn theo từng tiểu mục và không suy diễn từ công thức lỗi.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã cập nhật backend Docker và thử nguyên văn cả ba câu trong ảnh.
- **Mốc đã hoàn tất** — Xác định regex fullmatch loại câu có yêu cầu thứ hai.
- **Code đã cập nhật tới** — Working tree: nhận diện câu ghép hỏi theo chương, gom một lượt sinh ghi chú từng tiểu mục, giữ tên tiểu mục xuyên qua verifier và dùng trích đoạn thật khi diễn giải thiếu căn cứ; thêm test hồi quy.
- **Kiểm tra** — 128 test liên quan qua, git diff --check qua. Docker healthy. Câu 2 trả 3 tiểu mục trích trang 4, 14, 16 (2 ý SUPPORTED và một trích đoạn gốc); câu 8 trả định nghĩa có điều kiện và dẫn trang 4; câu 9 báo ký hiệu hỏng tại trang PDF 72.
- **Vướng mắc** — Chưa sửa lỗi ký hiệu lớp văn bản PDF. Trích đoạn mục 1.2 còn giữ cách trích xuất ký hiệu từ file.
- **Bước tiếp theo** — Không còn.

### feature1-grounded-reasoning · Xác minh suy luận theo bằng chứng

- **Prompt và ràng buộc** — Sửa A/C theo dòng và context, thêm kiểm tra nguồn hỗ trợ kết luận, thử Thinking chọn lọc. Giữ API tương thích.
- **Điều kiện hoàn thành** — Không xác minh quote sai dòng/ngoài context; phân biệt nhận định có nguồn, bị bác bỏ và chưa đủ dữ liệu; có test hồi quy.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Bản backend Docker healthy. Kiểm tra ngữ nghĩa bật, Thinking chọn lọc tắt mặc định.
- **Mốc đã hoàn tất** — Lookup giới hạn đúng line range và đoạn đã gửi. Tóm tắt ngắn và hỏi đáp dùng chung nguồn context; note map chỉ được lưu nếu nguồn hỗ trợ.
- **Code đã cập nhật tới** — Working tree: verifier, repository lookup, QA, document summary, provider, cấu hình Docker, helper kiểm tra kết luận và kiểm thử hồi quy.
- **Kiểm tra** — 127 test liên quan qua, git diff --check qua. Toàn repo 806 pass, 53 fail, 4 error. Ca Toán giữ phát biểu đúng và loại hai kết luận thiếu căn cứ. PDF thật đạt 3/5 lần đầu (121,17 giây), xử lý bổ sung đạt 5/5 (15,85 giây), cache cuối đủ 5/5 có SUPPORTED (0,23 giây). Ca so sánh hai nguồn: mặc định giữ cả hai hạn (20,4 giây), bật Thinking thử rồi fallback không có đáp án đã xác minh (49,36 giây).
- **Vướng mắc** — Bộ kiểm tra ngữ nghĩa dùng model nên vẫn có sai số; ca mở rộng miền xác định có chốt tất định riêng. Một phép thử Thinking chưa đủ kết luận tổng quát.
- **Bước tiếp theo** — Không còn.

### feature1-citation-outline-review · Phân tích phạm vi citation và dàn ý

- **Prompt và ràng buộc** — Phân tích A (line range), B (cha/con) và C (packet so với nguồn gốc). Chỉ phân tích.
- **Điều kiện hoàn thành** — Đối chiếu các nhánh QA, summary và search index, xác minh bằng ví dụ nhỏ và nêu hướng sửa.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất đối chiếu phạm vi nguồn.
- **Mốc đã hoàn tất** — Đã đọc verifier, search index, outline và hai nhánh tóm tắt.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Quote nằm ở dòng 40 nhưng khai 10–12 cho VERIFIED_EXACT với lookup toàn trang và UNGROUNDED_QUOTE với windows. Dàn ý cha dòng 1–6 chứa hai con 2–3 và 4–6; packet bỏ ký hiệu lỗi ở dòng 5.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### notebook-current-state · Kiểm tra cách notebook đang hoạt động

- **Prompt và ràng buộc** — Giải thích NotebookLM hiện đang hoạt động thế nào. Kiểm tra bản trong workspace và phân biệt với dịch vụ Google.
- **Điều kiện hoàn thành** — Mô tả luồng xử lý, engine đang phục vụ nếu xác minh được và giới hạn hiện tại.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất xác minh runtime và đối chiếu luồng xử lý.
- **Mốc đã hoàn tất** — WorkspaceAI chạy riêng với Ollama/Qwen; Google đã đổi tên NotebookLM thành Gemini Notebook.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Docker app và frontend healthy, Ollama đang chạy; `/api/runtime` trả HTTP 200 trên cổng 8501 và 8001 với `qwen3.5:9b-q4_K_M`. Đã đọc luồng Chat và đối chiếu với tài liệu chính thức của Google.
- **Vướng mắc** — Lần này chỉ kiểm tra trạng thái dịch vụ và cấu hình runtime, chưa chạy lại bộ kiểm thử chất lượng câu trả lời.
- **Bước tiếp theo** — Không còn.

### feature1-source-consistency · Dàn ý, độ dài và nhất quán nguồn

- **Prompt và ràng buộc** — Sửa luồng chung từ hai ví dụ Git và Toán thuộc hai note riêng. Tổng quát hóa cho nguồn khác, không gắn quy tắc với tên tài liệu. Kiểm thử dữ kiện mâu thuẫn, danh sách đánh số và công thức lỗi.
- **Điều kiện hoàn thành** — Dàn ý và mức chi tiết đúng yêu cầu, trích dẫn nằm trong phạm vi, có kiểm thử hồi quy với dữ liệu thực và ca biên.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã triển khai Docker và xác minh hai note riêng qua API.
- **Mốc đã hoàn tất** — PDF Toán có 5 bookmark cấp chương; trước sửa bộ lập dàn ý tạo thêm số bài tập. Trang PDF 72 đã có ký hiệu hỏng trong lớp văn bản. Đã đối chiếu dàn ý Toán 5 chương và Git 22 chương + 4 phụ lục.
- **Code đã cập nhật tới** — Working tree: ưu tiên cấu trúc rõ, đọc style DOCX và Markdown, phát hiện danh sách và dòng đầu trang, phân biệt tóm gọn/chi tiết, không đưa nhận định mới từ reduce vào kết quả, cache theo phiên bản và cấu trúc, khoanh nguồn trích dẫn và báo ký hiệu PDF không đọc được.
- **Kiểm tra** — 116 test Feature 1 và nguồn qua, 33 test frontend qua. Toàn repo 801 pass, 53 fail, 4 error. Qwen thử hai nguồn có hai ngày nộp khác nhau và dẫn riêng từng nguồn; nguồn thứ ba không được chọn bị loại. Các ca hồi quy gồm PDF không bookmark, DOCX, Markdown, TXT, tiêu đề lặp, nguồn trùng tên, trích dẫn ghép và bài 40. Docker: Toán tóm gọn 5/5 (18,25 giây; cache 0,06 giây), chi tiết 5/5 (27 ý, 125,43 giây; tổng quan khớp số chương), Chương 1 cho 3 tiểu mục, bài 40 báo trang 72. Git tóm gọn 26/26 (63,72 giây; cache 0,10 giây), chương 1 dẫn trang 5 và từ chối gọi nguồn Toán trong note Git.
- **Vướng mắc** — PDF thiếu hoặc hỏng lớp văn bản vẫn cần đối chiếu bản gốc hoặc OCR riêng. Chưa có kiểm chứng ngữ nghĩa tuyệt đối cho mọi nhận định tự do.
- **Bước tiếp theo** — Không còn.

### fix-chat-chapter · Sửa truy xuất chương và Markdown trong Chat

- **Prompt và ràng buộc** — Câu trả lời Git quá thô, Markdown hiện ký hiệu thô và Chương 1 bị nhầm với Python Bootcamp. Giữ nguyên phạm vi nguồn và xác minh trích dẫn.
- **Điều kiện hoàn thành** — Markdown trong câu trả lời hiển thị đúng. Câu hỏi theo số chương trích đúng phần đã chọn.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã triển khai app và frontend Docker, cả hai healthy.
- **Mốc đã hoàn tất** — Đã đối chiếu PDF, Chương 1 về quản lý phiên bản (trang 5), Chương 2 về cài đặt và cấu hình Git (trang 7).
- **Code đã cập nhật tới** — Working tree: nhận diện câu hỏi theo số chương và đọc trong phạm vi dàn ý, tái dùng ghi chú có nguồn, nhóm và diễn giải các lệnh Git bằng tiếng Việt, hiển thị Markdown nội dòng.
- **Kiểm tra** — 96 test Feature 1, 33 test frontend, frontend build và git diff --check đều qua. Thử bốn câu trong ảnh qua API và Chrome headless. Git hiển thị 24 dòng trong 5 nhóm với code nội dòng và nguồn trang 73. Mục 1/Chương 1 dẫn trang 5, Chương 2 dẫn trang 7.
- **Vướng mắc** — Kiểm tra trên PDF thật dùng cache đã có. Luồng chưa có cache được kiểm thử bằng model giả.
- **Bước tiếp theo** — Không còn.

### fix-summary-crash · Điều tra lỗi khi nhập “tóm tắt”

- **Prompt và ràng buộc** — Điều tra “tóm tắt” có vẻ bị crash và câu “hãy nêu những lệnh git quan trọng” báo thiếu bằng chứng. Giữ nguyên bộ xác minh trích dẫn và phạm vi tài liệu được chọn.
- **Điều kiện hoàn thành** — Sửa lỗi đã tái hiện, có kiểm thử hồi quy và thử cả hai câu trên bản Docker.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã triển khai và xác minh qua API và trình duyệt.
- **Mốc đã hoàn tất** — Docker không restart hoặc OOM. Log ghi cache hit chờ 121–149 giây trong lần tái hiện. Sau sửa, QAService trích đúng 24 nhóm lệnh Git ở trang 73 của PDF, tất cả VERIFIED_EXACT.
- **Code đã cập nhật tới** — Working tree: `document_summary.py` khóa theo đường dẫn cache, `qa_service.py` trích từng dòng từ bảng lệnh đúng tài liệu được chọn và dùng chung bước xác minh; thêm kiểm thử hồi quy cho hai luồng.
- **Kiểm tra** — 95 test Feature 1 và 33 test frontend qua. Docker app và frontend healthy. Qua proxy: “tóm tắt” bao phủ 26/26 mục trong 0,184 giây từ cache, liệt kê lệnh có 24 nhóm với nguồn trang 73 trong 0,019 giây. Đã gửi cả hai câu qua Chrome headless, cả hai hiển thị và không có lỗi console.
- **Vướng mắc** — Không tái hiện được trình duyệt bị văng. Lần tạo cache đầu cho PDF mất 189 giây ở lần đo trước khi triển khai bản sửa; bản sửa xử lý thời gian chờ giữa workspace.
- **Bước tiếp theo** — Không còn.

### fix-chat-send-stop · Sửa lỗi gửi tự dừng

- **Prompt và ràng buộc** — Sửa lỗi bấm gửi khiến câu hỏi bị ngắt.
- **Điều kiện hoàn thành** — Một thao tác gửi gọi API đúng một lần, nút Stop chỉ hủy khi người dùng bấm.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất và đã cập nhật Docker.
- **Mốc đã hoàn tất** — Log Docker có yêu cầu Chat bị trình duyệt ngắt. Đã tách nút Gửi và Stop, bỏ thao tác nhấp lặp của cùng một cú nhấp đúp.
- **Code đã cập nhật tới** — Working tree, `frontend/src/Chat.tsx`.
- **Kiểm tra** — Build và 33 kiểm thử frontend đạt. Chrome với API mô phỏng xác nhận nhấp đúp không hủy, Stop chủ động vẫn dừng và Enter gửi đúng một lần. Docker phục vụ bundle mới, container healthy và API Chat trả `CONVERSATION` cho câu kiểm tra.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### stop-chat-generation · Dừng phản hồi đang tạo

- **Prompt và ràng buộc** — Thêm thao tác chủ động dừng khi Chat đang suy nghĩ.
- **Điều kiện hoàn thành** — Dừng yêu cầu đang chờ, giữ câu hỏi và cho phép gửi tiếp.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất và đã cập nhật Docker.
- **Mốc đã hoàn tất** — Stop hủy yêu cầu phía trình duyệt, giữ câu hỏi, bỏ phản hồi đến muộn và cho phép gửi tiếp. Backend có thể tiếp tục xử lý yêu cầu đã nhận.
- **Code đã cập nhật tới** — Working tree, đã thêm nút Stop và hủy yêu cầu ở trình duyệt trong `Chat.tsx`, `api.ts`, `data.ts`.
- **Kiểm tra** — Build và 33 kiểm thử đạt. Chrome với phản hồi mô phỏng xác nhận Stop và gửi lại. Docker frontend healthy và phục vụ bundle có nút Stop.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### source-upload-motion · Chỉ báo tải nguồn và nút kẹp giấy

- **Prompt và ràng buộc** — Gỡ nút kẹp giấy trong ô chat và làm chuyển động lúc tải tài liệu.
- **Điều kiện hoàn thành** — Ô chat không còn nút kẹp giấy, cột Sources phản hồi trong khi tải và xử lý, hỗ trợ giảm chuyển động.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất và đã cập nhật Docker.
- **Mốc đã hoàn tất** — Đã bỏ nút kẹp giấy và thêm chuyển động xoay cho biểu tượng tải.
- **Code đã cập nhật tới** — Working tree nhánh `Pgkhiem31_UpdateProject/full-project`, sửa `Chat.tsx`, `Sources.tsx` và `notebook.css`.
- **Kiểm tra** — Build và 33 kiểm thử đạt. Chrome với tải chậm mô phỏng xác nhận đã bỏ nút, biểu tượng xoay trong lúc tải, tôn trọng chế độ giảm chuyển động và biến mất khi xử lý xong. Docker frontend healthy và phục vụ CSS mới.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### deploy-hierarchical-summary-docker · Triển khai tổng hợp phân cấp lên Docker

- **Prompt và ràng buộc** — Đưa bản cập nhật mới nhất trong working tree lên Docker cục bộ.
- **Điều kiện hoàn thành** — Backend và frontend healthy, bản mới có luồng tổng hợp phân cấp, cache và thời gian chờ tương ứng.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất.
- **Mốc đã hoàn tất** — Đã dựng lại app và frontend. Compose xác nhận hai container healthy.
- **Code đã cập nhật tới** — Dùng bản đang có trên nhánh `Pgkhiem31_UpdateProject/full-project`.
- **Kiểm tra** — Compose build và wait thành công. Frontend và API tài liệu phản hồi qua cổng 8501. Runtime báo Ollama Qwen 3.5 9B. Sáu tệp trong container khớp SHA-256 với working tree và Nginx dùng timeout 545 giây.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### diagnose-test-python · Khắc phục lệnh kiểm thử dùng sai Python

- **Prompt và ràng buộc** — Đọc log pytest và script đánh giá Feature 1 vừa được dán.
- **Điều kiện hoàn thành** — Xác định interpreter và kiểm chứng lệnh thay thế trong môi trường có thư viện.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất xác minh lệnh.
- **Mốc đã hoàn tất** — Log cho thấy Python hệ thống thiếu thư viện ngay khi import test và script.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Python hệ thống báo thiếu `fastapi`, `pypdf`, `rank_bm25`, `streamlit`. Python trong `.venv-schema-audit` import thành công, script chạy `--help` và 102 test Feature 1 cùng lưu thư viện đạt.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### implement-hierarchical-summary · Tổng hợp phân cấp tài liệu dài

- **Prompt và ràng buộc** — Dựng dàn ý PDF, map–reduce, kiểm tra bao phủ, lưu cache theo phiên bản và thêm script đánh giá. Giữ API và luồng truy xuất tương thích.
- **Điều kiện hoàn thành** — Có nguồn theo chương, chỉ thử lại phần thiếu, cache dùng lại và có kiểm thử tự động.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất triển khai mã và nghiệm thu cục bộ.
- **Mốc đã hoàn tất** — Thêm dàn ý, map–reduce, đối chiếu trích dẫn, thử lại phần thiếu, lưu cache JSON và script đánh giá. Lượt Qwen tuần tự chỉ đạt 11/26 và lượt ưu tiên chương với 16K đạt 18/26. Giảm lượt map xuống 4K để Qwen nằm trong VRAM và dùng schema ràng buộc mã chương, số đoạn nguồn sau khi thấy đầu ra tự do không ổn định.
- **Code đã cập nhật tới** — Working tree; đã sửa parser, metadata, lưu thư viện, QA, provider và thời gian chờ frontend.
- **Kiểm tra** — PDF 78 trang với Qwen 3.5 9B đạt 26/26 mục, không còn mục bị đánh dấu đọc thiếu, 57/57 trích đoạn khớp nguồn. Lượt đầu 210,86 giây, lượt đọc cache 0,24 giây. Ruff, TypeScript, Vite build và 33 test frontend đạt. Pytest 789 đạt, 53 fail và 4 lỗi đã tái hiện trên HEAD cùng môi trường.
- **Vướng mắc** — Chưa chấm tay toàn bộ nhận định, chưa đo với Gemini thật. Tổng hợp chạy khi người dùng yêu cầu, chưa chạy nền khi tải lên. Thay đổi nằm trong working tree.
- **Bước tiếp theo** — Không còn trong phạm vi triển khai và nghiệm thu được yêu cầu.

### plan-summary-quality · Đề xuất thuật toán nâng chất lượng tổng hợp

- **Prompt và ràng buộc** — Đối chiếu hai ảnh trên cùng PDF Git/GitHub và nêu các logic, thuật toán cần sửa.
- **Điều kiện hoàn thành** — Chỉ ra nguyên nhân trong mã, thứ tự cải tiến và tiêu chí so sánh chất lượng.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất đề xuất thuật toán và thước đo.
- **Mốc đã hoàn tất** — Xác định nhánh Ollama dài lấy mẫu 10.000 ký tự, cắt 280 ký tự mỗi đoạn, yêu cầu 5–8 ý sau tổng quan, bỏ lượt bổ sung và chỉ đối chiếu sự tồn tại của trích đoạn.
- **Code đã cập nhật tới** — Chỉ ghi tiến độ trong blueprint.
- **Kiểm tra** — Đã đối chiếu hai ảnh với `qa_service.py`, `llm_provider.py` và `citation_verifier.py`. Đề xuất lập dàn ý theo chương, tổng hợp phân cấp, kiểm tra độ bao phủ và mức hỗ trợ của nguồn, đo trên bộ PDF có đáp án chuẩn.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn trong phạm vi phân tích.

### synthesize-long-pdf · Tổng hợp ý nghĩa của tài liệu dài

- **Prompt và ràng buộc** — Feature 1 cần giải thích nội dung và mối liên hệ giữa các chủ đề khi hỏi toàn bộ PDF.
- **Điều kiện hoàn thành** — Tạo phần tổng quan và các ý diễn giải có dẫn nguồn, kiểm tra với PDF Git/GitHub.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất và cập nhật Docker.
- **Mốc đã hoàn tất** — Xác định Qwen hết thời gian và ứng dụng chuyển sang trích nguyên văn. Đã thêm chế độ tổng hợp gọn cho tài liệu dài với dẫn nguồn theo số đoạn.
- **Code đã cập nhật tới** — Sửa `qa_service.py`, `llm_provider.py` và `test_ollama_grounding.py` trong working tree.
- **Kiểm tra** — 85 kiểm thử đạt. Với PDF 78 trang, Qwen chạy 15,5 giây và sinh 6 ý tiếng Việt có nguồn, gồm tổng quan. Ngữ cảnh có chương cuối và phụ lục. Đã cập nhật app Docker, container healthy và truy cập qua cổng 8501 thành công.
- **Vướng mắc** — Bản tổng hợp cô đọng dựa trên ngữ cảnh đại diện. Kết quả thử còn bỏ qua một số phần sau, gồm Python Bootcamp và phụ lục. Trích dẫn khớp nguồn theo vị trí, chưa kiểm tra semantic từng ý.
- **Bước tiếp theo** — Không còn.

### deploy-summary-fix-docker · Chạy bản sửa Feature 1 trên Docker

- **Prompt và ràng buộc** — Dựng và chạy ứng dụng Docker với bản sửa tổng hợp PDF.
- **Điều kiện hoàn thành** — Container phục vụ bản sửa và API phản hồi sau khi cập nhật.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất.
- **Mốc đã hoàn tất** — Dựng và chạy image app và frontend mới. API qua frontend phản hồi và báo engine Ollama.
- **Code đã cập nhật tới** — Dùng bản sửa Feature 1 trong working tree.
- **Kiểm tra** — `docker compose up --build --detach --wait --wait-timeout 120 app frontend` thành công. Hai container healthy, frontend HTTP 200 ở cổng 8501 và regex định tuyến mới chạy trong container app.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### fix-git-tutorial-summary · Sửa tóm tắt toàn bộ PDF

- **Prompt và ràng buộc** — Feature 1 trả lời quá hẹp khi hỏi “Hãy nêu chi tiết những gì có trên file” với PDF hướng dẫn Git/GitHub.
- **Điều kiện hoàn thành** — Câu gốc đi vào nhánh tổng hợp, lấy ngữ cảnh từ các phần chính và có kiểm thử hồi quy.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất sửa định tuyến và kiểm tra trên PDF gốc.
- **Mốc đã hoàn tất** — Câu gốc trước đây chỉ vào nhánh tra cứu 5 đoạn. Đã sửa cách hỏi “trên file”, giữ đoạn đầu chương và ưu tiên các chương chính trong chế độ trích đoạn dự phòng.
- **Code đã cập nhật tới** — Working tree nhánh `Pgkhiem31_UpdateProject/full-project`. Đã sửa `backend/services/feature1/qa_service.py` và `tests/test_ollama_grounding.py`.
- **Kiểm tra** — 84 kiểm thử đạt. PDF gốc có 78 trang và 911 đoạn. Qwen thực nhận 98 đoạn có đủ 22 chương và 4 phụ lục, nhưng hết thời gian sau 115 giây. Mô phỏng model không trả kết quả với mã cuối xác nhận 31 trích đoạn có nguồn từ đủ 22 chương và 4 phụ lục.
- **Vướng mắc** — Gemini thật chưa được kiểm chứng trên PDF. Kiểm tra tự động từ chối gửi PDF ra Gemini vì thiếu cho phép cụ thể.
- **Bước tiếp theo** — Không còn trong phạm vi sửa mã. Cần cho phép gửi PDF tới Gemini nếu muốn xác nhận thêm chất lượng đầu ra của engine này.

### explain-fresh-checkout-setup · Xác minh cách chạy dự án sau khi pull

- **Prompt và ràng buộc** — Giải thích người khác lấy nhánh đã đẩy về có chạy được như máy hiện tại không. Không đọc hoặc ghi khóa API cục bộ.
- **Điều kiện hoàn thành** — Xác định điều kiện để chạy bản code đã push và những phần phải cài hoặc cấu hình riêng.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất hướng dẫn chạy trên máy mới và điều kiện tái tạo cấu hình.
- **Mốc đã hoàn tất** — Xác định `36e36ae` là commit cần kiểm tra. README gốc tham chiếu tệp `.env.example` đã được loại khỏi nhánh.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Commit có `requirements.txt`, `frontend/pnpm-lock.yaml` và `Start-Workspace.ps1`. Launcher Offline thiết lập provider và biến frontend, không bắt buộc `.env`. Compose đánh dấu `.env` không bắt buộc. Dữ liệu workspace và lịch sử trình duyệt không đi qua Git. Chưa chạy thử trên máy sạch.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### create-project-issue · Tạo issue trên GitHub

- **Prompt và ràng buộc** — Tạo issue trong `hoanghaiviet100-creator/WorkSpaceAI`. Chủ đề cần được xác định để nội dung đúng ý người dùng.
- **Điều kiện hoàn thành** — Issue được tạo trên GitHub với chủ đề đã xác nhận và trả về liên kết.
- **Trạng thái** — Đang làm.
- **Bước hiện tại** — Chờ người dùng xác định chủ đề issue.
- **Mốc đã hoàn tất** — Đã xác định repository và công cụ tạo issue. Đã gửi câu hỏi làm rõ chủ đề.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Đã đối chiếu nội dung vừa trao đổi và commit `36e36ae`.
- **Vướng mắc** — Chưa rõ issue cần ghi nhận nội dung nào.
- **Bước tiếp theo** — Soạn và tạo issue khi người dùng xác định chủ đề.

### missing-local-library-store · Giải thích tệp thiếu trên GitHub

- **Prompt và ràng buộc** — Giải thích vì sao `local_library_store.py` có ở máy nhưng thiếu trong thư mục `repositories` trên GitHub.
- **Điều kiện hoàn thành** — Xác định đường dẫn, trạng thái theo dõi, quy tắc loại nếu có và sự có mặt trong commit đã đẩy.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Xác nhận tệp có trên nhánh đã đẩy.
- **Mốc đã hoàn tất** — GitHub trả về tệp `backend/repositories/local_library_store.py` trên `Pgkhiem31_UpdateProject/full-project`; blob trùng với `HEAD` và ref theo dõi cục bộ.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — `git ls-files` và `git ls-tree` xác nhận tệp đã được theo dõi và có trong `36e36ae`. `git check-ignore -v` chỉ báo quy tắc `__pycache__/` trong hai đường dẫn kiểm tra. Ảnh không hiện tên nhánh hoặc commit.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### verify-full-project-push · Xác minh nhánh đã được push hay chưa

- **Prompt và ràng buộc** — Xác minh liệu toàn bộ dự án đã được đẩy lên nhánh riêng, theo các điều kiện loại tệp đã chốt.
- **Điều kiện hoàn thành** — Đối chiếu `HEAD`, index và nhánh trên `origin` rồi báo trạng thái thực tế.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã xác nhận push thành công và kiểm tra phạm vi cây tệp.
- **Mốc đã hoàn tất** — `HEAD` và ref cục bộ của `origin/Pgkhiem31_UpdateProject/full-project` cùng ở `36e36ae`. Cây commit có 219 tệp và không có đường dẫn thuộc nhóm bị loại.
- **Code đã cập nhật tới** — Chỉ ghi mốc xác minh trong working tree.
- **Kiểm tra** — GitHub trả về nhánh `Pgkhiem31_UpdateProject/full-project` và commit `36e36ae`. `git rev-list --left-right --count` trả về `0 0`. `git ls-tree` xác nhận 219 tệp, không có tệp env hay tệp từ `.agents/`, `.claude/`, `.codex/`.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

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
- **Mốc đã hoàn tất** — Xác nhận đang ở `Pgkhiem31_UpdateProject/full-project`. Người dùng đã stage toàn bộ thay đổi thuộc phạm vi. Ba thư mục bị loại là untracked và không xuất hiện trong các đối tượng Git chưa có ở remote theo các ref cục bộ.
- **Code đã cập nhật tới** — Index thật có 136 tệp thay đổi, gồm hai thay đổi xóa tệp mẫu env khỏi cây commit. Mốc xác minh mới của blueprint nằm trong working tree.
- **Kiểm tra** — `git ls-files` không trả về tệp env hay tệp trong ba thư mục bị loại. Hai bản mẫu còn trên máy. `git diff --cached --check` đạt. Các commit chưa đẩy chỉ tham chiếu bản mẫu đã có trên remote theo dữ liệu cục bộ.
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

### compare-surfsense · So sánh WorkspaceAI với SurfSense

- **Prompt và ràng buộc** — So sánh dự án hiện tại với SurfSense 2.3.1 đã phân tích. Đối chiếu mã nguồn và chỉ ghi mốc trong blueprint.
- **Điều kiện hoàn thành** — Nêu khác biệt về luồng tài liệu, truy xuất, trích dẫn, tính năng và triển khai dựa trên mã nguồn hai bên.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất đối chiếu working tree WorkspaceAI với SurfSense `b764f28`.
- **Mốc đã hoàn tất** — Đã xác định nhánh hiện tại và đối chiếu nhập liệu, công thức xếp hạng, việc lưu chỉ mục, xác minh trích dẫn, tóm tắt theo chương, Studio, email và Docker.
- **Code đã cập nhật tới** — Nhánh `Pgkhiem31_UpdateProject/full-project`, HEAD `36e36ae`, có thay đổi sẵn trong working tree. Tác vụ chỉ bổ sung mốc vào `BLUEPRINT.md`.
- **Kiểm tra** — Đối chiếu các điểm vào và cấu hình triển khai trong mã nguồn hai bên. Không chạy benchmark.
- **Vướng mắc** — Môi trường từ chối truy cập Docker socket và HTTP localhost, nên chưa xác nhận runtime đang chạy.
- **Bước tiếp theo** — Không còn.

### surfsense-inspired-development · Áp dụng truy xuất của SurfSense vào WorkspaceAI

- **Prompt và ràng buộc** — Áp dụng các cơ chế SurfSense giúp kết quả WorkspaceAI chính xác và đầy đủ. Giữ trích dẫn trang/dòng, dữ liệu cũ và phạm vi nguồn đã chọn.
- **Điều kiện hoàn thành** — Lưu và tái sử dụng vector đoạn, xếp hạng kết hợp hai tín hiệu, đọc đủ nguồn ngắn với câu hỏi bao quát và kiểm tra hồi quy.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất kiểm thử tự động và đối chiếu tài liệu Git thật qua Ollama cục bộ.
- **Mốc đã hoàn tất** — Đã đọc blueprint; xác định các điểm ghi thư viện; triển khai chỉ mục dẫn xuất theo mã bộ mã hóa, công thức xếp hạng kết hợp và bổ sung ngữ cảnh có giới hạn cho câu hỏi bao quát.
- **Code đã cập nhật tới** — Working tree nhánh hiện tại: repository, lưu thư viện, bộ mã hóa, bootstrap workspace, dịch vụ tài liệu, QA, README và kiểm thử truy xuất mới.
- **Kiểm tra** — 145 kiểm thử Feature 1, truy xuất, thư viện và API qua. git diff --check qua. Câu git remote -v có 2 nhận định SUPPORTED từ trang 26 trong 23,63 giây. Câu chương 8 trả đủ 8.1–8.9 từ trang 26–28 trong 15,45 giây, gồm 2 nhận định SUPPORTED và 8 trích đoạn nguyên văn đã xác minh. Hai ca chỉ dẫn nguồn đã chọn.
- **Vướng mắc** — Docker mặc định dùng bộ băm từ. Chưa đánh giá truy xuất đa ngôn ngữ bằng mô hình embedding chuyên dụng. Kiểm thử tài liệu thật chạy từ working tree qua Ollama, chưa dựng lại container app.
- **Bước tiếp theo** — Không còn.

### compare-thinking-mode · Kiểm tra chế độ suy luận của WorkspaceAI và SurfSense

- **Prompt và ràng buộc** — Giải thích model hiện tại có suy luận theo cách SurfSense vận hành hay không.
- **Điều kiện hoàn thành** — Phân biệt khả năng của model, trạng thái cấu hình của ứng dụng và kiểm chứng nguồn.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Hoàn tất đối chiếu SurfSense, mã nguồn WorkspaceAI và Docker đang chạy.
- **Mốc đã hoàn tất** — Đã phân biệt công tắc Thinking của SurfSense Basic, Thinking chọn lọc của WorkspaceAI và bước xác minh nguồn.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — API WorkspaceAI báo qwen3.5:9b-q4_K_M. Ollama /api/show báo hỗ trợ Thinking bật/tắt và mặc định bật. Container đặt FEATURE1_SELECTIVE_THINKING=false và FEATURE1_SEMANTIC_VERIFY=true.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.

### compare-project-fit · Chọn WorkspaceAI hay SurfSense theo nhu cầu

- **Prompt và ràng buộc** — Đánh giá bên nào hơn với WorkspaceAI hiện tại và SurfSense 2.3.1.
- **Điều kiện hoàn thành** — Kết luận theo mục đích sử dụng và nêu mức kiểm chứng của kết quả.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Đã chốt kết luận theo mục đích sử dụng.
- **Mốc đã hoàn tất** — WorkspaceAI phù hợp hơn với hỏi theo trang/dòng, theo chương và luồng học. SurfSense có phạm vi xử lý tệp và công cụ rộng hơn. Chưa xếp hạng độ chính xác chung.
- **Code đã cập nhật tới** — Chỉ ghi mốc trong blueprint.
- **Kiểm tra** — Tái sử dụng kết quả kiểm thử và xác nhận Docker đã ghi ở các mục liên quan.
- **Vướng mắc** — Chưa có benchmark trên cùng bộ câu hỏi và cùng mô hình.
- **Bước tiếp theo** — Không còn.

### surfsense-roadmap · Lộ trình phát triển WorkspaceAI theo SurfSense

- **Prompt và ràng buộc** — Lên hướng phát triển sau khi WorkspaceAI đã áp dụng lưu vector và truy xuất kết hợp. Ưu tiên chất lượng hỏi đáp tiếng Việt và bằng chứng theo trang/dòng.
- **Điều kiện hoàn thành** — Chốt thứ tự triển khai, tiêu chí đo chất lượng và bước có thể bắt đầu tiếp.
- **Trạng thái** — Đã xong phần lập lộ trình.
- **Bước hiện tại** — Đã đối chiếu mã nguồn và kết quả kiểm tra của phiên bản mới với cấu hình Docker hiện có.
- **Mốc đã hoàn tất** — Chốt thứ tự đưa bản truy xuất mới vào Docker và đo mốc gốc, thử embedding đa ngôn ngữ local, mở rộng đọc nguồn có giới hạn, bổ sung OCR theo nhu cầu. Giữ xác minh bằng chứng và luồng học tập hiện có.
- **Code đã cập nhật tới** — Lượt này chỉ ghi lộ trình trong blueprint.
- **Kiểm tra** — Đã đọc mốc 145 kiểm thử và ca Git 8.1–8.9. Chưa chạy thử nghiệm hoặc dựng Docker trong lượt này.
- **Vướng mắc** — Chưa có bộ benchmark chung cho truy xuất Việt–Anh. Dịch vụ Ollama hiện giới hạn một model nạp đồng thời, cần đo tác động nếu dùng chung cho embedding và sinh trả lời.
- **Bước tiếp theo** — Bản truy xuất đã chạy trong Docker và có mốc đo ở mục deploy-benchmark-surfsense-retrieval. Bước tiếp theo là thử embedding đa ngôn ngữ local trên cùng bộ câu hỏi.

### deploy-benchmark-surfsense-retrieval · Triển khai và đo truy xuất WorkspaceAI trên Docker

- **Prompt và ràng buộc** — Tiến hành bước tiếp theo trong lộ trình SurfSense. Dựng lại backend Docker và đo chất lượng trên cùng câu hỏi trước và sau, với Ollama và nguồn đã chọn.
- **Điều kiện hoàn thành** — Backend mới healthy, nội dung mã trong container khớp working tree, API qua frontend phục vụ đúng và có kết quả đối chiếu nguồn, độ bao phủ, thời gian.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Backend mới đang chạy healthy; đã đo đủ năm câu hỏi trước và sau.
- **Mốc đã hoàn tất** — Đã xác nhận app/frontend healthy, backend chưa có mã truy xuất mới, Qwen 3.5 9B chạy trong Ollama cục bộ, tài liệu Git có 78 trang. Sau triển khai, API qua frontend xác nhận cùng model và cùng hash tài liệu. Thư viện cũ đã lưu 913 vector subword-hash:384:v1.
- **Code đã cập nhật tới** — Bản cũ image 292af2741eb4. Bản mới image 4effb431cef3, chỉ dựng lại backend app. Sáu tệp triển khai khớp SHA-256 với working tree. Frontend và Ollama tiếp tục phục vụ.
- **Kiểm tra** — Bản cũ: đoạn đích của truy vấn chính xác hạng 1, hai ca diễn đạt lại và xuyên ngôn ngữ ngoài top 5. API: lệnh chính xác 18,88 giây, diễn đạt lại từ chối 6,82 giây, xuyên ngôn ngữ từ chối 0,26 giây, chương 8 đủ 9/9 trong 11,17 giây và ca thiếu nguồn từ chối trong 6,31 giây. Bản mới: lệnh chính xác vẫn hạng 1, API đúng trang 26 trong 17,60 giây; diễn đạt lại và xuyên ngôn ngữ vẫn ngoài top 5 và API từ chối sau 6,69 và 0,04 giây; chương 8 vẫn đủ 9/9, dẫn trang 26–28 trong 10,16 giây; ca thiếu nguồn từ chối trong 0,05 giây. Không có trích dẫn ngoài nguồn. Truy xuất ba câu từ 230,96/267,66/253,13 ms xuống 28,24/24,75/20,74 ms.
- **Vướng mắc** — Độ bao phủ của hai ca diễn đạt lại và xuyên ngôn ngữ chưa cải thiện bằng embedding băm từ hiện tại. Mỗi ca đo một lượt trên một tài liệu; số đo là mốc thử nghiệm.
- **Bước tiếp theo** — Không còn trong đợt triển khai. Dùng năm ca này làm mốc khi thử embedding đa ngôn ngữ.

### fix-paraphrased-remote-query · Sửa câu hỏi diễn đạt lại trong ảnh

- **Prompt và ràng buộc** — Sửa ca “How do I display the fetch and push URLs of configured remotes?” với một nguồn Git đã chọn. Giữ giới hạn nguồn và xác minh trang/dòng.
- **Điều kiện hoàn thành** — Câu hỏi nguyên văn trả lệnh git remote -v và dẫn đoạn có lệnh; ca ngoài nguồn vẫn từ chối.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Backend mới image f3bc3f1ab783 healthy, mã QA khớp SHA-256 và đã xác minh ba ca qua frontend.
- **Mốc đã hoàn tất** — Câu gốc xếp đoạn đích trang 26 ở hạng 10; truy vấn từ khóa rút gọn xếp hạng 1 và Ollama xác minh câu trả lời từ trang 26, dòng 92.
- **Code đã cập nhật tới** — QA bổ sung một lượt tìm bằng từ khóa rút gọn cho câu hỏi thủ tục tiếng Anh rồi đưa một đoạn phù hợp vào ngữ cảnh; thêm kiểm thử giữ đúng nguồn.
- **Kiểm tra** — 146 kiểm thử liên quan qua, git diff --check qua. Câu nguyên văn qua localhost:8501 trả git remote -v, nguồn Git đã chọn, trang PDF 26 dòng 92–93, VERIFIED_EXACT và SUPPORTED trong 22,98 giây. Ca Sputnik cùng kiểu câu hỏi vẫn báo thiếu bằng chứng; bỏ chọn nguồn trả ABSTAINED_NO_SOURCE_SELECTED.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn trong ca này. Ca tiếng Việt truy xuất đoạn tiếng Anh là mục thử embedding đa ngôn ngữ riêng.

### fix-summary-partial-coverage · Sửa báo cáo độ bao phủ và nội dung tóm tắt

- **Prompt và ràng buộc** — Sửa ca trong ảnh có thông báo 3/3 trong khi phần yêu cầu hệ thống còn thiếu và có lời hướng dẫn đọc thay cho nội dung. Giữ bằng chứng và giới hạn nguồn.
- **Điều kiện hoàn thành** — Hiển thị đúng số mục đủ nội dung, tóm tắt nêu thông tin trong tài liệu và xác minh ca nguyên văn.
- **Trạng thái** — Đã xong.
- **Bước hiện tại** — Bản Docker backend d68a47e96eb2 healthy. Đã xác minh câu nguyên văn và lượt đọc từ cache qua frontend.
- **Mốc đã hoàn tất** — Khớp chính xác cache ảnh với Team_8_Proposal.pdf. Tiêu đề bookmark rút gọn làm mất mục 2.1, còn cache coi đủ ngay khi mỗi chương có một ghi chú. Đã nhận lại ba tính năng 2.1.1–2.1.3 từ thân PDF.
- **Code đã cập nhật tới** — Sửa outline_builder.py, document_summary.py và kiểm thử hồi quy. Docker backend cuối image d68a47e96eb2, hai tệp khớp SHA-256. Bỏ mục bìa/mục lục và tiêu đề trống trước tiểu mục, ưu tiên ghi chú có nội dung, phục hồi phần thiếu và hiển thị số mục đầy đủ riêng.
- **Kiểm tra** — 148 kiểm thử liên quan qua và git diff --check qua. Lượt Docker đầu 285,04 giây và báo đúng 2/3. Sau tinh chỉnh, câu nguyên văn trả 3/3 mục đầy đủ với 16 ghi chú VERIFIED_EXACT và SUPPORTED, gồm 2.1.1–2.1.3, yêu cầu phi chức năng và ca sử dụng ở trang 13–16. Chỉ dẫn nguồn PDF đã chọn. Lượt bổ sung 62,53 giây, lượt cache 0,06 giây.
- **Vướng mắc** — Không có.
- **Bước tiếp theo** — Không còn.
