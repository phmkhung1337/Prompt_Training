import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api_budget import Budget, output_limit
import llm_client


class BudgetTests(unittest.TestCase):
    def setUp(self):
        llm_client._openai_client.cache_clear()
        retrieval = patch.object(llm_client, 'retrieve_faq', return_value=([
            {'id': '1', 'question': 'Học phí?', 'answer': 'Đáp án FAQ', 'section': 'Học phí', 'score': .9}
        ], True))
        retrieval.start()
        self.addCleanup(retrieval.stop)
        env = patch.dict('os.environ', {
            'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test',
            'LLM_MAX_HISTORY_PAIRS': '12', 'LLM_INPUT_BUDGET': '6000',
            'LLM_OUTPUT_SHORT': '350', 'LLM_OUTPUT_NORMAL': '600',
            'LLM_OUTPUT_DETAILED': '1400', 'LLM_TIMEOUT_SECONDS': '60',
        })
        env.start()
        self.addCleanup(env.stop)
        client = patch.object(llm_client, 'OpenAI')
        self.client = client.start().return_value
        self.addCleanup(client.stop)
        self.client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps({'answer': 'Đáp án', 'category': 'other', 'status': 'answered'}),
            usage=SimpleNamespace(input_tokens=123, output_tokens=45,
                                  input_tokens_details=SimpleNamespace(cached_tokens=64)),
        )

    def test_adaptive_output_levels(self):
        cfg = Budget.from_env()
        self.assertEqual(output_limit('tom tat ngan gon', 600, cfg), 350)
        self.assertEqual(output_limit('hoc phi o dau', 450, cfg), 450)
        self.assertEqual(output_limit('viet code va phan tich chi tiet', 900, cfg), 1400)

    def test_real_usage_and_cache_dont_confuse_estimates(self):
        stats, cache = {}, {}
        llm_client.ask_student('Giải thích Python', [], response_cache=cache, request_stats=stats)
        self.assertEqual(stats['input_tokens'], 123)
        self.assertEqual(stats['output_tokens'], 45)
        self.assertEqual(stats['cached_input_tokens'], 64)
        self.assertGreater(stats['estimated_input_tokens'], 0)
        llm_client.ask_student('Giải thích Python', [], response_cache=cache, request_stats=stats)
        self.assertEqual(stats['source'], 'session_cache')
        self.assertEqual(stats['input_tokens'], 0)
        self.client.responses.create.assert_called_once()

    def test_budget_removes_old_pairs_but_preserves_latest(self):
        history = []
        for i in range(12):
            history.extend([{'role': 'user', 'content': f'Câu {i}: ' + 'x' * 2000},
                            {'role': 'assistant', 'content': 'y' * 2000}])
        stats = {}
        llm_client.ask_student('Câu tiếp theo', history, request_stats=stats)
        sent = self.client.responses.create.call_args.kwargs['input']
        self.assertLess(stats['history_messages'], 24)
        self.assertLessEqual(stats['estimated_input_tokens'], 6000)
        self.assertEqual(sent[-3]['content'], history[-2]['content'])
        self.assertEqual((len(sent) - 1) % 2, 0)
        self.assertIn('lịch sử cũ đã được bỏ', self.client.responses.create.call_args.kwargs['instructions'])

    def test_endpoint_change_invalidates_cache(self):
        cache = {}
        llm_client.ask_student('Giải thích Python', [], response_cache=cache)
        with patch.dict('os.environ', {'OPENAI_BASE_URL': 'https://example.com/v1'}):
            llm_client.ask_student('Giải thích Python', [], response_cache=cache)
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_current_question_is_not_silently_truncated(self):
        with patch.dict('os.environ', {'LLM_INPUT_BUDGET': '1500'}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, 'ngân sách đầu vào'):
                llm_client.ask_student('ư' * 7900, [])
        self.client.responses.create.assert_not_called()

    def test_invalid_configuration_fails_before_api(self):
        with patch.dict('os.environ', {'LLM_OUTPUT_SHORT': '2000'}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, 'SHORT'):
                llm_client.ask_student('Câu hỏi', [])
        self.client.responses.create.assert_not_called()

    def test_profile_and_style_are_sent_and_invalidate_cache(self):
        cache, stats = {}, {}
        llm_client.ask_student('Giải thích Python', [], response_cache=cache, request_stats=stats,
                              student_profile='Mới bắt đầu, có 1 giờ/ngày', answer_style='short')
        sent = self.client.responses.create.call_args.kwargs
        self.assertIn('1 giờ/ngày', sent['input'][0]['content'])
        self.assertEqual(sent['max_output_tokens'], 350)
        llm_client.ask_student('Giải thích Python', [], response_cache=cache, student_profile='Đã học 2 năm', answer_style='detailed')
        self.assertEqual(self.client.responses.create.call_count, 2)
        self.assertEqual(self.client.responses.create.call_args.kwargs['max_output_tokens'], 1400)

    def test_old_history_setting_is_capped_and_long_question_supported(self):
        history = []
        for i in range(25):
            history.extend([{'role': 'user', 'content': f'Câu {i}'},
                            {'role': 'assistant', 'content': f'Trả lời {i}'}])
        with patch.dict('os.environ', {'LLM_MAX_HISTORY_PAIRS': '24', 'LLM_INPUT_BUDGET': '12000'}):
            stats = {}
            llm_client.ask_student('Giải thích ' + 'x' * 9000, history, request_stats=stats)
        self.assertEqual(stats['history_messages'], 10)
        self.assertEqual(self.client.responses.create.call_args.kwargs['input'][0]['content'], 'Câu 20')

    def test_oversized_secondary_sources_are_dropped_and_ui_matches_sent_context(self):
        hits = [{'id': str(i), 'question': f'Nguồn {i}', 'answer': 'x' * (80 if i == 0 else 2400),
                 'section': '', 'score': .9 - i * .1} for i in range(3)]
        displayed, stats = [], {}
        with patch.dict('os.environ', {'LLM_INPUT_BUDGET': '1500'}), patch.object(llm_client, 'retrieve_faq', return_value=(hits, True)):
            llm_client.ask_student('Câu hỏi', [], request_stats=stats, on_sources=lambda found, _: displayed.extend(found))
        self.assertEqual(displayed, hits[:1])
        self.assertEqual(stats['sources_count'], 1)
        self.assertEqual(stats['dropped_sources'], 2)
        self.assertLessEqual(stats['estimated_input_tokens'], 1500)
