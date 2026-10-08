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

    def test_suggestion_submits_once_and_new_chat_clears_history(self) -> None:
        with patch("llm_client.ask_student", return_value="FAQ answer") as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            self._button(app, "Học phí").click().run()
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(len(app.session_state["messages"]), 2)

            app.run()
            self.assertEqual(ask.call_count, 1)

            self._button(app, "Cuộc trò chuyện mới").click().run()
            self.assertEqual(app.session_state["messages"], [])

    def test_text_area_send_button_submits_once_and_clears_draft(self) -> None:
        with patch("llm_client.ask_student", return_value="FAQ answer") as ask:
            app = AppTest.from_file(str(APP_PATH)).run()
            app.text_area[0].set_value("Em xem học phí ở đâu?").run()
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
        with patch.object(llm_client, "ask_student", side_effect=[llm_client.HelpdeskError("API tạm lỗi"), "Đã trả lời"]) as ask:
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


if __name__ == "__main__":
    unittest.main()
