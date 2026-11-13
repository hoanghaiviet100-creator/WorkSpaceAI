"""Broader source-content prompts over existing HTTP adapters; no fake output."""
from dataclasses import asdict
from html import escape
import json

from backend.algorithms.f2_content_support import build_learning_objectives
from backend.providers.f2_flashcard_provider import build_flashcard_prompt
from backend.providers.f2_gemini_provider import GeminiStudyProvider
from backend.providers.f2_quiz_provider import build_quiz_prompt
from backend.providers.f2_study_provider import StudyEvidence


def build_source_content_prompt(evidence: tuple[StudyEvidence, ...], requested_count: int, study_format: str,
                                *, style: str = "learning") -> str:
    if study_format not in ("quiz", "flashcards"):
        raise ValueError("expected quiz or flashcards")
    base = (build_quiz_prompt(evidence, requested_count) if study_format == "quiz"
            else build_flashcard_prompt(evidence, requested_count))
    if style not in ("learning", "cloze"):
        raise ValueError("expected learning or cloze style")
    if style == "learning":
        goals = build_learning_objectives(tuple((e.source_id, e.source_ref.evidence_quote) for e in evidence))
        # IDs/headings are untrusted source-derived data, shared across formats.
        goal_data = escape(json.dumps([asdict(goal) for goal in goals], ensure_ascii=False), quote=False)
        remember = max(1, requested_count // 5) if requested_count >= 3 else 1
        understand = (requested_count - remember + 1) // 2
        apply = requested_count - remember - understand
        plan = f"Mục tiêu số lượng tối đa: {remember} nhớ, {understand} hiểu, {apply} vận dụng. "
        if study_format == "flashcards" and requested_count == 3:
            plan = "Mục tiêu số lượng tối đa: 1 nhớ, 1 hiểu, 1 vận dụng. "
        instructions = (
            "\nYêu cầu chất lượng học liệu: Không giới hạn ở cặp term/definition. "
            "Hãy đọc hiểu các khái niệm, sự kiện, quy tắc, điều kiện, ví dụ và quy trình trong nguồn để viết câu hỏi tự nhiên, đầy đủ ngữ cảnh. "
            "Câu hỏi phải tự đủ thông tin để trả lời: nêu rõ tên hàm/đối tượng/điều kiện liên quan. "
            "Không dùng 'this function', 'hàm này', 'đoạn trên' khi chưa xác định chủ thể ngay trong câu hỏi. "
            "Nếu nguồn thiếu tên/chủ thể cần thiết, bỏ qua nội dung đó thay vì đoán tên từ kiến thức ngoài. "
            "Ưu tiên câu hỏi hiểu, so sánh hoặc vận dụng thông tin đã được nguồn trình bày rõ; chỉ một đáp án đúng, các phương án nhiễu hợp lý và khác nhau. "
            "Không tạo câu chỉ chép nguyên văn rồi xóa một chỗ [___]. "
            "Giải thích vì sao đáp án được chọn phù hợp với nguồn, giữ nguyên điều kiện/phủ định/đơn vị và chỉ dùng source_ids thực sự hỗ trợ. "
            "Trả đúng JSON Schema đã cấp để web dựng câu hỏi tương tác; câu tự nhiên có thể cần review, không tự tuyên bố VERIFIED. "
            "Không tự giải bài tập Toán/Lý, tính kết quả mới hoặc chứng minh mệnh đề; phần đó chưa hỗ trợ.\n"
        )
        instructions += (
            "Hai loại học liệu phải bám cùng danh sách mục tiêu dưới đây. Chọn source_ids thực sự chứng minh mục tiêu, không dùng heading đứng riêng làm bằng chứng. "
            + plan + "Nếu không đủ căn cứ thì trả ít hơn, không tự tạo quy tắc hay dữ kiện nguồn. "
            "Trong tình huống mới được nêu dữ kiện giả định rõ ràng; quy tắc/thứ tự/cách suy ra phải có trong nguồn. "
            "Dùng tiền tố Nhớ:, Hiểu: hoặc Vận dụng: để người học nhận biết mục tiêu. Cloze là style riêng, không trộn vào style này.\n"
            "Các dạng có phép kiểm độc lập hiện có (thay phần {...} bằng dữ liệu nguồn, giữ chủ thể rõ ràng):\n"
            'Nhớ: Theo tài liệu, "{term}" là gì? -> đáp án {definition}; giải thích: Theo nguồn: {term}: {definition}\n'
            'Hiểu: Theo hai định nghĩa trong tài liệu, khi phân biệt "{a}" với "{b}", cặp mô tả nào khớp? -> đáp án {a}: {definition_a}; {b}: {definition_b}; '
            'giải thích: Theo nguồn: {a}: {definition_a}\\n{b}: {definition_b}\n'
            'Vận dụng: Tình huống "{case}" có đặc điểm "{definition}". Khái niệm nào có định nghĩa khớp đặc điểm này trong tài liệu? -> đáp án {term}; '
            'giải thích: Tình huống "{case}": {definition}\\nTheo nguồn: {term}: {definition}\n'
            'Nhớ: Trong quy trình "{title}", bước đầu tiên là gì?\n'
            'Hiểu: Trong quy trình "{title}", bước nào đứng ngay sau "{step}"? (hoặc ngay trước)\n'
            'Vận dụng: Trong quy trình "{title}", tình huống "{case}" đã hoàn thành "{step}". Cần thực hiện bước nào tiếp theo?\n'
            'Vận dụng: Trong quy trình "{title}", tình huống "{case}" cần bắt đầu "{step}". Bước nào phải được hoàn thành ngay trước đó?\n'
            'Đáp án quy trình lấy nguyên nội dung bước; giải thích: Theo quy trình "{title}": bước {n} là {answer} '
            '(thêm \\nBước {m} là {given_step} cho câu sau/trước). Không thêm bước chưa có.\n'
            'Nhớ: Theo quy tắc "{title}", điều kiện nào dẫn đến "{action}"?\n'
            'Hiểu: Theo quy tắc "{title}", điều kiện nào bảo đảm kết quả "{action}"?\n'
            'Đáp án là điều kiện đủ đầy đủ; giải thích: Theo quy tắc "{title}": {condition} bảo đảm kết quả "{action}".\n'
            'Vận dụng: Theo quy tắc "{title}", tình huống "{case}" có dữ kiện: {field} = {new_value}; {field2} = {value2}. Kết quả nào được áp dụng?\n'
            'Đáp án là kết quả suy ra từ nguồn. Giải thích: Dữ kiện: {same_facts}.\\nÁp dụng: {nguyên văn quy tắc đúng điều kiện}.\\nKết luận: {action}.\n'
            "Phép kiểm quy tắc hỗ trợ các mệnh đề If ... , then choose ... được ghi rõ trong nguồn, AND và so sánh ngưỡng/nhãn, giữ nguyên đơn vị. "
            "Đây không phải solver số học. Không biến văn bản không rõ ràng thành quy tắc chắc chắn. "
            "Các diễn giải ngoài những dạng chứng minh được vẫn có thể tạo để review, không tự VERIFIED.\n"
        )
        if study_format == "flashcards":
            instructions += (
                "Với Flashcards: front là câu hỏi theo mục tiêu; back gồm đáp án ngắn ở dòng đầu, xuống dòng rồi giải thích đúng mẫu của cùng mục tiêu. "
                "Giữ back <=60 từ, source_ids hỗ trợ cả hai phần. Chỉ trả root cards/front/back/source_ids theo schema Flashcards, không trả root questions/options.\n"
            )
        return base + instructions + '\n<learning_objectives untrusted="true">' + goal_data + "</learning_objectives>"
    policy = (
        "\nPhạm vi: khái niệm, sự kiện, quy tắc, điều kiện áp dụng, ví dụ và các bước thực hiện đã có trong nguồn. "
        "Không giới hạn ở cặp term/definition. Có thể đặt câu hỏi tự nhiên; mọi đáp án/giải thích phải có trích dẫn hỗ trợ, "
        "giữ đầy đủ phủ định, điều kiện, đơn vị và ngữ cảnh. Không thêm kiến thức để đủ số lượng. "
        "Mỗi item chỉ dùng source_ids có liên quan trực tiếp. "
        "Không tự giải bài tập Toán/Lý, tính kết quả mới hoặc chứng minh mệnh đề; phần đó chưa hỗ trợ.\n"
        "Để đối chiếu tự động, ưu tiên dạng điền nguyên văn: lấy TOÀN BỘ một evidence_quote, "
        "gộp khoảng trắng/xuống dòng và thay đúng một cụm đáp án bằng [___]. Giữ nguyên case và dấu câu. "
        "Ngữ cảnh ngoài chỗ trống cần ít nhất bốn từ. Không chèn nhãn [Dòng ...] vào câu trích. "
        "Câu hỏi tự nhiên/diễn giải có thể phải review, không được tự tuyên bố VERIFIED.\n"
    )
    if study_format == "quiz":
        policy += (
            'Mẫu cloze riêng: question="Điền nguyên văn theo đoạn trích:\\n{ngữ cảnh có [___]}"; '
            'explanation="Theo đoạn nguồn: {quote được khôi phục}". Chỉ một đáp án khôi phục nguyên văn.\n'
        )
    else:
        policy += (
            'Mẫu tự đối chiếu: front="Hoàn thành nguyên văn theo đoạn trích:\\n{ngữ cảnh có [___]}"; '
            "back là cụm đã bỏ, ngắn gọn và nguyên văn.\n"
        )
    return base + policy


class SourceContentProvider:
    """Explicit wrapper; preserves vendor name and delegates actual HTTP only."""
    def __init__(self, adapter, study_format: str, *, style: str = "learning"):
        if study_format not in ("quiz", "flashcards") or not callable(getattr(adapter, "generate_from_prompt", None)):
            raise ValueError("expected an F2 prompt transport and study format")
        self.adapter = adapter
        self.study_format = study_format
        if style not in ("learning", "cloze"):
            raise ValueError("expected learning or cloze style")
        self.style = style
        self.name = adapter.name

    def generate(self, evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
        prompt = build_source_content_prompt(evidence, requested_count, self.study_format, style=self.style)
        if isinstance(self.adapter, GeminiStudyProvider):
            return self.adapter.generate_from_prompt(prompt, self.study_format)
        return self.adapter.generate_from_prompt(prompt)
