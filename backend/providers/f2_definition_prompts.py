"""Shared exact-definition prompts for external F2 adapters; Q05 unchanged."""
from backend.algorithms.f2_flashcard_generation import DEFAULT_MAX_BACK_WORDS
from backend.providers.f2_flashcard_provider import build_flashcard_prompt
from backend.providers.f2_quiz_provider import build_quiz_prompt
from backend.providers.f2_study_provider import StudyEvidence


def _definition_policy(study_format: str) -> str:
    # Extracted verbatim from Gemini so both vendors use the same constraints.
    common = (
        "\nGiới hạn của phiên thử Q05: chỉ dùng các định nghĩa term/body rõ ràng trong nguồn. "
        "Giữ nguyên term và toàn bộ body (kể cả ngôn ngữ, phủ định, đơn vị, điều kiện); "
        "chỉ gộp khoảng trắng/xuống dòng. Không dịch, diễn giải, rút gọn hoặc thêm kiến thức. "
        "Bỏ định nghĩa mâu thuẫn hoặc nhiều term có cùng body; nếu không đủ thì trả ít hơn hoặc [].\n"
    )
    if study_format == "quiz":
        return common + (
            'Mẫu question chính xác: "Khái niệm nào được mô tả sau đây?\\n{body}". '
            "Các options là những term khác nhau có trong nguồn; correct_option_id chỉ term của body đó. "
            'Mẫu explanation chính xác: "Theo đoạn nguồn, {term}: {body}". '
            "source_ids trỏ định nghĩa hỗ trợ trực tiếp. Cần ít nhất hai term rõ ràng để tạo Quiz.\n"
        )
    return common + 'Mẫu front chính xác: "{term} là gì?"; back là toàn bộ body của term đó.\n'


def build_definition_quiz_prompt(evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
    return build_quiz_prompt(evidence, requested_count) + _definition_policy("quiz")


def build_definition_flashcard_prompt(evidence: tuple[StudyEvidence, ...], requested_count: int) -> str:
    return build_flashcard_prompt(evidence, requested_count,
        max_back_words=DEFAULT_MAX_BACK_WORDS) + _definition_policy("flashcards")
