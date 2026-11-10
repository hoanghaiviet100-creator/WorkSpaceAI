# Workspace: Nguồn – Hội thoại – Studio

## Bảng màu sáng theo ảnh mẫu (09/11/2026)

Bộ màu sáng hiện dùng nền lavender `#F0ECF6`, khung trắng tím `#FCFBFE`, nền phụ `#F1ECF7`, hồng nhạt `#F6E8EF`, cam đào `#F78F67`. Chữ chính `#28232F`, chữ phụ `#6B6274`, cam chữ `#9A4228`, tím nhấn `#825576`. Ô nhập có nền gần trắng và viền đào–hồng nhẹ; khung chat có trường màu lavender/hồng mờ theo ảnh tham khảo. Nút cam dùng chữ nâu đậm `#452310` để vẫn dễ đọc.

Các màu này chỉ áp dụng khi chế độ sáng đang hoạt động, bao gồm Home và hộp thoại. Chế độ tối giữ bảng màu cũ. Chín cặp màu chữ kiểm tra đạt tối thiểu 4.5:1; kết quả cụ thể ở `.taste-skill/light-v8/palette-checks.json`. Các quy định về bố cục, kích thước và chức năng bên dưới giữ nguyên; các hàng màu sáng trong bảng gốc được thay thế bởi bảng màu này.

## Cập nhật khung chat (09/11/2026)

Chat trống dùng bố cục giữa theo ảnh tham khảo: biểu tượng sách của WorkspaceAI, lời gợi mở, ba câu hỏi hiện có dạng nút ngắn và ô nhập lớn bo góc. Khi đã có tin nhắn, ô nhập trở về đáy khung. Chỉ tiếp thu bố cục và cách phân cấp thị giác; không thêm AI Agent, Report, Workflow, Recommended hay các thẻ chức năng của ảnh mẫu.

Đã bỏ nút Thêm nguồn trong chat. Tải tài liệu ở cột Nguồn; nút Đang dùng N nguồn vẫn mở phần lựa chọn. Đã gỡ toàn bộ Preview Desktop/Phone và khung điện thoại mô phỏng. Bố cục tự theo chiều rộng thật; trình chọn màu sáng/tối vẫn được giữ.

## Vấn đề UX và cách xử lý

Giao diện ba cột dễ bị rối khi mỗi cột có menu riêng, nhiều vùng cuộn và các nút tạo kết quả trùng nhau. Người dùng cũng dễ nhầm nguồn đang chọn với nguồn đã dùng trong câu trả lời cũ.

Phiên bản này giữ **một hội thoại cho mỗi workspace**. Nguồn nằm bên trái, kết quả Plan/Email nằm bên phải, ô nhập luôn ở cuối cột giữa. Lựa chọn nguồn hiện tại không thay đổi khi mở lại chat; mỗi câu trả lời và kết quả giữ danh sách nguồn tại thời điểm tạo. Trên điện thoại, chỉ một phần xuất hiện mỗi lần.

## Wireframe

Desktop, từ 1200px:

```text
┌────────────────────────────────────────────────────────────────────┐
│ ←  Tên workspace ✎                           Chia sẻ  Cài đặt  Avatar│
├────────────────┬─────────────────────────────┬──────────────────────┤
│ NGUỒN       ◁  │ HỘI THOẠI                  │ STUDIO             ▷ │
│ + Thêm nguồn   │ Tóm lược phạm vi nguồn      │ [Lên kế hoạch] [Email]│
│ Tìm / lọc      │ [Gợi ý 1] [Gợi ý 2] [Gợi ý 3]│                      │
│ Chọn tất cả ☑  │                    Bạn: ...│ Kết quả | Ghi chú    │
│ Tài liệu A  ☑ ⋯│ Trợ lý: ... [1] [2]        │ Kết quả mới nhất   ⋯ │
│ Tài liệu B  ☐ ⋯│ Sao chép · Lưu · Đánh giá   │ Kết quả trước đó   ⋯ │
│                │                             │                      │
│  cuộn riêng    │─────────────────────────────│     cuộn riêng       │
│                │ Nhập câu hỏi…               │                      │
│                │ Đang dùng N nguồn       [↑] │                      │
└────────────────┴─────────────────────────────┴──────────────────────┘
```

Tablet, 768–1199px:

```text
┌───────────────────────────────────────────────────────┐
│ ← Tên workspace                    Chia sẻ  ⚙  Avatar│
│ [Nguồn] [Studio]                                      │
├───────────────────────────────────┬───────────────────┤
│ Hội thoại chung                   │ Nguồn HOẶC Studio │
│ Tin nhắn và trích dẫn             │ chuyển bằng nút   │
│                                   │                   │
│───────────────────────────────────│                   │
│ Nhập câu hỏi…                  ↑  │                   │
└───────────────────────────────────┴───────────────────┘
```

Mobile, dưới 768px:

```text
┌──────────────────────────────┐
│ ← Tên workspace     ↗ ⚙ Avatar│
├──────────────────────────────┤
│ Nguồn / Chat / Studio        │
│ (một phần tại một thời điểm) │
│                              │
│ Nếu đang ở Chat:             │
│ ──────────────────────────── │
│ Nhập câu hỏi…             ↑  │
├──────────────────────────────┤
│   Nguồn     Chat     Studio  │
└──────────────────────────────┘
```

## Hệ thống thiết kế

| Thành phần | Quy định |
| --- | --- |
| Màu thương hiệu | Cam `#E85002`; chữ trên nền cam là `#171717` |
| Cam cho chữ/liên kết | Sáng `#A13700`; tối `#FF9A63`, tránh dùng cam thương hiệu làm chữ nhỏ trên trắng |
| Màu nhấn phụ | Teal sáng `#236C64`, tối `#8BCEC3`, chủ yếu cho biểu tượng Email và kết quả |
| Nền sáng | Canvas `#F3F3F1`, panel `#FFFFFF`, nền phụ `#F6F6F4` |
| Nền tối | Canvas `#111111`, panel `#1D1D1D`, nền phụ `#252525` |
| Chữ | Sáng `#242424` / phụ `#646464`; tối `#F3F3F1` / phụ `#B8B8B2` |
| Viền | Sáng `#E4E4E1`, tối `#383838`; focus dùng màu cam cho chữ |
| Phông chữ | Be Vietnam Pro, đóng gói trên máy, 400/500/600; một phông cho toàn bộ UI |
| Phân cấp | Tên workspace 17px; tiêu đề panel 14px/600; câu trả lời 13px, dòng 1.9; mô tả 12px; metadata 11–12px |
| Khoảng cách | Hệ 8px: 8/16/24/32px; 4px chỉ dùng cho chi tiết nhỏ |
| Lưới | Khung 12 cột logic, chia ba vùng theo nội dung. CSS dùng rail 300px + chat linh hoạt + rail 360px; từ 1600px rail 320/380px |
| Header | Desktop 64px; mobile 56px; không cuộn theo transcript |
| Bo góc | Panel 16px; ô nhập 16px; thẻ công cụ/menu 12px; hàng và input 8px |
| Bóng | Panel không có bóng. Menu/preview trích dẫn dùng bóng nhẹ `0 8px 24px #0002` |
| Vùng bấm | Mobile tối thiểu 44px, tab dưới 64px cộng vùng an toàn của thiết bị |
| Trạng thái | Hover trung tính, focus nhìn rõ, active nhẹ, disabled thực, loading theo yêu cầu API, lỗi có hướng xử lý |

Chữ chính và chữ phụ trên các nền panel tương ứng vượt ngưỡng WCAG AA 4.5:1. Không dùng màu làm dấu hiệu duy nhất: nguồn có tên/trạng thái, menu có nhãn, kết quả lỗi có nội dung và nút thử lại. Menu hỗ trợ phím mũi tên, Home/End, Escape; hộp thoại giữ focus và trả focus khi đóng. Studio có hai tab với trạng thái được thông báo; các thao tác cơ bản dùng phần tử button/input gốc.

## Các quyết định chính

- **Không có thanh quản lý nhiều chat.** Các tin nhắn cũ được xếp theo thời gian vào một luồng. Giữ nguyên bản gốc ở `legacyThreads`, đồng thời sao lưu dữ liệu trước chuyển đổi nếu bộ nhớ trình duyệt còn đủ.
- **Studio chỉ có hai thẻ.** Registry `STUDIO_TOOLS` quy định thẻ Plan và Email; cấu trúc lưới tự thêm hàng khi mở rộng. Không đưa chức năng tương lai vào giao diện hiện tại.
- **Giữ công cụ cũ trong ngữ cảnh kết quả.** Bảng task, duyệt đề xuất, Requirements và Reconciliation vẫn mở từ Studio. Email vẫn dùng trình soạn và các bước duyệt đã có. Tạo Email không tự gửi.
- **Lịch sử là các snapshot riêng.** Lưu tên, thời gian, nguồn đã dùng, nội dung và trạng thái; đổi tên nguồn hay chọn nguồn khác không viết lại lịch sử kết quả.
- **Trích dẫn kiểm tra được.** Chip số xem trước đoạn gốc khi hover/focus; bấm mở văn bản đã lập chỉ mục, đánh dấu dòng liên quan. Không thay văn bản của phiên bản cũ bằng phiên bản mới.
- **Không mô phỏng tiến trình.** Hiển thị thanh chuyển động khi API đang chạy, không gán phần trăm giả. Tải lại giữa chừng chuyển tác vụ sang lỗi có nút Thử lại.
- **Hai nút Landing đã bỏ theo đánh dấu.** Giữ nút New workspace ở hero và lịch sử workspace ngay bên dưới; bỏ nút ở header và nút trong banner cuối trang.

## Phạm vi thực tế và cải tiến tiếp theo

Đang hỗ trợ PDF có lớp văn bản, DOCX, PPTX, TXT, MD, CSV; dán văn bản và nhập liên kết HTTP/HTTPS công khai. DOCX được đọc thành một trang văn bản, PPTX theo thứ tự slide thực tế. PDF scan cần OCR. Trang nguồn hiển thị văn bản trích xuất, chưa phải bộ xem file Office/PDF nguyên bản.

Offline hiện dùng tìm kiếm và tổng hợp theo quy tắc. Plan tạo đề xuất dựa trên trích dẫn đã xác minh, không tự gán hạn hay người phụ trách. Plan được buộc xử lý Offline ngay cả khi Feature 1 được cấu hình AI ở tương lai. Email tạo bản nháp qua luồng đã có; launcher vẫn dùng gửi mô phỏng. Chia sẻ hiện sao chép liên kết mở trên thiết bị, chưa có cộng tác hoặc phân quyền máy chủ.

Nên ưu tiên tiếp: lưu chat và lịch sử Studio lên backend; lưu trữ bền vững bản nháp đã ký; đăng nhập/chia sẻ thực; bộ xem PDF với vùng tô sáng; OCR cho file scan. Khi có API streaming thực, có thể bổ sung dòng trả lời dần thay cho trạng thái chờ hiện tại.

Kiểm tra thực hiện và ảnh các kích thước nằm trong `.taste-skill/workspace-v6/`. Bộ đọc Office đối chiếu tài liệu chính thức Microsoft: [Word paragraphs](https://learn.microsoft.com/en-us/office/open-xml/word/working-with-paragraphs), [presentation slides](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-presentation-slides).
