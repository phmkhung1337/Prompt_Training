from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import llm_client


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class StreamlitAppTests(unittest.TestCase):
    def _button(self, app: AppTest, label: str):
        return next(button for button in app.button if button.label == label)

    def test_opening_page_does_not_call_api(self) -> None:
        with patch("llm_client.ask_student") as ask:
            app = AppTest.from_file(str(APP_PATH)).run()

        ask.assert_not_called()
        self.assertEqual(len(app.session_state["messages"]), 0)

    def test_theme_switch_preserves_chat_draft_and_preferences_without_api(self):
        with patch("llm_client.ask_student") as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            self.assertEqual(app.session_state["appearance"], "Tối")
            history = [{"role": "user", "content": "Câu trước"}, {"role": "assistant", "content": "Trả lời trước"}]
            app.session_state["messages"] = history.copy()
            app.session_state["response_cache"] = {"cached": (0, {"answer": "Đã lưu"})}
            app.session_state["student_profile"] = "Sinh viên năm 1"
            app.session_state["draft_question"] = "Câu hỏi đang soạn"
            app.run()
            app.radio[0].set_value("Sáng").run()
            self.assertEqual(app.session_state["messages"], history)
            self.assertEqual(app.session_state["draft_question"], "Câu hỏi đang soạn")
            self.assertIn("cached", app.session_state["response_cache"])
            self.assertEqual(app.session_state["student_profile"], "Sinh viên năm 1")
            self.assertFalse(app.exception)
            self._button(app, "Cuộc trò chuyện mới").click().run()
            self.assertEqual(app.session_state["appearance"], "Sáng")
            app.radio[0].set_value("Tối").run()
            self.assertEqual(app.session_state["appearance"], "Tối")
            self.assertFalse(app.exception)
        ask.assert_not_called()

    def test_reset_command_clears_history_cache_and_errors_without_api(self):
        with patch("llm_client.ask_student") as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            app.session_state["messages"] = [{"role": "user", "content": "Cũ"}, {"role": "assistant", "content": "Cũ"}]
            app.session_state["response_cache"] = {"old": (0, {})}
            app.session_state["failed_question"] = "Lỗi cũ"
            app.run()
            next(area for area in app.text_area if area.key == "draft_question").set_value(" /reset ")
            self._button(app, "Gửi câu hỏi").click().run()
            self.assertEqual(app.session_state["messages"], [])
            self.assertEqual(app.session_state["response_cache"], {})
            self.assertIsNone(app.session_state["failed_question"])
            self.assertFalse(app.exception)
        ask.assert_not_called()

    def test_sources_streaming_and_five_turn_limit(self):
        hits = [{"question": f"Nguồn {i}", "answer": f"Nội dung {i}", "score": .8} for i in range(3)]

        def respond(question, history, **kwargs):
            kwargs["on_sources"](hits, True)
            kwargs["on_delta"]("Xin ")
            kwargs["on_delta"]("chào")
            return {"answer": "Xin chào", "category": "other", "status": "answered"}

        with patch("llm_client.ask_student", side_effect=respond):
            app = AppTest.from_file(str(APP_PATH)).run()
            app.session_state["messages"] = [{"role": role, "content": f"{i}-{role}"} for i in range(5) for role in ("user", "assistant")]
            app.run()
            self._button(app, "Học phí").click().run()
            self.assertEqual(len(app.session_state["messages"]), 10)
            self.assertEqual(app.session_state["messages"][-1]["sources"], hits)
            self.assertEqual(app.session_state["messages"][0]["content"], "1-user")
            self.assertFalse(app.exception)

    def test_no_match_stats_render_without_error(self):
        def respond(question, history, **kwargs):
            kwargs["on_sources"]([], False)
            kwargs["request_stats"].update(source="no_match", input_tokens=0, output_tokens=0)
            return {"answer": llm_client.UNKNOWN_ANSWER, "category": "other", "status": "unknown"}

        with patch("llm_client.ask_student", side_effect=respond):
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["messages"][-1]["content"], llm_client.UNKNOWN_ANSWER)

    def test_tuition_clarification_shows_all_terms_and_survives_rerun(self):
        with patch("llm_client.OpenAI") as api, patch("llm_client.retrieve_faq") as retrieve:
            app = AppTest.from_file(str(APP_PATH)).run()
            next(area for area in app.text_area if area.key == "draft_question").set_value("Học phí của tôi là bao nhiêu?")
            self._button(app, "Gửi câu hỏi").click().run()
            self.assertEqual(app.session_state["messages"][-1]["content"], llm_client.TUITION_CLARIFICATION)
            self.assertEqual(len([b for b in app.button if (b.key or "").startswith("tuition_term_")]), 9)
            self.assertFalse(app.exception)
            app.run()
            self.assertEqual(len([b for b in app.button if (b.key or "").startswith("tuition_term_")]), 9)
            self._button(app, "Cuộc trò chuyện mới").click().run()
            self.assertFalse([b for b in app.button if (b.key or "").startswith("tuition_term_")])
        api.assert_not_called()
        retrieve.assert_not_called()

    def test_term_choice_submits_specific_question_once_and_can_switch_terms(self):
        clarify = {"answer": llm_client.TUITION_CLARIFICATION, "category": "tuition", "status": "clarify"}
        answer = {"answer": "Học phí kỳ 3: 36.300.000 đồng (demo).", "category": "tuition", "status": "answered"}
        with patch("llm_client.ask_student", side_effect=[clarify, answer, dict(answer, answer="Kỳ 0: 20.000.000 đồng (demo).")]) as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self._button(app, "Kỳ 3").click().run()
            self.assertEqual(ask.call_args.args[0], "Học phí kỳ 3 là bao nhiêu?")
            self.assertEqual(app.session_state["messages"][-1]["content"], answer["answer"])
            self.assertFalse(app.exception)
            app.run()
            self.assertEqual(ask.call_count, 2)
            self._button(app, "Kỳ 0 · Tiếng Anh").click().run()
            self.assertEqual(ask.call_args.args[0], "Học phí kỳ 0 là bao nhiêu?")
            self.assertEqual(ask.call_count, 3)
            self.assertFalse(app.exception)

    def test_unrelated_question_hides_term_choices(self):
        clarify = {"answer": llm_client.TUITION_CLARIFICATION, "category": "tuition", "status": "clarify"}
        with patch("llm_client.ask_student", side_effect=[clarify, {"answer": "Mở cổng sinh viên.", "category": "course_registration", "status": "answered"}]):
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self._button(app, "Đăng ký môn").click().run()
            self.assertFalse([b for b in app.button if (b.key or "").startswith("tuition_term_")])
            self.assertFalse(app.exception)

    def test_json_fallback_can_retry_without_polluting_history(self) -> None:
        from response_schema import validate_response
        fallback = validate_response("invalid json")
        success = {"answer": "Kỳ 1: 20 triệu đồng.", "category": "tuition", "status": "answered"}
        with patch("llm_client.ask_student", side_effect=[fallback, success]) as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self.assertEqual(app.session_state["messages"], [])
            self.assertTrue(app.session_state["failed_question"])
            self._button(app, "Thử lại câu hỏi này").click().run()
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(app.session_state["messages"][-1]["response_json"], success)
            self.assertEqual(app.session_state["messages"][-1]["content"], success["answer"])
            self.assertFalse(app.exception)

    def test_suggestion_submits_once_and_new_chat_clears_history(self) -> None:
        with patch("llm_client.ask_student", return_value={"answer": "FAQ answer", "category": "tuition", "status": "answered"}) as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(len(app.session_state["messages"]), 2)

            app.run()
            self.assertEqual(ask.call_count, 1)

            self._button(app, "Cuộc trò chuyện mới").click().run()
            self.assertEqual(app.session_state["messages"], [])

    def test_text_area_send_button_submits_once_and_clears_draft(self) -> None:
        with patch("llm_client.ask_student", return_value={"answer": "FAQ answer", "category": "tuition", "status": "answered"}) as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            next(area for area in app.text_area if area.key == "draft_question").set_value("Em xem học phí ở đâu?")
            self._button(app, "Gửi câu hỏi").click().run()

            self.assertEqual(ask.call_count, 1)
            self.assertEqual(app.session_state["draft_question"], "")
            self.assertEqual(app.session_state["messages"][-1]["content"], "FAQ answer")

            app.run()
            self.assertEqual(ask.call_count, 1)

    def test_failed_question_can_be_retried_without_losing_old_history(self) -> None:
        old_history = [
            {"role": "user", "content": "Câu trước"},
            {"role": "assistant", "content": "Trả lời trước"},
        ]
        with patch.object(llm_client, "ask_student", side_effect=[llm_client.HelpdeskError("API tạm lỗi"), {"answer": "Đã trả lời", "category": "other", "status": "answered"}]) as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            app.session_state["messages"] = old_history.copy()
            app.run()

            self._button(app, "Đăng ký môn").click().run()
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(app.session_state["messages"], old_history)

            self._button(app, "Thử lại câu hỏi này").click().run()
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(app.session_state["messages"][:2], old_history)
            self.assertEqual(app.session_state["messages"][-1]["content"], "Đã trả lời")

    def test_local_greeting_offers_topics_and_diagnostics_are_optional(self):
        with patch("llm_client.OpenAI") as api, patch("llm_client.retrieve_faq") as retrieve:
            app = AppTest.from_file(str(APP_PATH)).run()
            next(area for area in app.text_area if area.key == "draft_question").set_value("Xin chào")
            self._button(app, "Gửi câu hỏi").click().run()
            self.assertEqual(app.session_state["messages"][-1]["runtime_info"]["request_stats"]["source"], "local")
            self.assertEqual(len([b for b in app.button if (b.key or "").startswith("followup_topic_")]), 4)
            self.assertFalse([e for e in app.expander if e.label == "Chi tiết phản hồi"])
            next(c for c in app.checkbox if c.key == "show_diagnostics").check().run()
            self.assertTrue([e for e in app.expander if e.label == "Chi tiết phản hồi"])
            self.assertFalse(app.exception)
        api.assert_not_called()
        retrieve.assert_not_called()

    def test_error_has_one_error_notice_and_one_retry_action(self):
        with patch("llm_client.ask_student", side_effect=llm_client.HelpdeskError("Kết nối tạm lỗi")):
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Đăng ký môn").click().run()
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len([b for b in app.button if b.label == "Thử lại câu hỏi này"]), 1)
            self.assertFalse(app.exception)
            app.run()
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len([b for b in app.button if b.label == "Thử lại câu hỏi này"]), 1)


if __name__ == "__main__":
    unittest.main()
