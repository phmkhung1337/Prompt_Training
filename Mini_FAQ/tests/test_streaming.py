import json
import unittest
from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import httpx
import llm_client
from streaming import AnswerStream


class StreamingTests(unittest.TestCase):
    def test_json_chunks_escape_unicode_and_field_order(self):
        answer = 'Xin chào\n"sinh viên" \\ 🎓'
        raw = json.dumps({"category": "other", "answer": answer, "status": "answered"})
        chunks = []
        display = AnswerStream(chunks.append)
        for char in raw:
            display.feed(char)
        self.assertEqual("".join(chunks), answer)
        self.assertEqual(display.raw, raw)
        self.assertGreater(len(chunks), 1)

    def test_openai_deltas_and_completion(self):
        result = NS(output_text='{"answer":"Xin chào","category":"other","status":"answered"}', status="completed")
        events = [NS(type="response.output_text.delta", delta='{"answer":"Xin '), NS(type="response.output_text.delta", delta='chào","category":"other","status":"answered"}'), NS(type="response.completed", response=result)]
        client, chunks = Mock(), []
        client.responses.create.return_value = nullcontext(iter(events))
        self.assertIs(llm_client._stream_openai(client, {}, AnswerStream(chunks.append)), result)
        self.assertEqual(chunks, ["Xin ", "chào"])
        self.assertTrue(client.responses.create.call_args.kwargs["stream"])

    def test_ollama_stream_and_usage(self):
        lines = [json.dumps({"message": {"content": '{"answer":"Xin '}}), json.dumps({"message": {"content": 'chào","category":"other","status":"answered"}'}, "done": True, "prompt_eval_count": 12, "eval_count": 4})]
        response = Mock(status_code=200)
        response.iter_lines.return_value = iter(lines)
        chunks = []
        with patch.object(llm_client.httpx, "stream", return_value=nullcontext(response)):
            result = llm_client._stream_ollama("https://ollama.com", {}, {}, AnswerStream(chunks.append))
        self.assertEqual(chunks, ["Xin ", "chào"])
        self.assertEqual(result.usage.input_tokens, 12)
        self.assertEqual(result.status, "completed")

    def test_interrupted_stream_and_private_server_error(self):
        client = Mock()
        client.responses.create.return_value = nullcontext(iter([]))
        with self.assertRaisesRegex(llm_client.HelpdeskError, "bị ngắt"):
            llm_client._stream_openai(client, {}, AnswerStream(Mock()))
        for line in ('{"error":"secret-key"}', 'invalid-json', '{"message":{"content":"partial"}}'):
            response = Mock(status_code=200)
            response.iter_lines.return_value = iter([line])
            with patch.object(llm_client.httpx, "stream", return_value=nullcontext(response)), self.assertRaises(llm_client.HelpdeskError) as error:
                llm_client._stream_ollama("https://ollama.com", {}, {}, AnswerStream(Mock()))
            self.assertNotIn("secret-key", str(error.exception))
