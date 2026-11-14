"""Local F2 source inspection, generation, author review and checked practice.

No seeded workspace, synthetic output or validation override. Each browser
session owns its local source repository, drafts and practice identity.
"""
import os
from uuid import uuid4

from pydantic import ValidationError
import streamlit as st

from backend.core.f2_practice_schemas import FlashcardBackView, QuizSubmission
from backend.core.f2_study_schemas import StudySourceSelection
from backend.core.config import settings
from backend.providers.f2_flashcard_provider import OllamaFlashcardProvider
from backend.providers.f2_gemini_provider import DEFAULT_GEMINI_STUDY_MODEL, GeminiFlashcardProvider, GeminiQuizProvider
from backend.providers.f2_nvidia_nim_provider import DEFAULT_NVIDIA_NIM_MODEL, NvidiaNimFlashcardProvider, NvidiaNimQuizProvider
from backend.providers.f2_quiz_provider import OllamaQuizProvider
from backend.providers.f2_source_content_provider import SourceContentProvider
from backend.providers.f2_study_provider import StudyProviderError
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_flashcard_service import F2FlashcardService, FlashcardGenerationError
from backend.services.f2_practice_service import F2PracticeService, PracticeAccessContext, PracticeError
from backend.services.f2_quiz_service import F2QuizService, QuizGenerationError
from backend.services.f2_source_service import F2SourceService, SourceAccessContext, SourcePreparationError
from backend.services.f2_study_draft_service import F2StudyDraftService, StudyDraftError


def _runtime():
    if "f2_manual_runtime" not in st.session_state:
        repository = WorkspaceRepository()
        st.session_state["f2_manual_runtime"] = {
            "repository": repository,
            "ingestion": DocumentService(repository),
            "practice": F2PracticeService(repository),
            "review": F2StudyDraftService(repository),
            "version": 2,
            "workspace_id": str(uuid4()),
            "learner_id": str(uuid4()),
        }
    runtime = st.session_state["f2_manual_runtime"]
    if runtime.get("version") != 2:
        # Hot reload must use the new verifier without losing ingested sources
        # or password widgets. Keep the old practice object for this session.
        runtime["previous_practice"] = runtime["practice"]
        runtime["ingestion"] = DocumentService(runtime["repository"])
        runtime["practice"] = F2PracticeService(runtime["repository"])
        runtime["review"] = F2StudyDraftService(runtime["repository"])
        runtime["version"] = 2
        if st.session_state.get("f2_manual_active"):
            st.session_state["f2_manual_messages"] = [("info",
                "Bộ kiểm chứng đã cập nhật. Tài liệu được giữ; hãy tạo phiên luyện tập mới.")]
        st.session_state["f2_manual_active"] = None
    if not callable(getattr(runtime["review"], "preview_quiz", None)):
        # Upgrade a hot-reloaded service without resetting source/key widgets.
        runtime["review"] = F2StudyDraftService(runtime["repository"])
    return runtime


def _context(runtime):
    return PracticeAccessContext(runtime["learner_id"], SourceAccessContext(
        runtime["workspace_id"], frozenset(runtime["repository"].documents),
    ))


def _start_practice(runtime, resource, study_format, context):
    initial = (runtime["practice"].start_quiz(resource, context=context) if study_format == "quiz"
               else runtime["practice"].start_flashcards(resource, context=context))
    st.session_state["f2_manual_active"] = {"format": study_format, "session_id": initial.session_id}


def _generate(runtime, selected, study_format, count, *, engine="Offline", model="", api_key="",
              content_mode="source_content"):
    st.session_state["f2_manual_active"] = None
    st.session_state["f2_manual_draft"] = None
    st.session_state["f2_manual_draft_quiz"] = None
    st.session_state["f2_manual_preview"] = None
    st.session_state["f2_manual_diagnostic"] = None
    messages = []
    st.session_state["f2_manual_messages"] = messages
    try:
        context = _context(runtime)
        prepared = F2SourceService(runtime["repository"]).prepare_sources(
            StudySourceSelection(selected_doc_ids=selected, study_format=study_format, requested_count=count),
            context=context.sources,
        )
        provider = None
        if engine == "Gemini":
            provider_type = GeminiQuizProvider if study_format == "quiz" else GeminiFlashcardProvider
            provider = provider_type(api_key, model=model)
        elif engine == "NVIDIA NIM":
            provider_type = NvidiaNimQuizProvider if study_format == "quiz" else NvidiaNimFlashcardProvider
            provider = provider_type(api_key, model=model)
        elif engine == "Ollama":
            provider_type = OllamaQuizProvider if study_format == "quiz" else OllamaFlashcardProvider
            provider = provider_type(base_url=settings.ollama_base_url, model=model)
        if provider is not None and content_mode == "source_content":
            provider = SourceContentProvider(provider, study_format)
        if study_format == "quiz":
            generated = F2QuizService(provider).generate_quiz(prepared)
            resource = generated.quiz
        else:
            generated = F2FlashcardService(provider).generate_flashcards(prepared)
            resource = generated.deck
        # A selected adapter may not be called when evidence is empty. Model
        # aliases can resolve to a different version at Google; label honestly.
        provider_label = generated.provider_name + (f" · model yêu cầu: {model}" if provider is not None else "")
        messages.append(("info", f"Bộ sinh được chọn: {provider_label}"))
        codes = tuple(issue.code for issue in generated.issues)
        empty_output = "INSUFFICIENT_GENERATABLE_CONTENT" in codes
        if generated.status != "COMPLETE":
            message = "Bộ sinh trả về danh sách rỗng; chưa tạo được học liệu. Hãy xem nội dung trích xuất/cách sinh." if empty_output else generated.message
            messages.append(("error" if generated.status == "ERROR" else "warning", message))
        for issue in (*generated.source_issues, *generated.issues):
            if empty_output and issue.code == "INSUFFICIENT_GENERATABLE_CONTENT":
                continue
            if not any(message == issue.message for _, message in messages):
                messages.append(("warning", issue.message))
        if resource is None:
            if not prepared.passages:
                diagnostic = "NGUỒN: không có đoạn đủ điều kiện; chưa gọi bộ sinh. Xem nội dung trích xuất."
            elif any(code.startswith("PROVIDER_") for code in codes):
                diagnostic = "API: yêu cầu thất bại; xem mã lỗi phía trên. Chưa có học liệu để kiểm chứng."
            elif empty_output:
                diagnostic = "BỘ SINH: trả về danh sách rỗng. Điều này chưa chứng minh PDF thiếu nội dung; xem phần trích xuất và cách sinh."
            else:
                diagnostic = "ĐẦU RA: chưa có mục hợp lệ sau kiểm tra cấu trúc/nguồn. Xem lý do phía trên."
            st.session_state["f2_manual_diagnostic"] = diagnostic
            return
        review = runtime["review"].review(resource, context=context.sources)
        if review.validation.release_ready:
            # Q06 independently checks again; a UI receipt is never authority.
            _start_practice(runtime, resource, study_format, context)
        else:
            st.session_state["f2_manual_draft"] = {"resource": resource, "format": study_format}
            messages.append(("warning", review.validation.message))
    except (SourcePreparationError, QuizGenerationError, FlashcardGenerationError, PracticeError,
            StudyDraftError, StudyProviderError, ValidationError, ValueError) as error:
        messages.append(("error", str(error)))


def _source_preview(runtime, selected, study_format, count):
    if st.session_state.get("f2_manual_generate"):
        st.session_state["f2_manual_preview"] = None
    if st.button("Xem nội dung đã trích xuất", disabled=not selected, key="f2_manual_inspect"):
        st.session_state["f2_manual_active"] = None
        st.session_state["f2_manual_draft_quiz"] = None
        st.session_state["f2_manual_preview"] = tuple(selected)
    if st.session_state.get("f2_manual_preview") != tuple(selected) or not selected:
        return
    try:
        inspection = F2SourceService(runtime["repository"]).inspect_sources(
            StudySourceSelection(selected_doc_ids=selected, study_format=study_format, requested_count=count),
            context=_context(runtime).sources,
        )
        with st.expander("Nội dung trích xuất thực tế", expanded=True):
            st.caption("Đây là văn bản bộ đọc lấy được, chưa phải chứng nhận nội dung hay công thức chính xác. Các chunk có thể chồng dòng.")
            for document in inspection.documents:
                st.write(f"{document.doc_name} · {document.doc_version}")
                st.caption(f"{document.text_character_count} ký tự · {len(document.page_numbers)} trang có chữ · "
                    f"{document.usable_passage_count} đoạn đủ điều kiện")
                st.caption(" · ".join(f"{kind}: {value}" for kind, value in document.category_counts) or "Không có loại đoạn đủ điều kiện")
                for warning in document.warnings:
                    st.warning(warning)
                if document.chunks:
                    index = st.selectbox("Đoạn văn bản đã đọc", range(len(document.chunks)),
                        format_func=lambda i, chunks=document.chunks:
                            f"Trang {chunks[i].page_number} · Dòng {chunks[i].start_line}–{chunks[i].end_line}",
                        key=f"f2_preview_chunk_{document.doc_id}_{document.doc_version}")
                    chunk = document.chunks[index]
                    if chunk.excluded_as_suspicious:
                        st.warning("Chunk này bị loại khỏi nguồn sinh vì có dấu hiệu chỉ dẫn đáng ngờ.")
                    st.code(chunk.text, language=None)
    except (SourcePreparationError, ValueError) as error:
        st.error(str(error))


def render_controls():
    runtime = _runtime()
    st.subheader("1. Tài liệu")
    files = st.file_uploader("Tải PDF có lớp chữ, TXT hoặc MD", type=["pdf", "txt", "md"],
        accept_multiple_files=True, key="f2_manual_upload")
    if st.button("Nạp tài liệu", disabled=not files, key="f2_manual_ingest"):
        selected = list(st.session_state.get("f2_manual_selected", []))
        for uploaded in files:
            try:
                result = runtime["ingestion"].ingest_file(uploaded.name, uploaded.getvalue())
                doc_id = result["document"].doc_id
                if doc_id not in selected:
                    selected.append(doc_id)
                st.success(result["message"])
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error(f"Không đọc được {uploaded.name}. Hãy kiểm tra tệp và thử PDF có lớp chữ, TXT hoặc MD.")
        st.session_state["f2_manual_selected"] = selected
    documents = runtime["repository"].documents
    selected = st.multiselect("Chọn nguồn để tạo học liệu", options=list(documents),
        format_func=lambda doc_id: f"{documents[doc_id].doc_name} · {documents[doc_id].version_id}",
        key="f2_manual_selected")
    st.caption(f"Đã nạp {len(documents)} tài liệu · Đang chọn {len(selected)} nguồn")
    st.subheader("2. Tạo học liệu")
    label = st.radio("Loại học liệu", ["Quiz", "Flashcards"], horizontal=True, key="f2_manual_format")
    count = st.number_input("Số câu / thẻ mong muốn", min_value=1, value=10, step=1, key="f2_manual_count")
    _source_preview(runtime, selected, "quiz" if label == "Quiz" else "flashcards", count)
    engine = st.selectbox("Bộ sinh", ["Offline", "Gemini", "NVIDIA NIM", "Ollama"], key="f2_manual_engine")
    content_mode = "definitions"
    if engine != "Offline":
        mode = st.selectbox("Cách sinh", ["Nội dung tài liệu", "Định nghĩa (như bản cũ)"], key="f2_manual_content_mode")
        content_mode = "source_content" if mode == "Nội dung tài liệu" else "definitions"
        st.caption("Quiz dùng JSON để dựng câu hỏi và lựa chọn tương tác. Câu hỏi tự nhiên chưa kiểm chứng có thể làm thử ở chế độ nháp. Chưa tự giải bài Toán/Lý.")
    model, api_key = "", ""
    if engine == "Gemini":
        model = st.text_input("Model Gemini", value=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_STUDY_MODEL), key="f2_manual_gemini_model")
        entered_key = st.text_input("Gemini API key", type="password", key="f2_manual_gemini_key",
            help="Nhập tại đây hoặc cấu hình GEMINI_API_KEY trên server. Không cần gửi khóa trong chat.")
        api_key = entered_key.strip() or settings.gemini_api_key.strip()
        st.caption("Khi bấm tạo, các đoạn nguồn đã chọn được gửi tới Google. Khóa nhập tại đây chỉ giữ trong phiên, không ghi file.")
        if not api_key or api_key == "your_gemini_api_key_here":
            st.warning("Chưa có Gemini API key. Hãy nhập khóa của bạn để thử Gemini.")
        else:
            st.caption("Đã có khóa để gửi yêu cầu; chưa xác nhận khóa/quota hoạt động.")
    elif engine == "NVIDIA NIM":
        model = st.text_input("Model NVIDIA NIM", value=os.getenv("NVIDIA_NIM_MODEL", DEFAULT_NVIDIA_NIM_MODEL), key="f2_manual_nim_model")
        entered_key = st.text_input("NVIDIA API key", type="password", key="f2_manual_nim_key",
            help="Dùng key NVIDIA Build hoặc biến server NVIDIA_API_KEY. Không nhập Gemini key vào đây.")
        api_key = entered_key.strip() or os.getenv("NVIDIA_API_KEY", "").strip()
        st.caption("Khi bấm tạo, các đoạn nguồn đã chọn được gửi tới NVIDIA. Key nhập tại đây chỉ giữ trong phiên, không ghi file.")
        if not api_key or api_key == "your_nvidia_api_key_here":
            st.warning("Chưa có NVIDIA API key. Hãy nhập key của bạn để thử NVIDIA NIM.")
        else:
            st.caption("Đã có khóa để gửi yêu cầu; chưa xác nhận khóa/quota hoạt động.")
    elif engine == "Ollama":
        model = st.text_input("Model Ollama", value=settings.ollama_model, key="f2_manual_ollama_model")
        st.caption("Dùng Ollama đã chạy trên máy theo cấu hình server. Q05 vẫn chặn nội dung chưa được hỗ trợ.")
    else:
        st.caption("Bộ sinh định nghĩa offline hiện có; không gọi API.")
    missing_key = engine in ("Gemini", "NVIDIA NIM") and (
        not api_key or api_key in ("your_gemini_api_key_here", "your_nvidia_api_key_here"))
    if st.button("Tạo bộ luyện tập", type="primary", disabled=not selected or missing_key, key="f2_manual_generate"):
        with st.spinner("Đang chuẩn bị nguồn, tạo và kiểm chứng học liệu…"):
            _generate(runtime, selected, "quiz" if label == "Quiz" else "flashcards", count,
                engine=engine, model=model, api_key=api_key, content_mode=content_mode)


def _sources(refs):
    with st.expander("Xem trích dẫn"):
        for ref in refs:
            st.caption(f"{ref.doc_id} · {ref.doc_version} · Trang {ref.page_number} · Dòng {ref.start_line}–{ref.end_line}")
            st.text(ref.evidence_quote)


def _quiz(runtime, session_id, context):
    service = runtime["practice"]
    view = service.get_quiz(session_id, context=context)
    st.subheader("3. Làm Quiz")
    st.caption(f"{view.actual_count} câu thực tế / {view.requested_count} câu yêu cầu")
    if view.status == "IN_PROGRESS":
        with st.form(f"f2_quiz_form_{session_id}"):
            choices = []
            for i, question in enumerate(view.questions, 1):
                st.markdown(f"**Câu {i}**")
                st.text(question.question)
                options = {option.option_id: option.text for option in question.options}
                selected = st.radio("Chọn một đáp án", list(options), index=None,
                    format_func=lambda option_id, texts=options: f"{option_id}. {texts[option_id]}",
                    key=f"f2_answer_{session_id}_{question.question_id}")
                if selected is not None:
                    choices.append({"question_id": question.question_id, "option_id": selected})
            st.caption("Câu chưa chọn được tính là chưa trả lời. Nộp bài để xem kết quả và đáp án.")
            submitted = st.form_submit_button("Nộp bài", type="primary")
        if submitted:
            service.submit_quiz(session_id, QuizSubmission(answers=choices), context=context)
            st.rerun()
    else:
        result = service.get_quiz_result(session_id, context=context)
        st.success(f"Kết quả: {result.correct_count}/{result.total_count} câu đúng · {result.score_percent:g}%")
        st.caption(f"Đã trả lời {result.answered_count}/{result.total_count} câu")
        for i, (question, feedback) in enumerate(zip(view.questions, result.items, strict=True), 1):
            with st.container(border=True):
                st.markdown(f"**Câu {i} · {'Đúng' if feedback.is_correct else 'Chưa đúng'}**")
                st.text(question.question)
                options = {option.option_id: option.text for option in question.options}
                st.write("Bạn chọn: " + (options[feedback.selected_option_id] if feedback.selected_option_id else "Chưa trả lời"))
                st.write("Đáp án đúng: " + options[feedback.correct_option_id])
                st.text(feedback.explanation)
                _sources(feedback.source_refs)


def _flashcards(runtime, session_id, context):
    service = runtime["practice"]
    view = service.get_flashcard(session_id, context=context)
    st.subheader("3. Ôn Flashcards")
    st.caption(f"Thẻ {view.current_index + 1}/{view.actual_count} · Đã yêu cầu {view.requested_count} thẻ")
    with st.container(border=True):
        st.text(view.front)
        if isinstance(view, FlashcardBackView):
            st.divider()
            st.markdown("**Đáp án**")
            st.text(view.back)
            _sources(view.source_refs)
    previous, flip, following = st.columns(3)
    if previous.button("← Thẻ trước", disabled=view.current_index == 0):
        service.move_flashcard(session_id, "previous", card_id=view.card_id, context=context)
        st.rerun()
    if flip.button("Ẩn đáp án" if isinstance(view, FlashcardBackView) else "Lật thẻ", type="primary"):
        service.flip_flashcard(session_id, card_id=view.card_id, context=context)
        st.rerun()
    if following.button("Thẻ tiếp →", disabled=view.current_index == view.actual_count - 1):
        service.move_flashcard(session_id, "next", card_id=view.card_id, context=context)
        st.rerun()


def render_practice():
    runtime = _runtime()
    for level, message in st.session_state.get("f2_manual_messages", []):
        {"error": st.error, "warning": st.warning, "info": st.info}[level](message)
    if diagnostic := st.session_state.get("f2_manual_diagnostic"):
        st.caption(diagnostic)
    active = st.session_state.get("f2_manual_active")
    if not active:
        if draft := st.session_state.get("f2_manual_draft"):
            _render_draft(runtime, draft)
            return
        st.subheader("3. Luyện tập")
        st.write("Tải và nạp tài liệu ở bên trái, chọn nguồn rồi bấm Tạo bộ luyện tập.")
        return
    try:
        context = _context(runtime)
        if active["format"] == "quiz":
            _quiz(runtime, active["session_id"], context)
        else:
            _flashcards(runtime, active["session_id"], context)
    except PracticeError as error:
        st.error(str(error))
    if st.session_state.get("f2_manual_draft"):
        if st.button("Xem lại bản nháp (rời màn luyện tập)", key="f2_manual_return_draft"):
            st.session_state["f2_manual_active"] = None
            st.rerun()


def _render_draft(runtime, draft):
    preview = st.session_state.get("f2_manual_draft_quiz")
    if draft["format"] == "quiz" and preview and preview["quiz_set_id"] == draft["resource"].quiz_set_id:
        _draft_quiz(runtime, draft["resource"], preview)
        return
    st.subheader("3. Bản nháp cần review — chưa phải bài luyện tập")
    st.warning("Chế độ soạn/review có hiển thị đáp án do AI đề xuất. Đây chưa phải đáp án đã được xác nhận.")
    try:
        context = _context(runtime)
        review = runtime["review"].review(draft["resource"], context=context.sources)
        resource, validation = review.resource, review.validation
        items = resource.questions if draft["format"] == "quiz" else resource.cards
        st.caption(f"{len(items)} mục thực tế / {resource.selection.requested_count} yêu cầu · "
            f"{len(review.verified_item_ids)} mục đủ điều kiện luyện tập · Trạng thái: {validation.status}")
        for issue in validation.issues:
            st.warning(f"{issue.code}: {issue.message}")
        if draft["format"] == "quiz" and validation.status != "REJECTED" and not validation.issues:
            st.caption("Bạn có thể chọn đáp án và nộp thử bản nháp. Kết quả chỉ đối chiếu với đáp án AI đề xuất, chưa được xác nhận đúng về nội dung.")
            if st.button("Làm thử Quiz nháp (chưa kiểm chứng)", key="f2_manual_try_draft"):
                runtime["review"].preview_quiz(resource, context=context.sources)
                st.session_state["f2_manual_draft_quiz"] = {
                    "quiz_set_id": resource.quiz_set_id, "attempt_id": str(uuid4()), "submission": None,
                }
                st.session_state["f2_manual_preview"] = None
                st.rerun()
        results = {item.item_id: item for item in validation.items}
        for index, item in enumerate(items, 1):
            item_id = item.question_id if draft["format"] == "quiz" else item.card_id
            result = results.get(item_id)
            status = f"{result.source_status} / {result.support_status}" if result else "NOT_CHECKED"
            with st.expander(f"Mục {index} · {status}"):
                if result is None or result.source_status != "MATCHED":
                    st.warning("Không hiển thị nội dung lưu trong nháp vì nguồn hiện tại chưa đối chiếu được hoặc không còn được phép.")
                    for issue in result.issues if result else ():
                        st.warning(f"{issue.code}: {issue.message}")
                    continue
                if draft["format"] == "quiz":
                    st.text(item.question)
                    for option in item.options:
                        st.text(f"{option.option_id}. {option.text}")
                    st.text(f"Đáp án AI đề xuất: {item.correct_option_id}")
                    st.text(item.explanation)
                else:
                    st.text(item.front)
                    st.text(f"Mặt sau AI đề xuất: {item.back}")
                for issue in result.issues if result else ():
                    st.warning(f"{issue.code}: {issue.message}")
                # Literal output, not executable Markdown/HTML from a document.
                for ref in item.source_refs:
                    st.caption(f"{ref.doc_id} · {ref.doc_version} · Trang {ref.page_number} · Dòng {ref.start_line}–{ref.end_line}")
                    st.text(ref.evidence_quote)
        ready = len(review.verified_item_ids)
        if ready:
            st.caption(f"Chỉ {ready}/{len(items)} mục đã qua kiểm chứng sẽ được dùng; các mục còn lại giữ ở bản nháp.")
            if st.button(f"Luyện tập {ready} mục đã kiểm chứng", key="f2_manual_practice_subset"):
                subset = runtime["review"].verified_subset(resource, context=context.sources)
                _start_practice(runtime, subset, draft["format"], context)
                st.rerun()
        else:
            st.info("Chưa có mục đủ điều kiện luyện tập. Xem trích dẫn/lý do; có thể đổi nguồn hoặc tạo lại. Không có nút bỏ qua kiểm chứng.")
    except (StudyDraftError, PracticeError, ValueError) as error:
        st.error(str(error))


def _draft_quiz(runtime, resource, attempt):
    st.subheader("3. Làm thử Quiz nháp — chưa kiểm chứng")
    st.warning("Bản nháp do AI tạo. Lượt làm thử và đáp án đề xuất chưa phải kết quả học tập đã kiểm chứng.")
    try:
        context = _context(runtime)
        view = runtime["review"].preview_quiz(resource, context=context.sources, submission=attempt["submission"])
        st.caption(f"{view.actual_count} câu thực tế / {view.requested_count} yêu cầu · {view.status}")
        if view.result is None:
            with st.form(f"f2_draft_quiz_form_{attempt['attempt_id']}"):
                answers = []
                for index, question in enumerate(view.questions, 1):
                    st.markdown(f"**Câu {index}**")
                    st.text(question.question)
                    options = {option.option_id: option.text for option in question.options}
                    selected = st.radio("Chọn một đáp án", list(options), index=None,
                        format_func=lambda option_id, texts=options: f"{option_id}. {texts[option_id]}",
                        key=f"f2_draft_answer_{attempt['attempt_id']}_{question.question_id}")
                    if selected is not None:
                        answers.append({"question_id": question.question_id, "option_id": selected})
                st.caption("Nộp bản nháp để xem đối chiếu theo đáp án AI đề xuất, giải thích và trích dẫn. Câu bỏ trống được ghi là chưa trả lời.")
                submitted = st.form_submit_button("Nộp bản nháp", type="primary")
            if submitted:
                submission = QuizSubmission(answers=answers)
                runtime["review"].preview_quiz(resource, context=context.sources, submission=submission)
                attempt["submission"] = submission
                st.rerun()
        else:
            result = view.result
            st.info(f"Khớp đáp án AI đề xuất: {result.matching_count}/{result.total_count} · {result.match_percent:g}% — chưa phải điểm đã kiểm chứng.")
            st.caption(f"Đã trả lời {result.answered_count}/{result.total_count} câu")
            for index, (question, feedback) in enumerate(zip(view.questions, result.items, strict=True), 1):
                with st.container(border=True):
                    st.markdown(f"**Câu {index} · {'Khớp đề xuất' if feedback.matches_proposed else 'Chưa khớp đề xuất'}**")
                    st.text(question.question)
                    options = {option.option_id: option.text for option in question.options}
                    st.text("Bạn chọn: " + (options[feedback.selected_option_id] if feedback.selected_option_id else "Chưa trả lời"))
                    st.text("Đáp án AI đề xuất: " + options[feedback.proposed_option_id])
                    st.text(feedback.explanation)
                    _sources(feedback.source_refs)
            if st.button("Làm lại Quiz nháp", key="f2_manual_retry_draft"):
                attempt["submission"] = None
                attempt["attempt_id"] = str(uuid4())
                st.rerun()
    except (StudyDraftError, ValidationError, ValueError) as error:
        st.error(str(error))
    if st.button("Quay lại review bản nháp", key="f2_manual_back_review"):
        st.session_state["f2_manual_draft_quiz"] = None
        st.rerun()
