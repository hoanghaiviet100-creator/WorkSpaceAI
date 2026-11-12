# Kanban trong WorkspaceAI

Tài liệu lịch sử. Kanban đã được gỡ khỏi giao diện cùng F2 ngày 11/11/2026.

## Mục tiêu và các điểm UX cần tránh

Một workspace có một bảng duy nhất. Công việc chính là xem điều cần làm tiếp theo, di chuyển thẻ và cập nhật nội dung. Bảng mở rộng toàn màn hình để không ép các cột vào Studio rộng 360px.

- Gợi ý tự động dễ khiến người dùng tưởng dữ liệu đã được lưu hoặc đã được xác minh. Bản xem trước ghi rõ **Chưa tạo bảng / Chưa thêm vào bảng**, nguồn gợi ý và số thẻ đang chọn. Chỉ **Xác nhận** mới ghi dữ liệu chính thức.
- Tạo lại bảng dễ ghi đè chỉnh sửa. Khi đã có bảng, hành động chuyển thành **Nhờ AI gợi ý thêm**; chỉ nối thẻ đã duyệt, bỏ thẻ trùng, giữ nguyên thẻ cũ. Không có danh sách bảng hoặc nút tạo bảng thứ hai.
- Màu ở mọi vị trí làm các thẻ khó đọc. Màu chỉ dành cho nhãn, nguồn gợi ý và ngày cần chú ý; cột và thẻ dùng nền trung tính.
- Kéo-thả không đủ cho mọi thiết bị. Nút kéo hỗ trợ chuột, cảm ứng và **Alt + mũi tên**. Trong chi tiết thẻ còn có ô chọn cột. Các cột có lệnh chuyển trái/phải trong menu.
- Xóa cột có thể làm mất công việc. Hộp xác nhận yêu cầu chuyển thẻ sang cột còn lại; cột cuối cùng không thể xóa. Xóa thẻ có hoàn tác, khôi phục riêng thẻ đó thay vì quay lui toàn bảng.

## Wireframe

Thẻ trong Studio:

```text
┌ Studio ─────────────────────┐
│ [Lên kế hoạch] [Soạn email] │
│ ┌ Kanban ───────── 8 thẻ ┐ │
│ │ Cần làm 4  Đang làm 2 │ │
│ │ Hoàn thành 2          │ │
│ │ ━━━━━░░░░░░░░  25%    │ │
│ │ Hạn gần nhất: 12/11   │ │
│ │ Mở bảng            → │ │
│ └──────────────────────┘ │
│ Kết quả và ghi chú đã lưu │
└──────────────────────────┘
```

Bảng mở rộng desktop:

```text
┌ Kanban · tên workspace ─────────────────────────── [×] ┐
│ Tên bảng · Đã lưu          [Nhờ AI gợi ý thêm] [Thu nhỏ]│
│ [Tìm trong bảng] [Nhãn] [Ưu tiên] [Hạn]     [+ Thêm cột]│
│ ┌ Cần làm · 4 ───┐ ┌ Đang làm · 2 ─┐ ┌ Hoàn thành · 2┐│
│ │ nhãn   AI   ⋯  │ │               │ │               ││
│ │ Tiêu đề thẻ    │ │     thẻ       │ │     thẻ       ││
│ │ hạn · ưu tiên  │ │               │ │               ││
│ │ checklist/nguồn│ │               │ │               ││
│ │  cuộn riêng    │ │  cuộn riêng   │ │  cuộn riêng    ││
│ │ + Thêm thẻ     │ │ + Thêm thẻ    │ │ + Thêm thẻ     ││
│ └────────────────┘ └───────────────┘ └───────────────┘│
│ 8 thẻ · 25% hoàn thành        Alt + mũi tên để di chuyển│
└───────────────────────────────────────────────────────┘
```

Mobile:

```text
┌ Kanban · workspace ─────── × ┐
│ Tên bảng      [Gợi ý] [Thu nhỏ]│
│ Đã lưu                        │
│ [Tìm trong bảng____________]  │
│ [Nhãn] [Ưu tiên] [Hạn]        │
│ [+ Thêm cột]                  │
│ ┌ Cần làm · 4 ─────────── ⋯ ┐ │
│ │ nhãn               AI  ⋯ │ │
│ │ Tiêu đề thẻ              │ │
│ │ hạn · ưu tiên            │ │
│ │ … cuộn riêng …           │ │
│ │ + Thêm thẻ               │ │
│ └──────────────────────────┘ │
│        ● Cần làm  ○  ○       │
└──────────────────────────────┘
```

Chi tiết thẻ:

```text
┌ Chi tiết thẻ ───────────────── × ┐
│ Tiêu đề                          │
│ [Loại: công việc/sự kiện] [Cột]  │
│ Mô tả                            │
│ [Ngày bắt đầu]       [Hạn chót]  │
│ [Ưu tiên]                        │
│ Nhãn [tên] [màu] [+]             │
│ Checklist [✓] nội dung     [×]   │
│ Nguồn liên quan [✓] tên tài liệu │
│ Ghi chú                          │
│ [Xóa] [Nhân bản] [Hủy] [Lưu]     │
└─────────────────────────────────┘
```

Luồng trạng thái:

```text
Trống → Tạo gợi ý → Đang đọc nguồn → Xem trước → Xác nhận → Bảng chính thức
                         ↓ lỗi          ↓ Hủy                 ↓
                      Thử lại         vẫn trống       Gợi ý thêm → Xem trước
                                                              ↓ Xác nhận
                                                       Chỉ nối thẻ mới
```

## Hệ thống thiết kế

| Thành phần | Giá trị |
| --- | --- |
| Phông | Be Vietnam Pro được đóng gói sẵn, 400/500/600; một họ phông |
| Cỡ chữ | Tên bảng 20px desktop / 18px mobile; tên cột và thẻ 14px; nội dung 12–13px; metadata 11–12px |
| Màu chủ đạo | Giữ cam thương hiệu #E85002; giao diện sáng dùng peach #F78F67, chữ nhấn #9A4228 theo bảng màu đã duyệt |
| Màu nhấn dữ liệu | Xanh ngọc: chữ #235C50 / nền #E1F1ED; chỉ dùng cho nhãn |
| Nền sáng | Bảng/thẻ #FCFBFE; cột #F1ECF7; chữ #28232F; phụ #6B6274 |
| Nền tối | Bảng theo canvas hiện tại; cột #1B1B1B; thẻ #252525; chữ theo token sáng của chế độ tối |
| Nhãn phụ | Cam #FFEADD / #853A1F; hồng #F9E6EB / #90364E; xám #EEEAF0 / #544D5C; có biến thể tối riêng |
| Ngày cần chú ý | Quá hạn: #A63544 trên nền sáng, #FFACB7 trong tối; sắp hạn trong 3 ngày dùng chữ nhấn. Có chữ “Quá hạn” / “Sắp đến”, không chỉ dựa vào màu |
| Khoảng cách | Hệ 8px: đệm 8/16/24px, khoảng cột 16px, khoảng thẻ 8px |
| Bo góc | Khung 16px; cột/thẻ 12px; input 8–10px |
| Độ rộng | Desktop cột chia đều, tối thiểu 240px; tablet 304px; mobile một cột theo vùng nhìn với scroll-snap và chỉ báo |
| Thao tác | Nút và vùng chọn checkbox tối thiểu 44px; viền focus 2px; giảm chuyển động theo thiết bị |
| Đổ bóng | Không có ở thẻ/cột tĩnh; chỉ thông báo hoàn tác nổi sử dụng bóng nhẹ |

Các chữ và nhãn được chọn theo tương phản AA. Màu nền/tone từ yêu cầu trước được giữ nguyên; không thêm gradient vào Kanban.

## Mã nguồn và dữ liệu

- `src/Kanban.tsx`: trạng thái trống/tạo/lỗi/xem trước/bảng, thẻ Studio, chi tiết, thêm nhanh, kéo-thả, thao tác bàn phím, bộ lọc, hoàn tác và cột.
- `src/kanban-model.ts`: kiểu dữ liệu, một bảng cho mỗi workspace, xác nhận có kiểm tra bảng hiện tại, nối không ghi đè, di chuyển và thống kê.
- `src/kanban-service.ts`: gợi ý Offline theo quy tắc, hoặc bản mẫu mô phỏng có gắn nhãn rõ.
- `src/kanban.css`: định dạng có phạm vi riêng, hai giao diện và ba mức kích thước.
- `NotebookWorkspace.tsx`, `Studio.tsx`, `Chat.tsx`: nối thẻ tóm tắt, khung mở rộng và chip kết quả vào hội thoại duy nhất.

`Workspace.kanban` lưu một object, không phải mảng nhiều bảng. Bản xem trước chỉ nằm trong trạng thái giao diện; hủy không tạo bảng. Sau xác nhận, bảng và thẻ lưu cùng workspace trong localStorage `workspaceai-v2`. Bản mẫu có 3 cột và 8 thẻ, trộn thẻ gợi ý và thủ công, ngày minh họa, nhãn và checklist; chỉ xuất hiện khi người dùng chọn **Thử giao diện với 8 thẻ mẫu**.

Mỗi thẻ có `taskId` liên kết Tasks hiện có. Lưu thẻ đồng bộ tiêu đề/mô tả/hạn/trạng thái, giữ owner và ánh xạ requirement. Chỉnh sửa từ Tasks hiện lại trong Kanban. Xóa thẻ lưu Tasks tương ứng dưới dạng archived để có thể hoàn tác. Thẻ mới tạo thủ công ở Tasks được đưa vào lần xem trước gợi ý tiếp theo; không tự chèn vào bảng đã duyệt. Cột tùy biến ánh xạ một trạng thái schema; tùy chọn **hoàn thành** quyết định tiến độ.

## Cách chạy và kiểm tra

Khởi động ứng dụng như [README](README.md). Trong workspace, mở **Studio → Kanban**. Có thể thử bản mẫu mà không cần khóa AI; chỉ bấm Xác nhận khi muốn lưu mẫu vào workspace đó.

```powershell
pnpm.cmd test
pnpm.cmd build
node tests/browser-kanban.mjs
```

Bài kiểm tra trình duyệt dùng cùng Chrome/Edge và helper CDP như `browser-file-picker.mjs`; có thể đặt `TASTE_CDP_PATH`. Bảng và nguồn kiểm thử nằm trên địa chỉ tạm riêng, không thay đổi workspace thật. Ảnh và kết quả lưu trong `.taste-skill/kanban-v10/`.

## Giới hạn và bước cải tiến tiếp theo

Ứng dụng vẫn Offline theo lựa chọn hiện tại. Nhãn “AI” biểu thị nguồn gợi ý; phần xem trước nói rõ hiện là gợi ý theo quy tắc, không có mô hình AI sinh nội dung. Bộ đọc xem tối đa 8 nguồn được chọn (trang đầu nếu phải lấy từ backend), công việc hiện có và 20 trao đổi gần nhất. Ngày chỉ được lấy khi có đủ ngày/tháng/năm rõ ràng: ISO, dd/mm/yyyy, dd.mm.yyyy hoặc tên tháng tiếng Anh; không tự đoán năm cho ngày thiếu thông tin.

Kanban chưa có API CRUD/SQL riêng hoặc cộng tác nhiều người. Để dùng nhiều thiết bị, bước tiếp theo là thêm lưu trữ backend, khóa duy nhất theo workspace và kiểm soát phiên bản sửa đổi. Sau đó mới nối mô hình AI thật khi được người dùng chọn, mở rộng trích xuất nhiều trang có tọa độ bằng chứng, và lịch sử phiên bản/hoạt động. Không bật thêm AI hoặc dịch vụ tính phí trong đợt cập nhật này.
