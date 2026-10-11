import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import llm_client
from response_schema import HelpdeskResponse, validate_response


class SchemaTests(unittest.TestCase):
    def test_lossless_math_escape_normalization(self):
        raw = r'{"answer":"Đạo hàm của \(x^2\) là 2x.","category":"concept","status":"answered"}'
        info = {}
        result = validate_response(raw, validation_info=info)
        self.assertEqual(result['answer'], r'Đạo hàm của \(x^2\) là 2x.')
        self.assertEqual(result['status'], 'answered')
        self.assertTrue(info['json_normalized'])
        HelpdeskResponse.model_validate(result)

    def test_code_newlines_and_valid_escapes_are_preserved(self):
        answer = '```python\nprint("a")\nprint("b")\n```\nĐường dẫn: C:\\temp'
        payload = {'answer': answer, 'category': 'programming', 'status': 'answered'}
        info = {}
        self.assertEqual(validate_response(json.dumps(payload), validation_info=info), payload)
        self.assertFalse(info['json_normalized'])
        raw = '{"answer":"Dòng một\nDòng hai","category":"concept","status":"answered"}'
        self.assertEqual(validate_response(raw)['answer'], 'Dòng một\nDòng hai')

    def test_normalization_never_accepts_bad_schema_or_truncated_json(self):
        invalid = [
            r'{"answer":"\(x\)","category":"invalid","status":"answered"}',
            r'{"answer":"\(x\)","category":"concept","status":"answered","extra":1}',
            r'{"answer":"\(x\)","answer":"y","category":"concept","status":"answered"}',
            r'{"answer":"\(x\)","category":"concept","status":"answered"',
            r'{"answer":"\(x\)","category":"concept","status":"error"}',
            r'{"answer":"\frac{x}{y}","category":"concept","status":"answered"}',
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertEqual(validate_response(raw)['status'], 'error')

    def test_valid_and_fenced_json(self):
        payload = {"answer": "Ví dụ vòng lặp for trong Python.", "category": "concept", "status": "answered"}
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(validate_response(raw), payload)
        self.assertEqual(validate_response('```json\n' + raw + '\n```'), payload)

    def test_invalid_responses_produce_valid_safe_fallback(self):
        invalid = [
            'not json', '[]', '{}', '{"answer":"x"}',
            '{"answer":123,"category":"concept","status":"answered"}',
            '{"answer":" ","category":"concept","status":"answered"}',
            '{"answer":"x","category":"invalid","status":"answered"}',
            '{"answer":"x","category":"concept","status":"answered","extra":1}',
            '{"answer":"x","answer":"y","category":"concept","status":"answered"}',
            '{"answer":"untrusted error","category":"other","status":"error"}',
            '{"answer":"x","category":"tuition","status":"answered"}',
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                result = validate_response(raw)
                self.assertEqual(result['status'], 'error')
                HelpdeskResponse.model_validate(result)
                self.assertNotIn('untrusted error', result['answer'])

    def test_invalid_json_is_not_cached_or_retried(self):
        cache = {}
        with patch.dict('os.environ', {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'test-model'}), patch.object(llm_client, 'OpenAI') as client:
            create = client.return_value.responses.create
            create.return_value = SimpleNamespace(output_text='invalid json')
            result = llm_client.ask_student('Câu hỏi', [], response_cache=cache)
            self.assertEqual(result['status'], 'error')
            self.assertEqual(cache, {})
            create.assert_called_once()
            self.assertTrue(create.call_args.kwargs['text']['format']['strict'])
