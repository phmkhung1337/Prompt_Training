"""Streamlit chat UI for the demo student helpdesk."""

from __future__ import annotations

import streamlit as st

import llm_client


SUGGESTIONS = (
    ("Học phí", "Em xem học phí và công nợ ở đâu?"),
    ("Đăng ký môn", "Em đăng ký học phần như thế nào?"),
    ("Giấy xác nhận", "Em xin giấy xác nhận sinh viên ở đâu?"),
)


def _start_new_chat() -> None:
    st.session_state.messages = []
    st.session_state.failed_question = None
    st.session_state.last_error = None
    st.session_state.pending_question = None
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def _handle_question(question: str) -> None:
    question = question.strip()
    if not question:
        st.warning("Bạn hãy nhập câu hỏi trước nhé.")
        return
    if len(question) > llm_client.MAX_QUESTION_CHARS:
        st.error("Câu hỏi quá dài. Vui lòng rút gọn còn tối đa 2.000 ký tự.")
        return

    history = st.session_state.messages[-llm_client.MAX_HISTORY_MESSAGES :]
    with st.chat_message("user"):
        st.markdown(question)

    try:
        with st.spinner("Đang trả lời…"):
            answer = llm_client.ask_student(question, history, response_cache=st.session_state.response_cache)
    except llm_client.HelpdeskError as exc:
        st.session_state.failed_question = question
        st.session_state.last_error = str(exc)
        with st.chat_message("assistant"):
            st.error(str(exc))
        st.button("Thử lại câu hỏi này", on_click=_retry_failed_question, key="retry_failed_after_error")
        return
    except Exception:
        # Keep SDK details, local paths and stack traces out of the chat UI.
        st.session_state.failed_question = question
        st.session_state.last_error = "Có lỗi ngoài dự kiến. Bạn có thể thử lại câu hỏi này."
        with st.chat_message("assistant"):
            st.error(st.session_state.last_error)
        st.button("Thử lại câu hỏi này", on_click=_retry_failed_question, key="retry_failed_after_unexpected_error")
        return

    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    st.session_state.failed_question = None
    st.session_state.last_error = None


def main() -> None:
    st.set_page_config(page_title="Student Helpdesk Chatbot", layout="centered")
    _init_state()
    st.markdown(
        "<style>textarea { resize: none !important; }</style>",
        unsafe_allow_html=True,
    )

    st.title("Student Helpdesk Chatbot")
    st.caption(
        "Hỗ trợ thông tin học phí, đăng ký môn và dịch vụ sinh viên. "
        "Ứng dụng demo dùng FAQ giả lập, chưa kết nối hệ thống của trường."
    )
    st.info("Dữ liệu giả lập dùng để demo — hãy thay FAQ bằng thông tin chính thức trước khi sử dụng thực tế.")

    st.button("Cuộc trò chuyện mới", on_click=_start_new_chat, use_container_width=True)

    st.markdown("**Bạn có thể hỏi nhanh:**")
    columns = st.columns(len(SUGGESTIONS))
    for column, (label, question) in zip(columns, SUGGESTIONS):
        column.button(
            label,
            key=f"suggestion_{label}",
            on_click=_queue_question,
            args=(question,),
            use_container_width=True,
        )

    _render_history()

    if st.session_state.failed_question:
        st.warning(f"Câu hỏi chưa gửi thành công: {st.session_state.failed_question}")
        if st.session_state.last_error:
            st.error(st.session_state.last_error)
        st.button("Thử lại câu hỏi này", on_click=_retry_failed_question, key="retry_failed")

    st.text_area(
        "Nhập câu hỏi hoặc tin nhắn của bạn:",
        key="draft_question",
        height=130,
        max_chars=llm_client.MAX_QUESTION_CHARS,
        placeholder="Ví dụ: Em xem học phí và công nợ ở đâu?",
    )
    st.button("Gửi câu hỏi", on_click=_queue_typed_question, key="send_question")

    pending_question = st.session_state.pop("pending_question", None)
    if pending_question is not None:
        _handle_question(pending_question)


if __name__ == "__main__":
    main()
