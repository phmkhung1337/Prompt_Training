import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import llm_client
from response_schema import HelpdeskResponse, validate_response


class SchemaTests(unittest.TestCase):
    def setUp(self):
        llm_client._openai_client.cache_clear()

    def test_valid_and_fenced_json(self):
        payload = {"answer": "Kỳ 1: 20 triệu đồng.", "category": "tuition", "status": "answered"}
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(validate_response(raw), payload)
        self.assertEqual(validate_response('```json\n' + raw + '\n```'), payload)

    def test_invalid_responses_produce_valid_safe_fallback(self):
        invalid = [
            'not json', '[]', '{}', '{"answer":"x"}',
            '{"answer":123,"category":"tuition","status":"answered"}',
            '{"answer":" ","category":"tuition","status":"answered"}',
            '{"answer":"x","category":"invalid","status":"answered"}',
            '{"answer":"x","category":"tuition","status":"answered","extra":1}',
            '{"answer":"x","answer":"y","category":"tuition","status":"answered"}',
            '{"answer":"untrusted error","category":"other","status":"error"}',
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                result = validate_response(raw)
                self.assertEqual(result['status'], 'error')
                HelpdeskResponse.model_validate(result)
                self.assertNotIn('untrusted error', result['answer'])

    def test_invalid_json_is_not_cached_or_retried(self):
        cache = {}
        with patch.dict('os.environ', {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'test-model'}), patch.object(llm_client, 'OpenAI') as client, patch.object(llm_client, 'retrieve_faq', return_value=([{'question': 'Q', 'answer': 'A'}], True)):
            create = client.return_value.responses.create
            create.return_value = SimpleNamespace(output_text='invalid json')
            result = llm_client.ask_student('Câu hỏi', [], response_cache=cache)
            self.assertEqual(result['status'], 'error')
            self.assertEqual(cache, {})
            create.assert_called_once()
            self.assertTrue(create.call_args.kwargs['text']['format']['strict'])
