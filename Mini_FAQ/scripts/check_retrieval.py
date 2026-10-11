"""Offline smoke evaluation of the current FAQ and locally cached embeddings."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import llm_client
import retrieval


CASES = (
    ("Học phí kỳ 3 là bao nhiêu?", {"4", "5"}),
    ("Em chuyển khoản rồi nhưng vẫn báo còn nợ", {"3"}),
    ("toi dang ky hoc phan o dau", {"6"}),
    ("Em xin giấy chứng nhận đang học ở trường", {"11"}),
    ("Quỹ khởi nghiệp hỗ trợ bao nhiêu tiền?", {"14"}),
    ("Chuyển lớp có mất phí không?", {"22"}),
)


def main():
    rows = []
    for question, expected in CASES:
        started = time.perf_counter()
        hits, relevant = llm_client.retrieve_faq(question, [])
        rows.append({"question": question, "ids": [h["id"] for h in hits],
                     "expected_in_top3": relevant and bool(expected & {h["id"] for h in hits}),
                     "ms": round((time.perf_counter() - started) * 1000),
                     "scores": [h["score"] for h in hits]})
    before = retrieval._query_vector.cache_info()
    llm_client.retrieve_faq(CASES[0][0], [])
    after = retrieval._query_vector.cache_info()
    report = {"cases": rows, "passed": sum(row["expected_in_top3"] for row in rows),
              "total": len(rows), "repeat_query_cache_hit": after.hits > before.hits,
              "api_calls": 0}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["total"] and report["repeat_query_cache_hit"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
