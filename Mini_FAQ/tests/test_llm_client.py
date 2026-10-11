import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openai import APIConnectionError
import llm_client

HITS = [{"id": str(i), "question": f"FAQ {i}", "answer": f"Nội dung {i}", "section": "Học phí", "score": .8 - i / 100} for i in range(1, 4)]


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        llm_client._openai_client.cache_clear()
        self.client = Mock()
        self.response = {"answer": "Đáp án", "category": "tuition", "status": "answered"}
        self.client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(self.response))
        for context in (patch.dict("os.environ", {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model", "LLM_MAX_HISTORY_PAIRS": "24", "LLM_INPUT_BUDGET": "12000"}),
                        patch.object(llm_client, "OpenAI", return_value=self.client),
                        patch.object(llm_client, "retrieve_faq", return_value=(HITS, True))):
            context.start()
            self.addCleanup(context.stop)

    def test_only_three_sources_are_sent_and_shown_before_response(self):
        events = []
        self.client.responses.create.side_effect = lambda **kw: (events.append("api") or SimpleNamespace(output_text=json.dumps(self.response)))
        result = llm_client.ask_student("Học phí?", [], on_sources=lambda hits, found: events.append(hits))
        self.assertEqual(events, [HITS, "api"])
        self.assertEqual(result, self.response)
        request = self.client.responses.create.call_args.kwargs
        for hit in HITS:
            self.assertIn(hit["answer"], request["instructions"])
        self.assertNotIn("### 5.", request["instructions"])
        self.assertFalse(request["store"])

    def test_five_recent_turns_even_with_old_env_value(self):
        history = [{"role": role, "content": f"{i}-{role}"} for i in range(15) for role in ("user", "assistant")]
        llm_client.ask_student("Còn hạn thì sao?", history)
        sent = self.client.responses.create.call_args.kwargs["input"]
        self.assertEqual(sent[:-1], history[-10:])
        self.assertEqual(len(sent), 11)

    def test_tuition_amount_without_term_asks_before_retrieval_or_api(self):
        for question in ("Học phí của tôi là bao nhiêu?", "học phí của tôi là bao nhiều", "Em phải đóng bao nhiêu học phí?"):
            with self.subTest(question=question), patch.object(llm_client, "retrieve_faq") as retrieve:
                stats, deltas = {}, []
                result = llm_client.ask_student(question, [], request_stats=stats, on_delta=deltas.append)
                self.assertEqual(result, {"answer": llm_client.TUITION_CLARIFICATION, "category": "tuition", "status": "clarify"})
                self.assertEqual(deltas, [result["answer"]])
                self.assertEqual(stats["source"], "clarification")
                retrieve.assert_not_called()
        self.client.responses.create.assert_not_called()

    def test_tuition_specific_term_total_and_payment_do_not_ask_term(self):
        for question in ("Học phí kỳ 0 là bao nhiêu?", "Học phí kì 3 là bao nhiêu?",
                         "Học phí kỳ tám là bao nhiêu?", "Học phí tiếng Anh là bao nhiêu?",
                         "Tổng học phí của tôi là bao nhiêu?", "Em xem học phí ở đâu?",
                         "Em thanh toán học phí như thế nào?"):
            with self.subTest(question=question):
                self.client.responses.create.reset_mock()
                result = llm_client.ask_student(question, [])
                self.assertEqual(result, self.response)
                self.client.responses.create.assert_called_once()

    def test_tuition_term_reply_is_explicit_in_retrieval_and_api_input(self):
        history = [{"role": "user", "content": "Học phí của tôi là bao nhiêu?"},
                   {"role": "assistant", "content": llm_client.TUITION_CLARIFICATION}]
        for reply, term in (("3", 3), ("kì 8", 8), ("Em đang học kỳ 2", 2), ("tiếng Anh", 0)):
            with self.subTest(reply=reply), patch.object(llm_client, "retrieve_faq", return_value=(HITS, True)) as retrieve:
                llm_client.ask_student(reply, history)
                self.assertIn(f"kỳ {term}", retrieve.call_args.args[0])
                sent = self.client.responses.create.call_args.kwargs["input"][-1]["content"]
                self.assertIn(f"kỳ {term}", sent)

    def test_bare_number_after_other_topic_is_not_a_tuition_reply(self):
        llm_client.ask_student("3", [{"role": "assistant", "content": "Bạn muốn đăng ký mấy môn?"}])
        sent = self.client.responses.create.call_args.kwargs["input"][-1]["content"]
        self.assertEqual(sent, "3")

    def test_no_match_returns_exact_fallback_without_llm(self):
        stats, events = {}, []
        with patch.object(llm_client, "retrieve_faq", return_value=(HITS, False)):
            result = llm_client.ask_student("Không liên quan", [], request_stats=stats,
                on_sources=lambda *args: events.append("sources"), on_delta=lambda text: events.append(text))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["answer"], llm_client.UNKNOWN_ANSWER)
        self.assertEqual(events, ["sources", llm_client.UNKNOWN_ANSWER])
        self.assertEqual(stats["input_tokens"], 0)
        self.client.responses.create.assert_not_called()

    def test_model_unknown_is_normalized(self):
        self.client.responses.create.return_value.output_text = json.dumps(dict(self.response, status="unknown", answer="Không rõ"))
        self.assertEqual(llm_client.ask_student("Hạn cụ thể?", [])["answer"], llm_client.UNKNOWN_ANSWER)

    def test_connection_error_is_safe(self):
        self.client.responses.create.side_effect = APIConnectionError(message="private", request=Mock())
        with self.assertRaisesRegex(llm_client.HelpdeskError, "Không kết nối được"):
            llm_client.ask_student("Câu hỏi", [])

    def test_missing_config_and_long_input(self):
        for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
            with self.subTest(name=name), patch.dict("os.environ", {name: ""}):
                with self.assertRaisesRegex(llm_client.HelpdeskError, name):
                    llm_client.ask_student("Câu hỏi", [])
        with self.assertRaisesRegex(llm_client.HelpdeskError, "16.000"):
            llm_client.ask_student("x" * 16001, [])
        self.client.responses.create.assert_not_called()

    def test_cache_context_and_expiry(self):
        cache = {}
        llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 1)
        llm_client.ask_student("Câu hỏi", [{"role": "user", "content": "Câu trước"}], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 2)
        with patch.object(llm_client.time, "monotonic", return_value=max(v[0] for v in cache.values()) + 301):
            llm_client.ask_student("Câu hỏi", [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 3)

    def test_empty_incomplete_and_invalid_json_not_cached(self):
        for response in (SimpleNamespace(output_text=" "), SimpleNamespace(output_text="Bị cắt", status="incomplete")):
            cache = {}
            self.client.responses.create.return_value = response
            with self.assertRaises(llm_client.HelpdeskError):
                llm_client.ask_student("Câu hỏi", [], response_cache=cache)
            self.assertEqual(cache, {})
        self.client.responses.create.return_value = SimpleNamespace(output_text="Sai JSON")
        cache = {}
        self.assertEqual(llm_client.ask_student("Câu hỏi", [], response_cache=cache)["status"], "error")
        self.assertEqual(cache, {})

    def test_document_cache_reloads_after_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "faq.md"
            path.write_text("Nội dung đầu", encoding="utf-8")
            self.assertEqual(llm_client._read_text(path), "Nội dung đầu")
            path.write_text("Nội dung đã cập nhật", encoding="utf-8")
            self.assertEqual(llm_client._read_text(path), "Nội dung đã cập nhật")

    def test_smalltalk_avoids_both_retrieval_and_api_but_real_question_does_not(self):
        for question in ("Xin chào!", "cảm ơn bạn", "Bạn làm được gì?"):
            with self.subTest(question=question), patch.object(llm_client, "retrieve_faq") as retrieve:
                stats, chunks = {}, []
                result = llm_client.ask_student(question, [], request_stats=stats, on_delta=chunks.append)
                self.assertEqual(result["status"], "answered")
                self.assertEqual(stats["source"], "local")
                self.assertEqual(stats["input_tokens"], 0)
                self.assertEqual(chunks, [result["answer"]])
                retrieve.assert_not_called()
        self.client.responses.create.assert_not_called()
        llm_client.ask_student("Xin chào, em xin giấy xác nhận ở đâu?", [])
        self.client.responses.create.assert_called_once()

    def test_consecutive_repeat_reuses_answer_but_source_changes_invalidate_it(self):
        cache = {}
        question = "Em đăng ký môn ở đâu?"
        result = llm_client.ask_student(question, [], response_cache=cache)
        history = [{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"]}]
        stats = {}
        llm_client.ask_student(question, history, response_cache=cache, request_stats=stats)
        self.client.responses.create.assert_called_once()
        self.assertEqual(stats["source"], "session_cache")
        changed = [dict(HITS[0], answer="Chính sách đã thay đổi"), *HITS[1:]]
        with patch.object(llm_client, "retrieve_faq", return_value=(changed, True)):
            llm_client.ask_student(question, history, response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_semester_words_and_previous_explicit_personal_term(self):
        history = [{"role": "user", "content": "Học phí của tôi là bao nhiêu?"},
                   {"role": "assistant", "content": llm_client.TUITION_CLARIFICATION}]
        for reply, term in (("kỳ ba", 3), ("học kỳ thứ tám", 8), ("hai", 2), ("Em đang học kỳ3", 3)):
            with self.subTest(reply=reply):
                llm_client.ask_student(reply, history)
                self.assertIn(f"kỳ {term}", self.client.responses.create.call_args.kwargs["input"][-1]["content"])
        personal = [{"role": "user", "content": "Em đang học kỳ 4"}, {"role": "assistant", "content": "Bạn muốn biết gì?"}]
        llm_client.ask_student("Học phí của tôi bao nhiêu?", personal)
        self.assertIn("kỳ 4", self.client.responses.create.call_args.kwargs["input"][-1]["content"])

    def test_sdk_connection_pool_is_reused_and_configuration_changes_separate_clients(self):
        with patch.object(llm_client, "OpenAI", return_value=self.client) as factory:
            llm_client.ask_student("Đăng ký môn?", [])
            llm_client.ask_student("Giấy xác nhận?", [])
            factory.assert_called_once()
            with patch.dict("os.environ", {"OPENAI_BASE_URL": "https://example.com/v1"}):
                llm_client.ask_student("Giấy xác nhận?", [])
            self.assertEqual(factory.call_count, 2)
