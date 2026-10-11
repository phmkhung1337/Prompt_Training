"""Cached multilingual embeddings with lexical reranking and source filtering."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TOP_K = 3
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class RetrievalError(Exception):
    pass


@dataclass(frozen=True)
class FAQEntry:
    id: str
    question: str
    answer: str
    section: str = ""


@lru_cache(maxsize=16)
def parse_faq(text: str, *, is_json: bool = False) -> tuple[FAQEntry, ...]:
    if is_json:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = data["faqs"]
            if not isinstance(data, list) or not data:
                raise ValueError()
            entries = []
            for i, item in enumerate(data, 1):
                q, a = item["question"], item["answer"]
                if not isinstance(q, str) or not isinstance(a, str) or not q.strip() or not a.strip():
                    raise ValueError()
                entries.append(FAQEntry(str(item.get("id", i)), q.strip(), a.strip(), str(item.get("category", ""))))
            return tuple(entries)
        except (ValueError, KeyError, TypeError) as exc:
            raise RetrievalError("faq.json cần là danh sách question/answer không rỗng (hoặc object có khóa faqs).") from exc
    entries, section = [], ""
    # Preserve each complete answer, including tables and multiline content.
    for block in re.split(r"(?m)^(?=## )", text):
        if block.startswith("## "):
            section = block.splitlines()[0][3:].strip()
        for match in re.finditer(r"(?ms)^### (.+?)\n(.*?)(?=^### |\Z)", block):
            question, answer = match.group(1).strip(), match.group(2).strip()
            if question and answer:
                entries.append(FAQEntry(str(len(entries) + 1), question, answer, section))
    if not entries:
        raise RetrievalError("faq.md cần các mục ### Câu hỏi, theo sau là câu trả lời; hoặc thêm faq.json.")
    return tuple(entries)


@lru_cache(maxsize=2)
def _model(name: str):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(name, device="cpu", cache_folder=str(Path(__file__).parent / ".cache" / "embeddings"))
    except ImportError as exc:
        raise RetrievalError("Thiếu thư viện embeddings. Chạy python -m pip install -r requirements.txt.") from exc
    except Exception as exc:
        raise RetrievalError("Không tải được model embeddings. Kiểm tra mạng ở lần chạy đầu hoặc FAQ_EMBEDDING_MODEL trong .env.") from exc


@lru_cache(maxsize=4)
def _index(entries: tuple[FAQEntry, ...], model_name: str):
    # The question and group describe the intent; a short answer prefix adds terms.
    texts = [f"{e.section}: {e.question}\n{e.answer[:600]}" for e in entries]
    return _model(model_name).encode(texts, normalize_embeddings=True, show_progress_bar=False)


@lru_cache(maxsize=256)
def _query_vector(question: str, model_name: str):
    return _model(model_name).encode(question, normalize_embeddings=True, show_progress_bar=False)


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", text))


_STOPWORDS = frozenset("toi em minh ban cua la co the lam the nao gi o dau xin cho hoi va thi sao nhe a".split())


def _expanded_query(question: str) -> str:
    normalized = _normalized(question)
    # Enrollment certificates are commonly described without the FAQ's exact term.
    if "giay chung nhan" in normalized and re.search(r"\bdang hoc\b|\bsinh vien\b", normalized):
        return "Tôi xin giấy xác nhận sinh viên ở đâu?\n" + question
    return question


@lru_cache(maxsize=4)
def _lexical_index(entries: tuple[FAQEntry, ...]):
    documents = [frozenset(_normalized(f"{e.section} {e.question}").split()) - _STOPWORDS for e in entries]
    frequencies = {word: sum(word in doc for doc in documents) for doc in documents for word in doc}
    weights = {word: math.log(1 + len(entries) / count) for word, count in frequencies.items()}
    questions = [_normalized(re.sub(r"^\d+[.)]\s*", "", e.question)) for e in entries]
    return documents, weights, questions


def search_faq(question: str, entries: tuple[FAQEntry, ...]) -> tuple[list[dict], bool]:
    model_name = os.getenv("FAQ_EMBEDDING_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        threshold = float(os.getenv("FAQ_MIN_SCORE", "0.35"))
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError()
    except ValueError as exc:
        raise RetrievalError("FAQ_MIN_SCORE phải là số từ 0 đến 1.") from exc
    try:
        vectors = _index(entries, model_name)
        expanded = _expanded_query(question)
        query_text = " ".join(expanded.split()).lower()
        query = _query_vector(query_text, model_name)
        cosine = vectors @ query
        if not all(math.isfinite(float(value)) for value in cosine):
            raise ValueError("Invalid embedding score")
        documents, weights, questions = _lexical_index(entries)
        normalized = _normalized(question)
        words = frozenset(_normalized(expanded).split()) - _STOPWORDS
        total_weight = sum(weights.get(word, math.log(1 + len(entries))) for word in words)
        scores = []
        for i, value in enumerate(cosine):
            lexical = sum(weights.get(word, 0) for word in words & documents[i]) / total_weight if total_weight else 0
            semantic = max(-1., min(1., float(value)))
            # A modest lexical boost preserves semantic paraphrases. Exact FAQ titles win.
            scores.append(1. if normalized == questions[i] else semantic + .12 * lexical * (1 - max(0., semantic)))
        ranked = sorted(range(len(entries)), key=lambda i: (-float(scores[i]), i))[:TOP_K]
        exact = [i for i in ranked if normalized == questions[i]]
        if exact:
            ranked = exact
        ranked = [i for i in ranked if float(scores[i]) >= threshold]
        hits = [{"id": entries[i].id, "question": entries[i].question,
                 "answer": entries[i].answer, "section": entries[i].section,
                 "score": round(float(scores[i]), 4),
                 "semantic_score": round(float(cosine[i]), 4)} for i in ranked]
        return hits, bool(hits)
    except RetrievalError:
        raise
    except Exception as exc:
        raise RetrievalError("Không tính được embeddings FAQ. Kiểm tra model và dữ liệu FAQ.") from exc
