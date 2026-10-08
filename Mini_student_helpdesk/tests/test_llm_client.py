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
            {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"},
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
        self.assertEqual(request["max_output_tokens"], llm_client.SINGLE_TOPIC_OUTPUT_TOKENS)
        self.assertNotIn("### 5.", request["instructions"])

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

    def test_all_faq_questions_keep_their_entire_section(self) -> None:
        import re
        faq = llm_client.load_faq()
        for heading in re.findall(r"(?m)^### (.+)$", faq):
            with self.subTest(question=heading):
                selected, _ = llm_client.select_faq(heading, [])
                self.assertIn("### " + heading, selected)

    def test_ambiguous_and_follow_up_keep_context_and_full_faq(self) -> None:
        history = [{"role": "user", "content": "Em đăng ký môn ở đâu?"},
                   {"role": "assistant", "content": "Mở mục đăng ký học phần."}]
        self.assertEqual(llm_client.select_history("Còn hạn thì sao?", history), history)
        faq, limit = llm_client.select_faq("Còn hạn thì sao?", history)
        self.assertEqual(faq, llm_client.load_faq())
        self.assertEqual(limit, llm_client.MAX_OUTPUT_TOKENS)

    def test_only_unrelated_pairs_are_dropped_for_independent_lookup(self) -> None:
        history = [{"role": "user", "content": "Em đăng ký môn ở đâu?"},
                   {"role": "assistant", "content": "Cổng sinh viên."},
                   {"role": "user", "content": "Em đã đóng học phí rồi."},
                   {"role": "assistant", "content": "Giữ lại biên nhận."}]
        self.assertEqual(llm_client.select_history("Em xem học phí ở đâu?", history), history[2:])
        self.assertEqual(llm_client.select_history("Còn học phí đó xem ở đâu?", history), history)

    def test_multi_topic_keeps_both_sections_and_output_budget(self) -> None:
        faq, limit = llm_client.select_faq("Học phí và đăng ký môn ở đâu?", [])
        self.assertIn("### 1.", faq)
        self.assertIn("### 5.", faq)
        self.assertEqual(limit, llm_client.MAX_OUTPUT_TOKENS)

    def test_unknown_faq_layout_falls_back_to_full_document(self) -> None:
        with patch.object(llm_client, "load_faq", return_value="# FAQ\n## Quy định mới\nNội dung mới"):
            faq, limit = llm_client.select_faq("Em xem học phí ở đâu?", [])
        self.assertIn("Nội dung mới", faq)
        self.assertEqual(limit, llm_client.MAX_OUTPUT_TOKENS)

    def test_identical_request_uses_cache_but_changed_context_does_not(self) -> None:
        cache = {}
        llm_client.ask_student("Em xem học phí ở đâu?", [], response_cache=cache)
        llm_client.ask_student("Em xem học phí ở đâu?", [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 1)
        llm_client.ask_student("Còn hạn thì sao?", [{"role": "user", "content": "Câu trước"}], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 2)
        with patch.object(llm_client, "load_system_prompt", return_value="Prompt đã thay đổi"):
            llm_client.ask_student("Em xem học phí ở đâu?", [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 3)

    def test_expired_cache_calls_api_again(self) -> None:
        cache = {}
        llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        with patch.object(llm_client.time, "monotonic", return_value=next(iter(cache.values()))[0] + 301):
            llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_repeated_standalone_lookup_hits_cache_without_second_call(self) -> None:
        cache = {}
        question = "Em xem học phí ở đâu?"
        answer = llm_client.ask_student(question, [], response_cache=cache)
        history = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        self.assertEqual(llm_client.ask_student(question, history, response_cache=cache), answer)
        self.client.responses.create.assert_called_once()

    def test_incomplete_answer_is_not_cached(self) -> None:
        cache = {}
        self.client.responses.create.return_value = SimpleNamespace(status="incomplete", output_text="Câu bị cắt")
        with self.assertRaisesRegex(llm_client.HelpdeskError, "chưa hoàn thành"):
            llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        self.assertEqual(cache, {})

    def test_document_cache_reloads_after_edit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            faq = Path(folder) / "faq.md"
            faq.write_text("Nội dung đầu", encoding="utf-8")
            with patch.object(llm_client, "FAQ_PATH", faq):
                self.assertEqual(llm_client.load_faq(), "Nội dung đầu")
                faq.write_text("Nội dung đã cập nhật dài hơn", encoding="utf-8")
                self.assertEqual(llm_client.load_faq(), "Nội dung đã cập nhật dài hơn")


if __name__ == "__main__":
    unittest.main()
