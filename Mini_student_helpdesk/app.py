"""Streamlit chat UI for the demo student helpdesk."""

from __future__ import annotations

import streamlit as st

import llm_client


SUGGESTIONS = (
    ("Hiểu bài", "Giúp em hiểu một khái niệm khó bằng ví dụ dễ hiểu."),
    ("Lập trình", "Em mới học Python, hãy giải thích vòng lặp for kèm ví dụ."),
    ("Ôn thi", "Giúp em lập kế hoạch ôn thi phù hợp với thời gian của em."),
    ("Cách học", "Em học trước quên sau, nên thay đổi phương pháp học thế nào?"),
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
    if st.session_state.get("domain_version") != "study_support_v1":
        st.session_state.domain_version = "study_support_v1"
        st.session_state.messages = []
        st.session_state.response_cache = {}
        st.session_state.failed_question = None
        st.session_state.last_error = None
        st.session_state.pending_question = None
    defaults = {
        "messages": [],
        "failed_question": None,
        "last_error": None,
        "pending_question": None,
        "draft_question": "",
        "response_cache": {},
        "student_profile": "",
        "answer_style": "Tự động",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_response_json(response: dict, info: dict | None = None) -> None:
    with st.expander("JSON đã validate"):
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
                    st.caption("Sử dụng API")
                    st.write("Cache phiên" if stats["source"] == "session_cache" else "Gọi API")
                    st.write(f"Input thực tế: {stats['input_tokens'] if stats['input_tokens'] is not None else 'API không cung cấp'}")
                    st.write(f"Output thực tế: {stats['output_tokens'] if stats['output_tokens'] is not None else 'API không cung cấp'}")
                    st.caption(f"Input ước tính: {stats['estimated_input_tokens']} · Trần output: {stats['output_limit']} · Lịch sử: {stats['history_messages']} tin")
                    if stats.get("reasoning_reserve"):
                        st.caption(f"Mức đáp án: {stats['answer_limit']} · Dự phòng suy luận: {stats['reasoning_reserve']} token (trần, không phải số đã dùng).")
                    if stats["dropped_for_budget"]:
                        st.caption(f"Đã bỏ {stats['dropped_for_budget']} tin cũ để vừa ngân sách; có thể nhắc lại chi tiết cần dùng.")


def _render_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("response_json"):
                _render_response_json(message["response_json"], message.get("runtime_info"))


def _handle_question(question: str) -> None:
    question = question.strip()
    if not question:
        st.warning("Bạn hãy nhập câu hỏi trước nhé.")
        return
    if len(question) > llm_client.MAX_QUESTION_CHARS:
        st.error("Câu hỏi quá dài. Vui lòng rút gọn còn tối đa 16.000 ký tự.")
        return

    history = st.session_state.messages
    runtime_info = llm_client.get_runtime_info()
    runtime_info["request_stats"] = {}
    with st.chat_message("user"):
        st.markdown(question)

    try:
        with st.spinner("Đang trả lời…"):
            answer = llm_client.ask_student(question, history, response_cache=st.session_state.response_cache,
                                            request_stats=runtime_info["request_stats"],
                                            student_profile=st.session_state.student_profile,
                                            answer_style={"Tự động": "auto", "Ngắn gọn": "short", "Chi tiết": "detailed"}[st.session_state.answer_style])
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
        if answer["status"] == "error":
            st.warning(answer["answer"])
            _render_response_json(answer, runtime_info)
        else:
            st.markdown(answer["answer"])
            _render_response_json(answer, runtime_info)

    if answer["status"] == "error":
        st.session_state.failed_question = question
        st.session_state.last_error = answer["answer"]
        st.button("Thử lại câu hỏi này", on_click=_retry_failed_question, key="retry_invalid_json")
        return

    st.session_state.messages.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer["answer"], "response_json": answer,
             "runtime_info": runtime_info},
        ]
    )
    st.session_state.failed_question = None
    st.session_state.last_error = None


def main() -> None:
    st.set_page_config(page_title="AI Student Helpdesk — Trợ lý học tập", layout="centered")
    _init_state()
    runtime_info = llm_client.get_runtime_info()
    with st.sidebar:
        st.subheader("Kết nối LLM")
        st.caption("Nhà cung cấp")
        st.text(runtime_info["provider"])
        st.caption("Model")
        st.code(runtime_info["model"], language=None)
        st.caption("URL API")
        st.code(runtime_info["url"], language=None)
        st.divider()
        st.subheader("Cá nhân hóa")
        st.selectbox("Mức trả lời", ("Tự động", "Ngắn gọn", "Chi tiết"), key="answer_style")
        st.text_area("Bối cảnh của bạn (tùy chọn)", key="student_profile", max_chars=2000,
                     placeholder="Ví dụ: Sinh viên CNTT năm 1, mới học Python, có 1 giờ học mỗi ngày.")
        st.caption("Bối cảnh được gửi cùng câu hỏi để AI tư vấn phù hợp. Cuộc trò chuyện mới vẫn giữ lựa chọn này.")
    st.markdown(
        "<style>textarea { resize: none !important; }</style>",
        unsafe_allow_html=True,
    )

    st.title("AI Student Helpdesk")
    st.caption(
        "Trợ lý học tập cho sinh viên: hiểu bài, giải bài tập, lập trình, ôn thi và định hướng học tập."
    )

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
        placeholder="Ví dụ: Giải thích vòng lặp Python hoặc giúp em lập kế hoạch ôn thi.",
    )
    st.button("Gửi câu hỏi", on_click=_queue_typed_question, key="send_question")

    pending_question = st.session_state.pop("pending_question", None)
    if pending_question is not None:
        _handle_question(pending_question)


if __name__ == "__main__":
    main()
