import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import llm_client
import retrieval


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        retrieval._index.cache_clear()
        retrieval._query_vector.cache_clear()
    def test_markdown_preserves_complete_answer_and_group(self):
        text = "# FAQ\n## Học phí\n### Thanh toán?\nBước 1\n\n|a|b|\n|1|2|\n### Công nợ?\nLiên hệ\n## Học tập\n### Đăng ký?\nMở cổng"
        entries = retrieval.parse_faq(text)
        self.assertEqual(len(entries), 3)
        self.assertIn("|1|2|", entries[0].answer)
        self.assertEqual(entries[2].section, "Học tập")

    def test_json_formats_and_invalid_entries(self):
        data = [{"question": "Q", "answer": "A"}]
        for value in (data, {"faqs": data}):
            self.assertEqual(retrieval.parse_faq(json.dumps(value), is_json=True)[0].answer, "A")
        for value in ([], {}, [{"question": "", "answer": "A"}], [{"question": "Q", "answer": 3}]):
            with self.assertRaises(retrieval.RetrievalError):
                retrieval.parse_faq(json.dumps(value), is_json=True)

    def test_cosine_ranking_top_three_threshold_and_index_reuse(self):
        entries = tuple(retrieval.FAQEntry(str(i), f"Q{i}", f"A{i}") for i in range(4))
        model = Mock()
        model.encode.side_effect = [np.array([[0., 1.], [.6, .8], [1., 0.], [.8, .6]]), np.array([1., 0.]), np.array([0., -1.])]
        retrieval._index.cache_clear()
        with patch.object(retrieval, "_model", return_value=model), patch.dict("os.environ", {"FAQ_MIN_SCORE": "0.35"}):
            hits, relevant = retrieval.search_faq("Diễn đạt khác", entries)
            self.assertEqual([h["id"] for h in hits], ["2", "3", "1"])
            self.assertTrue(relevant)
            _, relevant = retrieval.search_faq("Không liên quan", entries)
            self.assertFalse(relevant)
            self.assertEqual(model.encode.call_count, 3)
        retrieval._index.cache_clear()

    def test_json_takes_priority_and_edits_are_reloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            md, js = Path(folder) / "faq.md", Path(folder) / "faq.json"
            md.write_text("### Q\nA", encoding="utf-8")
            with patch.object(llm_client, "FAQ_PATH", md), patch.object(llm_client, "FAQ_JSON_PATH", js), patch.object(llm_client, "search_faq", return_value=([], False)) as search:
                llm_client.retrieve_faq("Q", [])
                self.assertEqual(search.call_args.args[1][0].answer, "A")
                js.write_text('[{"question":"New","answer":"Updated"}]', encoding="utf-8")
                llm_client.retrieve_faq("Q", [])
                self.assertEqual(search.call_args.args[1][0].answer, "Updated")

    def test_followup_query_uses_last_user_context_only(self):
        with patch.object(llm_client, "search_faq", return_value=([], True)) as search:
            llm_client.retrieve_faq("Còn hạn thì sao?", [{"role": "user", "content": "Em đóng học phí thế nào?"}, {"role": "assistant", "content": "Không phải truy vấn"}])
        self.assertIn("học phí", search.call_args.args[0])
        self.assertNotIn("Không phải truy vấn", search.call_args.args[0])

    def test_query_cache_reuses_encoding_and_updated_faq_rebuilds_index(self):
        entries = (retrieval.FAQEntry("1", "Học phí?", "Câu trả lời"),)
        changed = (retrieval.FAQEntry("1", "Học phí?", "Chính sách mới"),)
        model = Mock()
        model.encode.side_effect = [np.array([[1., 0.]]), np.array([1., 0.]), np.array([[1., 0.]])]
        with patch.object(retrieval, "_model", return_value=model):
            retrieval.search_faq("Mức học phí", entries)
            retrieval.search_faq("Mức học phí", entries)
            hits, _ = retrieval.search_faq("Mức học phí", changed)
        self.assertEqual(model.encode.call_count, 3)
        self.assertEqual(hits[0]["answer"], "Chính sách mới")

    def test_exact_unaccented_title_wins_and_weak_sources_are_excluded(self):
        entries = (retrieval.FAQEntry("1", "1. Tôi đăng ký học phần ở đâu?", "Đăng ký trên cổng"),
                   retrieval.FAQEntry("2", "Xin giấy xác nhận?", "Xin giấy"),
                   retrieval.FAQEntry("3", "Môn học không hiện?", "Liên hệ đào tạo"))
        with patch.object(retrieval, "_index", return_value=np.array([[.2, 0.], [.1, 0.], [.5, 0.]])), \
             patch.object(retrieval, "_query_vector", return_value=np.array([1., 0.])), \
             patch.dict("os.environ", {"FAQ_MIN_SCORE": "0.35"}):
            hits, relevant = retrieval.search_faq("toi dang ky hoc phan o dau", entries)
        self.assertTrue(relevant)
        self.assertEqual(hits[0]["id"], "1")
        self.assertEqual(hits[0]["score"], 1.)
        self.assertNotIn("2", [h["id"] for h in hits])

    def test_followup_crosses_short_reply_but_new_explicit_topic_does_not_inherit(self):
        history = [{"role": "user", "content": "Học phí của tôi là bao nhiêu?"},
                   {"role": "assistant", "content": llm_client.TUITION_CLARIFICATION},
                   {"role": "user", "content": "3"}, {"role": "assistant", "content": "Mức học phí"}]
        self.assertIn("Học phí", llm_client._retrieval_query("Giải thích thêm", history))
        question = "Còn giấy xác nhận sinh viên thì sao?"
        self.assertEqual(llm_client._retrieval_query(question, history), question)

    def test_certificate_expansion_only_applies_to_student_enrollment(self):
        expanded = retrieval._expanded_query("Em xin giấy chứng nhận đang học ở trường")
        self.assertIn("giấy xác nhận sinh viên", expanded)
        unrelated = "Giấy chứng nhận tốt nghiệp cấp khi nào?"
        self.assertEqual(retrieval._expanded_query(unrelated), unrelated)

    def test_demo_header_is_carried_into_context_but_official_data_is_not_labeled(self):
        hits = [{"id": "1", "question": "Q", "answer": "A", "score": .9}]
        for prefix, expected in (("> **Dữ liệu giả lập dùng để demo.**\n", True), ("# Thông tin chính thức\n", False)):
            with self.subTest(expected=expected), patch.object(llm_client, "FAQ_JSON_PATH", Path("missing-demo-check.json")), \
                 patch.object(llm_client, "_read_text", return_value=prefix + "## Nhóm\n### Q\nA"), \
                 patch.object(llm_client, "search_faq", return_value=(hits, True)):
                found, _ = llm_client.retrieve_faq("Q", [])
                self.assertEqual(bool(found[0].get("source_is_demo")), expected)
                self.assertEqual("Dữ liệu giả lập" in llm_client.format_faq(found), expected)
