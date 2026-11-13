"""Reviewed-by-code-author candidates for synthetic PDFs; NOT live LLM output.

Used as controlled HTTP responses in tests and exported with an empty human
review sheet. Expected answers are explicit fixtures, not computed by Q05.
"""
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures/f2_learning"


def samples(topic, source_id):
    def quiz(question, choices, explanation):
        return {"question": question, "options": [{"option_id": chr(65 + i), "text": text} for i, text in enumerate(choices)],
            "correct_option_id": "A", "explanation": explanation, "source_ids": [source_id]}

    if topic == "concepts":
        a, b, c = "Batch processing", "Interactive processing", "Streaming processing"
        da = "Work runs without waiting for user input."
        db = "Work waits for user input before continuing."
        dc = "Work handles each arriving record immediately."
        questions = [
            quiz(f'Nhớ: Theo tài liệu, "{a}" là gì?', [da, db, dc], f"Theo nguồn: {a}: {da}"),
            quiz(f'Hiểu: Theo hai định nghĩa trong tài liệu, khi phân biệt "{a}" với "{b}", cặp mô tả nào khớp?',
                [f"{a}: {da}; {b}: {db}", f"{a}: {db}; {b}: {da}"], f"Theo nguồn: {a}: {da}\n{b}: {db}"),
            quiz(f'Hiểu: Theo hai định nghĩa trong tài liệu, khi phân biệt "{b}" với "{c}", cặp mô tả nào khớp?',
                [f"{b}: {db}; {c}: {dc}", f"{b}: {dc}; {c}: {db}"], f"Theo nguồn: {b}: {db}\n{c}: {dc}"),
            quiz(f'Vận dụng: Tình huống "NightJob-17" có đặc điểm "{da}". Khái niệm nào có định nghĩa khớp đặc điểm này trong tài liệu?',
                [a, b, c], f'Tình huống "NightJob-17": {da}\nTheo nguồn: {a}: {da}'),
            quiz(f'Vận dụng: Tình huống "Session-29" có đặc điểm "{db}". Khái niệm nào có định nghĩa khớp đặc điểm này trong tài liệu?',
                [b, a, c], f'Tình huống "Session-29": {db}\nTheo nguồn: {b}: {db}'),
        ]
    elif topic == "procedure":
        title = "Sample intake"
        steps = ["Register the sample.", "Assign a tracking code.", "Record storage conditions.",
                 "Place the sample in storage.", "Confirm the inventory entry."]
        questions = [
            quiz(f'Nhớ: Trong quy trình "{title}", bước đầu tiên là gì?', [steps[0], steps[1], steps[2]],
                f'Theo quy trình "{title}": bước 1 là {steps[0]}'),
            quiz(f'Hiểu: Trong quy trình "{title}", bước nào đứng ngay sau "{steps[0]}"?', [steps[1], steps[0], steps[2]],
                f'Theo quy trình "{title}": bước 2 là {steps[1]}\nBước 1 là {steps[0]}'),
            quiz(f'Hiểu: Trong quy trình "{title}", bước nào đứng ngay trước "{steps[3]}"?', [steps[2], steps[1], steps[4]],
                f'Theo quy trình "{title}": bước 3 là {steps[2]}\nBước 4 là {steps[3]}'),
            quiz(f'Vận dụng: Trong quy trình "{title}", tình huống "Sample-17" đã hoàn thành "{steps[1]}". Cần thực hiện bước nào tiếp theo?',
                [steps[2], steps[3], steps[0]], f'Theo quy trình "{title}": bước 3 là {steps[2]}\nBước 2 là {steps[1]}'),
            quiz(f'Vận dụng: Trong quy trình "{title}", tình huống "Sample-29" cần bắt đầu "{steps[4]}". Bước nào phải được hoàn thành ngay trước đó?',
                [steps[3], steps[2], steps[1]], f'Theo quy trình "{title}": bước 4 là {steps[3]}\nBước 5 là {steps[4]}'),
        ]
    elif topic == "rules":
        title = "Cold-chain intake"
        accept = "temperature is at most 8 C and seal is intact"
        equivalent = "temperature is no more than 8 C and seal is intact"
        reject = "temperature is above 8 C"
        questions = [
            quiz(f'Nhớ: Theo quy tắc "{title}", điều kiện nào dẫn đến "Accept"?',
                [accept, reject, "seal is broken"], f'Theo quy tắc "{title}": {accept} bảo đảm kết quả "Accept".'),
            quiz(f'Hiểu: Theo quy tắc "{title}", điều kiện nào bảo đảm kết quả "Accept"?',
                [equivalent, "seal is intact", reject], f'Theo quy tắc "{title}": {equivalent} bảo đảm kết quả "Accept".'),
            quiz(f'Hiểu: Theo quy tắc "{title}", điều kiện nào bảo đảm kết quả "Reject"?',
                [reject, "temperature is at most 8 C", "seal is intact"], f'Theo quy tắc "{title}": {reject} bảo đảm kết quả "Reject".'),
            quiz(f'Vận dụng: Theo quy tắc "{title}", tình huống "Batch-17" có dữ kiện: temperature = 7 C; seal = intact. Kết quả nào được áp dụng?',
                ["Accept", "Reject"], 'Dữ kiện: temperature = 7 C; seal = intact.\nÁp dụng: If temperature is at most 8 C and seal is intact, then choose "Accept".\nKết luận: Accept.'),
            quiz(f'Vận dụng: Theo quy tắc "{title}", tình huống "Batch-29" có dữ kiện: temperature = 9 C; seal = intact. Kết quả nào được áp dụng?',
                ["Reject", "Accept"], 'Dữ kiện: temperature = 9 C; seal = intact.\nÁp dụng: If temperature is above 8 C, then choose "Reject".\nKết luận: Reject.'),
        ]
    else:
        raise ValueError(topic)
    cards = [{"front": q["question"], "back": q["options"][0]["text"] + "\n" + q["explanation"],
              "source_ids": q["source_ids"]} for q in (questions[0], questions[1], questions[3])]
    return {"questions": questions}, {"cards": cards}
