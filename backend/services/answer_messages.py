"""Natural request-language messages for document questions."""
import re

def vietnamese(query):
    if re.search(r'(?:in English|bằng tiếng Anh|tiếng Anh nhé)',query,re.I): return False
    if re.search(r'(?:in Vietnamese|bằng tiếng Việt)',query,re.I): return True
    return bool(re.search(r'[\u0102-\u01b0\u1ea0-\u1ef9]',query))

def failure_message(query,code):
    vi=vietnamese(query)
    if code in ('GENERATION_PREPARING','MODEL_LOAD_TIMEOUT','GENERATION_RESIDENCY_LOST','GENERATION_MODEL_MISSING','GENERATION_INVALID_CONFIG','GENERATION_UNAVAILABLE'):
        from backend.services.generation_readiness import message
        return message(code,vi)
    if 'BUSY' in code:
        return 'Mình đang xử lý một yêu cầu khác. Bạn chờ một chút nhé.' if vi else 'Another request is being processed. Please wait a moment.'
    if 'RESOURCE' in code:
        return 'Máy hiện chưa đủ bộ nhớ để tiếp tục. Bạn hãy giải phóng bộ nhớ rồi thử lại nhé.' if vi else 'There is not enough available memory to continue. Please free some memory and try again.'
    if 'INVALID_INPUT' in code:
        return 'Bạn hãy rút ngắn câu hỏi hoặc bắt đầu cuộc trò chuyện mới nhé.' if vi else 'Please shorten your question or start a new conversation.'
    return 'Mình chưa thể hoàn thành câu trả lời từ các tài liệu đã chọn. Bạn thử lại sau nhé.' if vi else 'I could not complete an answer from the selected documents. Please try again later.'


def requests_bilingual(query):
    if re.search(r'\b(?:bilingual)\b|song ngữ',query,re.I):return True
    return bool(re.search(r'\b(?:answer|respond|reply)\b|trả lời',query,re.I)
                and re.search(r'Vietnamese|tiếng Việt',query,re.I)
                and re.search(r'English|tiếng Anh',query,re.I))
