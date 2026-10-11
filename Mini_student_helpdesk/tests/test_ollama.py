import json
import unittest
from unittest.mock import patch

import httpx
import llm_client


class OllamaTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {
            'LLM_PROVIDER': 'ollama', 'OLLAMA_API_KEY': 'test-key',
            'OLLAMA_BASE_URL': 'https://ollama.com', 'OLLAMA_MODEL': 'gemma4:31b',
        })
        env.start()
        self.addCleanup(env.stop)
        post = patch.object(llm_client.httpx, 'post', return_value=httpx.Response(200, json={
            'message': {'content': json.dumps({'answer': 'Đáp án Ollama', 'category': 'concept', 'status': 'answered'})}, 'done': True, 'done_reason': 'stop',
        }))
        self.post = post.start()
        self.addCleanup(post.stop)

    def test_cloud_payload_and_cache(self):
        cache = {}
        q = 'Giải thích vòng lặp Python là gì?'
        self.assertEqual(llm_client.ask_student(q, [], response_cache=cache)['answer'], 'Đáp án Ollama')
        llm_client.ask_student(q, [], response_cache=cache)
        self.post.assert_called_once()
        call = self.post.call_args
        self.assertEqual(call.args[0], 'https://ollama.com/api/chat')
        self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer test-key')
        payload = call.kwargs['json']
        self.assertFalse(payload['stream'])
        self.assertNotIn('format', payload)
        self.assertEqual(payload['messages'][0]['role'], 'system')
        self.assertIn('FAQ', payload['messages'][0]['content'])
        self.assertEqual(payload['messages'][-1]['content'], q)
        self.assertEqual(payload['options']['num_predict'], llm_client._get_budget().normal_output)

    def test_reasoning_headroom_and_config_change_invalidate_cache(self):
        cache, stats = {}, {}
        with patch.dict('os.environ', {'OLLAMA_MODEL': 'gpt-oss:120b', 'OLLAMA_REASONING_RESERVE': '1024'}):
            llm_client.ask_student('Giải thích vòng lặp Python', [], response_cache=cache, request_stats=stats)
            self.assertEqual(stats['reasoning_reserve'], 1024)
            self.assertEqual(self.post.call_args.kwargs['json']['options']['num_predict'], stats['answer_limit'] + 1024)
            llm_client.ask_student('Giải thích vòng lặp Python', [], response_cache=cache)
            self.post.assert_called_once()
            with patch.dict('os.environ', {'OLLAMA_REASONING_RESERVE': '2048'}):
                llm_client.ask_student('Giải thích vòng lặp Python', [], response_cache=cache)
            self.assertEqual(self.post.call_count, 2)

    def test_math_escapes_are_normalized_without_another_api_call(self):
        self.post.return_value = httpx.Response(200, json={
            'message': {'content': r'{"answer":"Nguyên hàm của \(2x\) là x^2; kết quả là 9.","category":"concept","status":"answered"}'},
            'done': True, 'done_reason': 'stop',
        })
        stats = {}
        result = llm_client.ask_student('Tính tích phân 2x từ 0 đến 3', [], request_stats=stats)
        self.assertEqual(result['status'], 'answered')
        self.assertIn(r'\(2x\)', result['answer'])
        self.assertTrue(stats['json_normalized'])
        self.post.assert_called_once()

    def test_invalid_reasoning_reserve_fails_before_api_call(self):
        with patch.dict('os.environ', {'OLLAMA_REASONING_RESERVE': '-1'}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, 'OLLAMA_REASONING_RESERVE'):
                llm_client.ask_student('Giải thích Python', [])
        self.post.assert_not_called()

    def test_cloud_requires_key(self):
        with patch.dict('os.environ', {'OLLAMA_API_KEY': ''}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, 'OLLAMA_API_KEY'):
                llm_client.ask_student('Câu hỏi', [])
        self.post.assert_not_called()

    def test_local_without_key(self):
        with patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://localhost:11434/api/', 'OLLAMA_API_KEY': ''}):
            llm_client.ask_student('Câu hỏi', [])
        self.assertEqual(self.post.call_args.args[0], 'http://localhost:11434/api/chat')
        self.assertEqual(self.post.call_args.kwargs['headers'], {})
        self.assertEqual(self.post.call_args.kwargs['json']['format']['additionalProperties'], False)

    def test_http_errors_are_safe(self):
        for code in (401, 403, 404, 429, 500):
            self.post.return_value = httpx.Response(code, text='private details')
            with self.subTest(code=code), self.assertRaises(llm_client.HelpdeskError) as result:
                llm_client.ask_student('Câu hỏi', [])
            self.assertNotIn('private', str(result.exception))
            self.assertNotIn('test-key', str(result.exception))

    def test_timeout_and_bad_json(self):
        self.post.side_effect = httpx.ReadTimeout('private details')
        with self.assertRaisesRegex(llm_client.HelpdeskError, 'hết thời gian chờ'):
            llm_client.ask_student('Câu hỏi', [])
        self.post.side_effect = None
        self.post.return_value = httpx.Response(200, text='invalid json')
        with self.assertRaisesRegex(llm_client.HelpdeskError, 'không hợp lệ'):
            llm_client.ask_student('Câu hỏi', [])

    def test_incomplete_not_cached(self):
        cache = {}
        self.post.return_value = httpx.Response(200, json={
            'message': {'content': 'Bị cắt'}, 'done': True, 'done_reason': 'length',
        })
        with self.assertRaisesRegex(llm_client.HelpdeskError, 'chưa hoàn thành'):
            llm_client.ask_student('Câu hỏi', [], response_cache=cache)
        self.assertEqual(cache, {})

    def test_remote_http_rejected(self):
        with patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://ollama.com'}):
            with self.assertRaisesRegex(llm_client.HelpdeskError, 'HTTPS'):
                llm_client.ask_student('Câu hỏi', [])
        self.post.assert_not_called()
