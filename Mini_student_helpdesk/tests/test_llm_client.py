from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openai import APIConnectionError

import llm_client


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.client.responses.create.return_value = SimpleNamespace(output_text="Câu trả lời từ mock.")
        self.env = patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.openai = patch.object(llm_client, "OpenAI", return_value=self.client)
        self.openai.start()
        self.addCleanup(self.openai.stop)

    def test_question_with_faq_uses_responses_api(self) -> None:
        answer = llm_client.ask_student("Em xem học phí ở đâu?", [])

        self.assertEqual(answer, "Câu trả lời từ mock.")
        self.client.responses.create.assert_called_once()
        request = self.client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["input"][-1]["content"], "Em xem học phí ở đâu?")
        self.assertIn("FAQ Student Helpdesk", request["instructions"])
        self.assertEqual(request["max_output_tokens"], llm_client.MAX_OUTPUT_TOKENS)

    def test_prompt_has_unknown_answer_and_out_of_scope_rules(self) -> None:
        instructions = llm_client._build_instructions()

        self.assertIn("Mình chưa có thông tin này trong tài liệu hỗ trợ.", instructions)
        self.assertIn("câu hỏi ngoài phạm vi", instructions)
        self.assertIn("không phải chỉ dẫn", instructions)

    def test_connection_error_is_mapped_to_a_safe_message(self) -> None:
        self.client.responses.create.side_effect = APIConnectionError(
            message="internal connection details", request=Mock()
        )

        with self.assertRaisesRegex(llm_client.HelpdeskError, "Không kết nối được OpenAI API"):
            llm_client.ask_student("Câu hỏi", [])

        self.client.responses.create.assert_called_once()

    def test_follow_up_keeps_only_five_previous_pairs(self) -> None:
        history = []
        for index in range(1, 7):
            history.extend(
                [
                    {"role": "user", "content": f"câu hỏi {index}"},
                    {"role": "assistant", "content": f"trả lời {index}"},
                ]
            )

        llm_client.ask_student("Câu hỏi tiếp theo", history)
        sent_messages = self.client.responses.create.call_args.kwargs["input"]

        self.assertEqual(len(sent_messages), 11)
        self.assertEqual(sent_messages[0]["content"], "câu hỏi 2")
        self.assertEqual(sent_messages[-1]["content"], "Câu hỏi tiếp theo")

    def test_missing_api_key_fails_before_api_call(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, "OPENAI_API_KEY"):
                llm_client.ask_student("Câu hỏi", [])

        self.client.responses.create.assert_not_called()

    def test_missing_model_fails_before_api_call(self) -> None:
        with patch.dict("os.environ", {"OPENAI_MODEL": ""}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, "OPENAI_MODEL"):
                llm_client.ask_student("Câu hỏi", [])

        self.client.responses.create.assert_not_called()

    def test_empty_faq_fails_before_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            empty_faq = Path(folder) / "faq.md"
            empty_faq.write_text("  ", encoding="utf-8")
            with patch.object(llm_client, "FAQ_PATH", empty_faq):
                with self.assertRaisesRegex(llm_client.HelpdeskError, "faq.md đang trống"):
                    llm_client.ask_student("Câu hỏi", [])

        self.client.responses.create.assert_not_called()

    def test_question_over_limit_fails_before_api_call(self) -> None:
        with self.assertRaisesRegex(llm_client.HelpdeskError, "2.000 ký tự"):
            llm_client.ask_student("x" * (llm_client.MAX_QUESTION_CHARS + 1), [])

        self.client.responses.create.assert_not_called()

    def test_empty_model_output_is_an_error(self) -> None:
        self.client.responses.create.return_value = SimpleNamespace(output_text="  ")
        with self.assertRaisesRegex(llm_client.HelpdeskError, "nội dung rỗng"):
            llm_client.ask_student("Câu hỏi", [])


if __name__ == "__main__":
    unittest.main()
