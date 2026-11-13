"""Source-relative cloze support for facts/rules/procedures; stdlib only.

Natural questions stay review-required unless the old definition proof applies.
This is not a general semantic judge or a mathematical solver.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import product
import re

from backend.algorithms.f2_study_validation import ContentSupportDecision, validate_flashcard_support, validate_quiz_support


QUIZ_CLOZE_PREFIX = "Điền nguyên văn theo đoạn trích:"
CARD_CLOZE_PREFIX = "Hoàn thành nguyên văn theo đoạn trích:"
_BLANK = "[___]"
_MATH = re.compile(r"(?:\btính\s+(?:giá trị|số|tổng|xác suất|diện tích|thể tích)|giải phương trình|chứng minh|bao nhiêu cách|\bcalculate\b|\bsolve\b)", re.I)
_MISSING_SUBJECT = re.compile(r"\bthis function\b|\bthat function\b|hàm này|đoạn trên", re.I)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _decision(code: str, message: str, status="REVIEW_REQUIRED") -> ContentSupportDecision:
    return ContentSupportDecision(status, code, message)


def _context(prompt: str, prefix: str) -> str | None:
    text = _flat(prompt)
    if not text.startswith(prefix + " "):
        return None
    context = text[len(prefix):].strip()
    if context.count(_BLANK) != 1 or len(context.replace(_BLANK, "").split()) < 4:
        return None
    return context


def validate_quiz_content_support(question: str, options: Sequence[tuple[str, str]], correct_option_id: str,
    explanation: str, cited_sources: Sequence[tuple[str, str]], all_sources: Sequence[tuple[str, str]]) -> ContentSupportDecision:
    if _MISSING_SUBJECT.search(question):
        return _decision("MISSING_SUBJECT", "Câu hỏi chưa tự xác định hàm/chủ thể; cần bổ sung ngữ cảnh.")
    if learning_question_kind(question):
        return _validate_learning(question, options, correct_option_id, explanation, cited_sources, all_sources)
    old = validate_quiz_support(question, options, correct_option_id, explanation, cited_sources, all_sources)
    if old.status in ("SUPPORTED", "REJECTED"):
        return old
    if _MATH.search(question):
        return _decision("MATH_REASONING_DEFERRED", "Câu hỏi có dấu hiệu cần tính toán/chứng minh; phần tự giải bài tập đang ngoài phạm vi.")
    if not _flat(question).startswith(QUIZ_CLOZE_PREFIX):
        return old
    context = _context(question, QUIZ_CLOZE_PREFIX)
    if context is None:
        return _decision("UNSUPPORTED_CLOZE", "Cần đúng một chỗ trống và đủ ngữ cảnh nguyên văn để đối chiếu.")
    texts = [_flat(text) for _, text in options]
    if len(set(texts)) != len(texts):
        return _decision("AMBIGUOUS_OPTIONS", "Có lựa chọn trùng nhau sau chuẩn hóa khoảng trắng.")
    cited_quotes = {s: _cloze_quotes(quote) for s, quote in cited_sources}
    matches = {option_id: {s for s, quotes in cited_quotes.items() if context.replace(_BLANK, _flat(text)) in quotes}
               for option_id, text in options}
    supported_ids = {key for key, refs in matches.items() if refs}
    if len(supported_ids) > 1:
        return _decision("AMBIGUOUS_CLOZE", "Nhiều lựa chọn khôi phục được nguồn trích dẫn; cần review.")
    if supported_ids and correct_option_id not in supported_ids:
        return _decision("WRONG_ANSWER_KEY", "Đáp án đánh dấu không phải lựa chọn khôi phục nguyên văn nguồn.", "REJECTED")
    if not supported_ids:
        return _decision("UNSUPPORTED_CLOZE", "Không lựa chọn nào khôi phục toàn bộ đoạn nguồn được trích dẫn.")
    selected = next(_flat(text) for key, text in options if key == correct_option_id)
    filled = context.replace(_BLANK, selected)
    all_quotes = {candidate for _, quote in all_sources for candidate in _cloze_quotes(quote)}
    prefix, suffix = context.split(_BLANK)
    alternatives = {quote for quote in all_quotes if quote.startswith(prefix) and quote.endswith(suffix)}
    if alternatives - {filled}:
        return _decision("AMBIGUOUS_CLOZE", "Nguồn đã chọn có ngữ cảnh phù hợp với lựa chọn khác; cần review.")
    if set(cited_quotes) != matches[correct_option_id]:
        return _decision("IRRELEVANT_CITATION", "Có trích dẫn không hỗ trợ câu điền nguyên văn này.")
    if _flat(explanation) != f"Theo đoạn nguồn: {filled}":
        return _decision("UNSUPPORTED_EXPLANATION", "Giải thích cần khớp toàn bộ đoạn nguồn, không thêm nội dung.")
    return _decision("EXTRACTIVE_CLOZE_SUPPORT", "Đúng một lựa chọn khôi phục toàn bộ đoạn nguồn nguyên văn.", "SUPPORTED")


def validate_flashcard_content_support(front: str, back: str, cited_sources: Sequence[tuple[str, str]],
    all_sources: Sequence[tuple[str, str]]) -> ContentSupportDecision:
    if _MISSING_SUBJECT.search(front):
        return _decision("MISSING_SUBJECT", "Mặt trước chưa xác định chủ thể; cần review.")
    if learning_question_kind(front):
        answer, separator, explanation = back.partition("\n")
        if not separator:
            return _decision("MISSING_REASONING", "Thẻ theo mục tiêu cần đáp án và dòng giải thích có căn cứ.")
        return _validate_learning(front, (("answer", answer),), "answer", explanation, cited_sources, all_sources, card=True)
    old = validate_flashcard_support(front, back, cited_sources, all_sources)
    if old.status == "SUPPORTED":
        return old
    if _MATH.search(front):
        return _decision("MATH_REASONING_DEFERRED", "Phần tự giải bài tập/tính toán chưa được hỗ trợ; cần review.")
    if not _flat(front).startswith(CARD_CLOZE_PREFIX):
        return old
    context = _context(front, CARD_CLOZE_PREFIX)
    if context is None:
        return _decision("UNSUPPORTED_CLOZE", "Cần đúng một chỗ trống và đủ ngữ cảnh nguyên văn.")
    filled = context.replace(_BLANK, _flat(back))
    if not cited_sources or any(filled not in _cloze_quotes(quote) for _, quote in cited_sources):
        return _decision("UNSUPPORTED_ANSWER", "Mặt sau chưa khôi phục đầy đủ nguồn được trích dẫn.")
    prefix, suffix = context.split(_BLANK)
    alternatives = {q for _, quote in all_sources for q in _cloze_quotes(quote) if q.startswith(prefix) and q.endswith(suffix)}
    if alternatives - {filled}:
        return _decision("AMBIGUOUS_CLOZE", "Có nội dung khác trong cùng ngữ cảnh ở nguồn đã chọn; cần review.")
    return _decision("EXTRACTIVE_CLOZE_SUPPORT", "Mặt sau khôi phục toàn bộ đoạn nguồn nguyên văn.", "SUPPORTED")


def _cloze_quotes(quote: str) -> set[str]:
    """Whole span or complete standalone bullet, never an arbitrary substring."""
    result = {_flat(quote)}
    lines = quote.splitlines()
    bullets = [i for i, line in enumerate(lines) if re.match(r"^\s*[•*-]\s+", line)]
    if not bullets or any(line.strip() for line in lines[:bullets[0]]):
        return result
    for index, start in enumerate(bullets):
        end = bullets[index + 1] if index + 1 < len(bullets) else len(lines)
        text = _flat(re.sub(r"^\s*[•*-]\s+", "", lines[start]) + " " + " ".join(lines[start + 1:end]))
        if text.endswith((".", ";", "!")):
            result.add(text)
    return result


@dataclass(frozen=True)
class LearningObjective:
    objective_id: str
    kind: str
    title: str
    source_ids: tuple[str, ...]
    skills: tuple[str, ...] = ("nhớ", "hiểu", "vận dụng")


_HEADING = re.compile(r"^(Concepts?|Procedure|Rule|Policy|Function|Khái niệm|Quy trình|Quy tắc|Hàm)\s*:\s*(.+)$", re.I)
_STEP_LINE = re.compile(r"^(\d+)[.)]\s+(.+)$")
_RULE = re.compile(r'^If (.+), then choose "([^"\n]+)"\.$', re.I)
_PREDICATE = re.compile(r"^([\w -]+?)\s+(is at most|is no more than|is at least|is no less than|is above|is below|is not|is|<=|>=|!=|=|<|>)\s+(.+)$", re.I)
_NUMBER = re.compile(r"^(-?\d+(?:\.\d+)?)\s*([A-Za-z%]+)?$")


def learning_question_kind(question: str) -> str | None:
    match = re.match(r"^(Nhớ|Hiểu|Vận dụng):\s+", question.strip(), re.I)
    return match[1].casefold() if match else None


def _predicate(text):
    match = _PREDICATE.fullmatch(text.strip())
    if not match:
        return None
    field, operator, value = match.groups()
    operators = {"is at most": "<=", "is no more than": "<=", "is at least": ">=", "is no less than": ">=",
                 "is above": ">", "is below": "<", "is not": "!=", "is": "="}
    operator = operators.get(operator.casefold(), operator)
    numeric = _NUMBER.fullmatch(value)
    if numeric:
        try:
            return (field.strip(), operator, Decimal(numeric[1]), numeric[2] or "")
        except InvalidOperation:
            return None
    if operator not in ("=", "!=") or any(c in value for c in '\n;"'):
        return None
    return (field.strip(), operator, value.strip(), None)


def _conditions(text):
    parts = re.split(r"\s+and\s+", text.strip(), flags=re.I)
    parsed = tuple(_predicate(part) for part in parts)
    return parsed if 0 < len(parsed) <= 8 and all(parsed) else None


def _catalog(sources):
    definitions, procedures, rules, bad = {}, {}, {}, set()
    for source_id, quote in sources:
        lines = [line.strip() for line in quote.splitlines() if line.strip()]
        term, body = None, []

        def flush_definition():
            if term is not None:
                definitions.setdefault(term, set()).add((_flat(" ".join(body)), source_id))

        for line in lines:
            match = re.fullmatch(r'([^:\n]{1,80}):\s+(.+)', line)
            if _HEADING.match(line):
                flush_definition()
                term, body = None, []
            elif match and not line.endswith("?"):
                flush_definition()
                term, body = match[1], [match[2]]
            elif term is not None:
                body.append(line)  # preserve wrapped qualifiers/conditions
        flush_definition()
        header = _HEADING.fullmatch(lines[0]) if lines else None
        if not header or len(lines) < 2:
            continue
        role, title = header[1].casefold(), header[2]
        if role in ("procedure", "quy trình"):
            steps = [_STEP_LINE.fullmatch(line) for line in lines[1:]]
            if len(steps) >= 2 and all(steps) and [int(s[1]) for s in steps] == list(range(1, len(steps) + 1)):
                procedures.setdefault(title, []).append((tuple(s[2] for s in steps), source_id))
            else:
                bad.add(title)
        elif role in ("rule", "policy", "quy tắc"):
            for line in lines[1:]:
                match = _RULE.fullmatch(line)
                predicates = _conditions(match[1]) if match else None
                if not predicates:
                    bad.add(title)
                else:
                    rules.setdefault(title, []).append((predicates, match[2], line, source_id))
    return definitions, procedures, rules, bad


def build_learning_objectives(sources: Sequence[tuple[str, str]]) -> tuple[LearningObjective, ...]:
    """Shared evidence-derived goals for both formats; titles/IDs are data."""
    definitions, procedures, rules, bad = _catalog(sources)
    goals = []
    for term, records in definitions.items():
        if len({body for body, _ in records}) == 1:
            goals.append(("concept", term, tuple(sorted({s for _, s in records}))))
    for kind, catalog in (("procedure", procedures), ("rule", rules)):
        for title, records in catalog.items():
            if title not in bad:
                goals.append((kind, title, tuple(sorted({r[-1] for r in records}))))
    if not goals:
        # Other PDF prose still gets shared evidence goals. This does not
        # certify arbitrary paraphrases: unsupported reasoning stays review.
        goals = [("source_understanding", _flat(quote)[:120], (source_id,))
                 for source_id, quote in sources if len(quote.split()) >= 3 and not _HEADING.fullmatch(quote.strip())]
    return tuple(LearningObjective(f"O{i}", kind, title, refs) for i, (kind, title, refs) in enumerate(goals, 1))


def _test_predicate(predicate, values):
    field, operator, expected, unit = predicate
    actual, actual_unit = values[field]
    if actual_unit != unit or isinstance(expected, Decimal) != isinstance(actual, Decimal):
        return False
    if operator == "=": return actual == expected
    if operator == "!=": return actual != expected
    if operator == "<": return actual < expected
    if operator == "<=": return actual <= expected
    if operator == ">": return actual > expected
    return actual >= expected


def _outcomes(rules, values):
    return {action for predicates, action, _, _ in rules if all(_test_predicate(p, values) for p in predicates)}


def _worlds(rules, extra=()):
    predicates = [p for conditions, _, _, _ in rules for p in conditions]
    fields = {p[0] for p in predicates}
    if not fields or len(fields) > 4 or len(rules) > 16 or any(p[0] not in fields for p in extra):
        return None
    domains = []
    for field in sorted(fields):
        values = [p for p in (*predicates, *extra) if p[0] == field]
        units = {p[3] for p in values}
        if len(units) != 1:
            return None
        unit = next(iter(units))
        if unit is None:
            candidates = {p[2] for p in values} | {object()}
        else:
            boundaries = sorted({p[2] for p in values})
            candidates = set(boundaries) | {boundaries[0] - 1, boundaries[-1] + 1}
            candidates.update((a + b) / 2 for a, b in zip(boundaries, boundaries[1:]))
        domains.append([(v, unit) for v in candidates])
    size = 1
    for domain in domains:
        size *= len(domain)
    if size > 2048:
        return None
    return [dict(zip(sorted(fields), combination)) for combination in product(*domains)]


def _learning_solutions(question, choices, sources, *, domain_sources=None):
    """Finite, source-relative proofs. Unknown language abstains, never guesses."""
    definitions, procedures, rules, bad = _catalog(sources)
    solutions, relevant = {}, set()
    # Definition lookup and comparison bind subjects in the question itself.
    match = re.fullmatch(r'Nhớ: Theo tài liệu, "([^"\n]+)" là gì\?', question)
    application = re.fullmatch(r'Vận dụng: Tình huống "([^"\n]+)" có đặc điểm "([^"\n]+)"\. Khái niệm nào có định nghĩa khớp đặc điểm này trong tài liệu\?', question)
    comparison = re.fullmatch(r'Hiểu: Theo hai định nghĩa trong tài liệu, khi phân biệt "([^"\n]+)" với "([^"\n]+)", cặp mô tả nào khớp\?', question)
    if match or application or comparison:
        single = {term: next(iter({body for body, _ in records})) for term, records in definitions.items()
                  if len({body for body, _ in records}) == 1}
        domain = definitions if domain_sources is None else _catalog(domain_sources)[0]
        known = {term: next(iter({body for body, _ in records})) for term, records in domain.items()
                 if len({body for body, _ in records}) == 1}
        if match and match[1] in single:
            term = match[1]; answer = single[term]
            if any(c not in set(known.values()) for c in choices): return None
            solutions[answer] = f"Theo nguồn: {term}: {answer}"
            relevant = {s for _, s in definitions[term]}
        elif application:
            label, body = application.groups()
            if any(c not in known for c in choices): return None
            for term, definition in single.items():
                if definition == body:
                    solutions[term] = f'Tình huống "{label}": {body}\nTheo nguồn: {term}: {body}'
                    relevant.update(s for _, s in definitions[term])
        elif comparison and comparison[1] in single and comparison[2] in single and comparison[1] != comparison[2]:
            a, b = comparison.groups()
            for choice in choices:
                pair = re.fullmatch(r'([^:]+): (.+); ([^:]+): (.+)', choice)
                if not pair or pair[1] != a or pair[3] != b or pair[2] not in known.values() or pair[4] not in known.values(): return None
            answer = f"{a}: {single[a]}; {b}: {single[b]}"
            solutions[answer] = f"Theo nguồn: {a}: {single[a]}\n{b}: {single[b]}"
            relevant = {s for term in (a, b) for _, s in definitions[term]}
        return solutions, relevant
    # Ordered procedures require a named heading and complete contiguous order.
    patterns = [
        (r'Nhớ: Trong quy trình "([^"\n]+)", bước đầu tiên là gì\?', "first"),
        (r'Hiểu: Trong quy trình "([^"\n]+)", bước nào đứng ngay sau "([^"\n]+)"\?', "next"),
        (r'Hiểu: Trong quy trình "([^"\n]+)", bước nào đứng ngay trước "([^"\n]+)"\?', "previous"),
        (r'Vận dụng: Trong quy trình "([^"\n]+)", tình huống "[^"\n]+" đã hoàn thành "([^"\n]+)"\. Cần thực hiện bước nào tiếp theo\?', "next"),
        (r'Vận dụng: Trong quy trình "([^"\n]+)", tình huống "[^"\n]+" cần bắt đầu "([^"\n]+)"\. Bước nào phải được hoàn thành ngay trước đó\?', "previous"),
    ]
    for pattern, direction in patterns:
        match = re.fullmatch(pattern, question)
        if not match: continue
        title = match[1]; records = procedures.get(title, [])
        orders = {steps for steps, _ in records}
        if title in bad or len(orders) != 1: return None
        steps = next(iter(orders))
        if len(set(steps)) != len(steps) or any(c not in steps for c in choices): return None
        origin = 0 if direction == "first" else (steps.index(match[2]) if match[2] in steps else -1)
        index = 0 if direction == "first" else origin + (1 if direction == "next" else -1)
        if origin < 0 or not 0 <= index < len(steps): return None
        answer = steps[index]
        explanation = f'Theo quy trình "{title}": bước {index + 1} là {answer}'
        if direction != "first": explanation += f'\nBước {origin + 1} là {steps[origin]}'
        return {answer: explanation}, {s for _, s in records}
    # Conditional implication and fresh scenario data, without arithmetic.
    condition_query = re.fullmatch(r'(?:Nhớ: Theo quy tắc "([^"\n]+)", điều kiện nào dẫn đến "([^"\n]+)"|Hiểu: Theo quy tắc "([^"\n]+)", điều kiện nào bảo đảm kết quả "([^"\n]+)")\?', question)
    scenario = re.fullmatch(r'Vận dụng: Theo quy tắc "([^"\n]+)", tình huống "([^"\n]+)" có dữ kiện: (.+)\. Kết quả nào được áp dụng\?', question)
    if not condition_query and not scenario: return None
    title = (condition_query[1] or condition_query[3]) if condition_query else scenario[1]
    group = rules.get(title, [])
    if not group or title in bad or _worlds(group) is None: return None
    relevant = {r[-1] for r in group}
    if condition_query:
        target = condition_query[2] or condition_query[4]
        if target not in {r[1] for r in group}: return None
        for choice in choices:
            predicates = _conditions(choice)
            worlds = _worlds(group, predicates) if predicates else None
            if worlds is None: return None
            matching = [w for w in worlds if all(_test_predicate(p, w) for p in predicates)]
            if matching and all(_outcomes(group, w) == {target} for w in matching):
                solutions[choice] = f'Theo quy tắc "{title}": {choice} bảo đảm kết quả "{target}".'
        return solutions, relevant
    facts = {}
    for part in scenario[3].split("; "):
        predicate = _predicate(part)
        if not predicate or predicate[1] != "=" or predicate[0] in facts: return None
        facts[predicate[0]] = (predicate[2], predicate[3])
    fields = {p[0] for predicates, _, _, _ in group for p in predicates}
    if set(facts) != fields or any(c not in {r[1] for r in group} for c in choices): return None
    # Unit/type mismatch is missing information, never an implicit conversion.
    if any(facts[p[0]][1] != p[3] for predicates, _, _, _ in group for p in predicates): return None
    outcomes = _outcomes(group, facts)
    if len(outcomes) != 1: return {}, relevant
    action = next(iter(outcomes))
    active = sorted({line for predicates, outcome, line, _ in group
                     if outcome == action and all(_test_predicate(p, facts) for p in predicates)})
    # A short, auditable derivation is shown only after submit/flip.
    solutions[action] = tuple(f'Dữ kiện: {scenario[3]}.\nÁp dụng: {line}\nKết luận: {action}.' for line in active)
    return solutions, relevant


def _validate_learning(question, options, correct_option_id, explanation, cited_sources, all_sources, *, card=False):
    if _MATH.search(question):
        return _decision("MATH_REASONING_DEFERRED", "Chưa hỗ trợ tự giải bài Toán/Lý.")
    choices = tuple(_flat(text) for _, text in options)
    if len(set(c.casefold() for c in choices)) != len(choices):
        return _decision("AMBIGUOUS_OPTIONS", "Các lựa chọn trùng nhau sau chuẩn hóa.")
    complete = _learning_solutions(question.strip(), choices, all_sources)
    cited = _learning_solutions(question.strip(), choices, cited_sources, domain_sources=all_sources)
    if complete is None or cited is None:
        return _decision("UNSUPPORTED_LEARNING_REASONING", "Chưa đủ dữ kiện/ngữ cảnh hoặc dạng diễn giải chưa có phép kiểm phù hợp.")
    solutions, _ = complete
    cited_solutions, relevant = cited
    valid = [option_id for option_id, text in options if _flat(text) in solutions]
    if card and len(solutions) != 1:
        return _decision("AMBIGUOUS_ANSWER", "Nguồn cho phép nhiều đáp án cho thẻ; cần review.")
    if len(valid) != 1 or correct_option_id != valid[0]:
        return _decision("AMBIGUOUS_OR_UNSUPPORTED_ANSWER", "Không chứng minh được đúng một đáp án theo toàn bộ quy tắc/định nghĩa nguồn.")
    answer = next(_flat(text) for option_id, text in options if option_id == correct_option_id)
    if answer not in cited_solutions or any(s not in relevant for s, _ in cited_sources):
        return _decision("INSUFFICIENT_CITED_SUPPORT", "Locator đúng nhưng trích dẫn chưa hỗ trợ phép suy ra này.")
    def proofs(expected):
        return {_flat(value) for value in expected} if isinstance(expected, tuple) else {_flat(expected)}
    if _flat(explanation) not in proofs(solutions[answer]) & proofs(cited_solutions[answer]):
        return _decision("UNSUPPORTED_EXPLANATION", "Lời giải thiếu/sai điều kiện hoặc không khớp phép suy ra từ nguồn.")
    return _decision("SOURCE_LEARNING_SUPPORT", "Đã kiểm độc lập chủ thể, điều kiện/thứ tự, đáp án duy nhất và lời giải theo nguồn.", "SUPPORTED")
