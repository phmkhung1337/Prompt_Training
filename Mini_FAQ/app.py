"""Streamlit chat UI for the demo student helpdesk."""

from __future__ import annotations

import streamlit as st

import llm_client
from ui_theme import apply_theme


SUGGESTIONS = (
    ("Học phí", "Học phí của tôi là bao nhiêu?"),
    ("Đăng ký môn", "Em đăng ký học phần như thế nào?"),
    ("Giấy xác nhận", "Em xin giấy xác nhận sinh viên ở đâu?"),
    ("Hỗ trợ sinh viên", "Tôi liên hệ bộ phận hỗ trợ sinh viên bằng cách nào?"),
)

TOPIC_DETAILS = (
    (":material/account_balance_wallet:", "Xem mức học phí theo kỳ"),
    (":material/menu_book:", "Tra cứu đăng ký học phần"),
    (":material/description:", "Tìm hướng dẫn xin giấy tờ"),
    (":material/support_agent:", "Tìm đầu mối hỗ trợ của trường"),
)


def _start_new_chat(*, clear_draft: bool = True) -> None:
    st.session_state.messages = []
    st.session_state.failed_question = None
    st.session_state.last_error = None
    st.session_state.pending_question = None
    if clear_draft:
        st.session_state.draft_question = ""
    st.session_state.response_cache = {}


def _queue_question(question: str) -> None:
    st.session_state.pending_question = question
    st.session_state.draft_question = ""
    st.session_state.failed_question = None
    st.session_state.last_error = None


def _queue_typed_question() -> None:
    st.session_state.pending_question = st.session_state.get("draft_question", "")
    st.session_state.draft_question = ""
    st.session_state.failed_question = None
    st.session_state.last_error = None


def _retry_failed_question() -> None:
    question = st.session_state.get("failed_question")
    if question:
        st.session_state.pending_question = question
        st.session_state.failed_question = None
        st.session_state.last_error = None


def _init_state() -> None:
    defaults = {
        "messages": [],
        "failed_question": None,
        "last_error": None,
        "pending_question": None,
        "draft_question": "",
        "response_cache": {},
        "student_profile": "",
        "answer_style": "Tự động",
        "appearance": "Tối",
        "show_diagnostics": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_response_json(response: dict, info: dict | None = None) -> None:
    if not st.session_state.get("show_diagnostics", False):
        return
    with st.expander("Chi tiết phản hồi"):
        json_column, info_column = st.columns([3, 2])
        with json_column:
            st.json(response)
        with info_column:
            if info:
                st.caption("Model")
                st.code(info["model"], language=None)
                st.caption("URL API")
                st.code(info["url"], language=None)
                if info.get("request_stats"):
                    stats = info["request_stats"]
                    if stats["source"] == "no_match":
                        st.caption("Không có FAQ liên quan · Không gọi API")
                        return
                    if stats["source"] == "clarification":
                        st.caption("Hỏi lại kỳ học · Không gọi API")
                        return
                    if stats["source"] == "local":
                        st.caption("Hội thoại cơ bản · Không gọi API")
                        return
                    st.caption("Sử dụng API")
                    st.write("Cache phiên" if stats["source"] == "session_cache" else "Gọi API")
                    st.write(f"Input thực tế: {stats['input_tokens'] if stats['input_tokens'] is not None else 'API không cung cấp'}")
                    st.write(f"Output thực tế: {stats['output_tokens'] if stats['output_tokens'] is not None else 'API không cung cấp'}")
                    st.caption(f"Input ước tính: {stats['estimated_input_tokens']} · Trần output: {stats['output_limit']} · Lịch sử: {stats['history_messages']} tin")
                    if stats["dropped_for_budget"]:
                        st.caption(f"Đã bỏ {stats['dropped_for_budget']} tin cũ để vừa ngân sách; có thể nhắc lại chi tiết cần dùng.")
                    if "retrieval_ms" in stats:
                        st.caption(f"Tra FAQ: {stats['retrieval_ms']} ms · Tổng: {stats.get('elapsed_ms', 0)} ms")


def _render_tuition_suggestions(response: dict) -> None:
    if response.get("category") != "tuition" or response.get("status") not in {"clarify", "answered"}:
        return
    with st.container(key="tuition_choices"):
        st.caption("Chọn kỳ muốn xem · Kỳ 0 là tiếng Anh")
        for term, column in enumerate(st.columns(9)):
            column.button(
                "Kỳ 0 · Tiếng Anh" if term == 0 else f"Kỳ {term}",
                key=f"tuition_term_{term}",
                on_click=_queue_question,
                args=(f"Học phí kỳ {term} là bao nhiêu?",),
                use_container_width=True,
            )


def _render_followups(response: dict, info: dict | None = None) -> None:
    if response.get("category") == "tuition":
        _render_tuition_suggestions(response)
    elif response.get("status") == "unknown" or (info or {}).get("request_stats", {}).get("source") == "local":
        with st.container(key="recovery_suggestions"):
            st.caption("Chọn một chủ đề hoặc nói rõ hơn điều bạn muốn tìm:")
            for index, column in enumerate(st.columns(4)):
                label, question = SUGGESTIONS[index]
                column.button(label, key=f"followup_topic_{index}", on_click=_queue_question,
                              args=(question,), use_container_width=True)


def _render_data_notice(response: dict, sources: list[dict]) -> None:
    if any(source.get("source_is_demo") for source in sources):
        note = "Dữ liệu demo"
        if response.get("category") == "tuition":
            note += " · Mức học phí theo kỳ, không phải công nợ cá nhân"
        st.caption(note)


def _render_history() -> None:
    for index, message in enumerate(st.session_state.messages):
        avatar = ":material/auto_awesome:" if message["role"] == "assistant" else ":material/person:"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            if message.get("response_json"):
                _render_data_notice(message["response_json"], message.get("sources", []))
                if index == len(st.session_state.messages) - 1 and st.session_state.pending_question is None:
                    _render_followups(message["response_json"], message.get("runtime_info"))
            if message.get("sources"):
                _render_sources(message["sources"], message.get("relevant", True))
            if message.get("response_json"):
                _render_response_json(message["response_json"], message.get("runtime_info"))


def _render_sources(hits: list[dict], relevant: bool) -> None:
    if not relevant:
        return
    if hits:
        with st.expander(f"Nguồn tham khảo · {len(hits)} FAQ", expanded=False):
            for i, hit in enumerate(hits, 1):
                with st.expander(f"{i}. {hit['question']}", expanded=False):
                    st.markdown(hit["answer"])
                    if st.session_state.get("show_diagnostics", False):
                        st.caption(f"Điểm tìm kiếm: {hit['score']:.3f}")


def _handle_question(question: str) -> None:
    question = question.strip()
    if question.lower() == "/reset":
        _start_new_chat(clear_draft=False)
        st.rerun()
    if not question:
        st.warning("Bạn hãy nhập câu hỏi trước nhé.")
        return
    if len(question) > llm_client.MAX_QUESTION_CHARS:
        st.error("Câu hỏi quá dài. Vui lòng rút gọn còn tối đa 16.000 ký tự.")
        return

    history = st.session_state.messages
    runtime_info = llm_client.get_runtime_info()
    runtime_info["request_stats"] = {}
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(question)

    sources, relevant, streamed = [], True, ""
    assistant = st.chat_message("assistant", avatar=":material/auto_awesome:")
    with assistant:
        answer_area = st.empty()
        suggestion_area = st.container()
        source_area = st.container()
        details_area = st.container()

    def show_sources(hits, found):
        nonlocal sources, relevant
        sources, relevant = hits, found
        with source_area:
            _render_sources(hits, found)

    def show_delta(delta):
        nonlocal streamed
        streamed += delta
        answer_area.markdown(streamed + " ▌")

    try:
        with st.spinner("Đang tìm FAQ và trả lời…"):
            answer = llm_client.ask_student(question, history, response_cache=st.session_state.response_cache,
                                            request_stats=runtime_info["request_stats"],
                                            student_profile=st.session_state.student_profile,
                                            answer_style={"Tự động": "auto", "Ngắn gọn": "short", "Chi tiết": "detailed"}[st.session_state.answer_style],
                                            on_sources=show_sources, on_delta=show_delta)
    except llm_client.HelpdeskError as exc:
        answer_area.error(str(exc))
        st.session_state.failed_question = question
        st.session_state.last_error = str(exc)
        return
    except Exception:
        # Keep SDK details, local paths and stack traces out of the chat UI.
        st.session_state.failed_question = question
        st.session_state.last_error = "Có lỗi ngoài dự kiến. Bạn có thể thử lại câu hỏi này."
        answer_area.error(st.session_state.last_error)
        return

    with assistant:
        if answer["status"] == "error":
            answer_area.warning(answer["answer"])
        else:
            answer_area.markdown(answer["answer"])
            with suggestion_area:
                _render_data_notice(answer, sources)
                _render_followups(answer, runtime_info)
        with details_area:
            _render_response_json(answer, runtime_info)

    if answer["status"] == "error":
        st.session_state.failed_question = question
        st.session_state.last_error = answer["answer"]
        return

    st.session_state.messages.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer["answer"], "response_json": answer,
             "runtime_info": runtime_info, "sources": sources, "relevant": relevant},
        ]
    )
    st.session_state.messages = st.session_state.messages[-llm_client.MAX_HISTORY_MESSAGES:]
    st.session_state.failed_question = None
    st.session_state.last_error = None


def _active_topic() -> str | None:
    if not st.session_state.messages:
        return None
    latest_question = next((message["content"] for message in reversed(st.session_state.messages)
                            if message["role"] == "user"), "")
    for label, question in SUGGESTIONS:
        if latest_question == question:
            return label
    response = st.session_state.messages[-1].get("response_json", {})
    return {
        "tuition": "Học phí",
        "course_registration": "Đăng ký môn",
        "student_services": "Giấy xác nhận",
    }.get(response.get("category"))


def _render_welcome() -> None:
    st.markdown(
        '<div class="welcome-hero">'
        '<div class="hero-symbol" aria-hidden="true">✦</div>'
        '<h1 class="welcome-title">Bạn cần hỗ trợ gì hôm nay?</h1>'
        '<p class="welcome-description">Học phí, lịch học và thủ tục sinh viên.<br>'
        'Hỏi tự nhiên, tìm câu trả lời từ bộ FAQ của trường.</p></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="welcome_topics"):
        for start in (0, 2):
            columns = st.columns(2)
            for index, column in enumerate(columns, start):
                label, question = SUGGESTIONS[index]
                icon, description = TOPIC_DETAILS[index]
                with column:
                    with st.container(key=f"topic_card_{index}"):
                        st.button(
                            label, icon=icon, key=f"suggestion_{index}",
                            on_click=_queue_question, args=(question,),
                            use_container_width=True,
                        )
                        st.caption(description)


def main() -> None:
    st.set_page_config(page_title="Campus FAQ Assistant", page_icon="🎓", layout="wide")
    _init_state()

    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand"><div class="brand-mark" aria-hidden="true">C</div>'
            '<div class="brand-name">Campus<span> FAQ</span></div></div>',
            unsafe_allow_html=True,
        )
        st.caption("Trợ lý thông tin sinh viên")
        with st.container(key="new_chat"):
            st.button(
                "Cuộc trò chuyện mới", icon=":material/add:",
                on_click=_start_new_chat, use_container_width=True,
            )
        st.markdown('<div class="sidebar-label">KHÁM PHÁ</div>', unsafe_allow_html=True)
        with st.container(key="sidebar_topics"):
            active_topic = _active_topic()
            for index, (label, question) in enumerate(SUGGESTIONS):
                st.button(
                    label, icon=TOPIC_DETAILS[index][0], key=f"nav_topic_{index}",
                    on_click=_queue_question, args=(question,),
                    type="primary" if label == active_topic else "secondary",
                    use_container_width=True,
                )
        st.divider()
        with st.expander("Cá nhân hóa"):
            st.selectbox("Mức trả lời", ("Tự động", "Ngắn gọn", "Chi tiết"), key="answer_style")
            st.text_area(
                "Bối cảnh của bạn (tùy chọn)", key="student_profile", max_chars=2000,
                placeholder="Ví dụ: Sinh viên CNTT năm 1, mới học Python.",
            )
            st.caption("Bối cảnh giúp bot trả lời phù hợp hơn và được giữ khi tạo cuộc trò chuyện mới.")
        st.markdown('<div class="sidebar-label">GIAO DIỆN</div>', unsafe_allow_html=True)
        st.radio("Giao diện", ("Sáng", "Tối"), key="appearance", horizontal=True, label_visibility="collapsed")
        st.caption("Gõ /reset để bắt đầu lại · Nhớ 5 lượt gần nhất")
        with st.expander("Thông tin kết nối"):
            runtime_info = llm_client.get_runtime_info()
            st.caption(runtime_info["provider"])
            st.code(runtime_info["model"], language=None)
            st.code(runtime_info["url"], language=None)
            st.checkbox("Hiện chi tiết kỹ thuật", key="show_diagnostics")

    apply_theme(st.session_state.appearance)
    st.markdown(
        '<div class="workspace-header"><span class="workspace-title">Campus FAQ Assistant</span>'
        '<span class="workspace-status"><span class="status-dot" aria-hidden="true"></span>'
        'Tra cứu từ bộ FAQ</span></div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.messages and st.session_state.pending_question is None:
        _render_welcome()

    has_conversation = bool(st.session_state.messages or st.session_state.pending_question or st.session_state.failed_question)
    with st.container(key="conversation", height=420 if has_conversation else "content", border=False,
                      autoscroll=has_conversation):
        _render_history()
        pending_question = st.session_state.pop("pending_question", None)
        if pending_question is not None:
            _handle_question(pending_question)

        if st.session_state.failed_question:
            if pending_question is None:
                st.error(st.session_state.last_error or "Chưa thể xử lý câu hỏi này.")
                st.caption(f"Câu hỏi: {st.session_state.failed_question}")
            st.button("Thử lại câu hỏi này", on_click=_retry_failed_question, key="retry_failed")

    with st.container(key="chat_composer"):
        with st.form("message_form", border=False):
            input_column, send_column = st.columns([6, 1.4], vertical_alignment="bottom")
            with input_column:
                st.text_area(
                    "Nhập câu hỏi hoặc tin nhắn của bạn:",
                    key="draft_question", height=80, label_visibility="collapsed",
                    max_chars=llm_client.MAX_QUESTION_CHARS,
                    placeholder="Hỏi về học phí, đăng ký môn hoặc thủ tục…",
                )
            with send_column:
                st.form_submit_button(
                    "Gửi câu hỏi", icon=":material/arrow_upward:",
                    on_click=_queue_typed_question, key="send_question", type="primary",
                    use_container_width=True,
                )
    with st.container(key="composer_note"):
        st.caption("Ctrl+Enter để gửi · Enter để xuống dòng · Kiểm tra thông tin quan trọng từ nguồn tham khảo.")

if __name__ == "__main__":
    main()
