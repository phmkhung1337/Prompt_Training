import unittest
from unittest.mock import patch

import cli


class TerminalTests(unittest.TestCase):
    def test_sources_before_stream_reset_and_history_cap(self):
        seen = []

        def ask(question, history, **kwargs):
            seen.append(list(history))
            kwargs["on_sources"]([{"question": "FAQ nguồn", "answer": "Nội dung nguồn", "score": .8}], True)
            kwargs["on_delta"]("Đáp ")
            kwargs["on_delta"]("án")
            kwargs["response_cache"]["cached"] = True
            return {"answer": "Đáp án", "status": "answered"}

        questions = [f"Câu {i}" for i in range(7)] + ["/reset", "Câu mới", "/exit"]
        with patch("builtins.input", side_effect=questions), patch("builtins.print") as output, patch.object(cli.llm_client, "ask_student", side_effect=ask):
            cli.main()
        self.assertEqual(len(seen[6]), 10)
        self.assertEqual(seen[-1], [])
        texts = [str(call.args[0]) for call in output.call_args_list if call.args]
        self.assertLess(texts.index("Nội dung nguồn"), texts.index("Đáp "))
