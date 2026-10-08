"""OpenAI/Ollama integration with shared context optimization and session cache."""

from __future__ import annotations

import os
import hashlib
import json
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Sequence
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)


PROJECT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = PROJECT_DIR / "system_prompt.txt"
FAQ_PATH = PROJECT_DIR / "faq.md"
MAX_QUESTION_CHARS = 2_000
MAX_HISTORY_PAIRS = 5
MAX_HISTORY_MESSAGES = MAX_HISTORY_PAIRS * 2
MAX_OUTPUT_TOKENS = 600
SINGLE_TOPIC_OUTPUT_TOKENS = 450
RESPONSE_CACHE_TTL = 300
RESPONSE_CACHE_SIZE = 32
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

load_dotenv(PROJECT_DIR / ".env")

# Conservative local routing: unknown wording/layout always keeps the full FAQ.
TOPIC_TERMS = {
    "hoc phi": ("hoc phi", "cong no", "thanh toan", "dong tien", "bien nhan", "ma giao dich"),
    "dang ky mon": ("dang ky mon", "dang ky hoc phan", "hoc phan", "thoi khoa bieu", "lich hoc", "trung lich", "nham lop", "phong dao tao"),
    "ho tro sinh vien": ("giay xac nhan", "dich vu sinh vien", "ho tro sinh vien", "thu tuc sinh vien", "hotro", "phong 101"),
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _topics(text: str) -> set[str]:
    text = _normalize(text)
    return {topic for topic, terms in TOPIC_TERMS.items()
            if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) for term in terms)}


@lru_cache(maxsize=8)
def _read_text_cached(path: str, modified_ns: int, size: int) -> str:
    # Cache is invalidated by file metadata, so edited FAQ/prompt take effect.
    return Path(path).read_text(encoding="utf-8-sig").strip()


def _read_text(path: Path) -> str:
    info = path.stat()
    return _read_text_cached(str(path), info.st_mtime_ns, info.st_size)


def select_history(question: str, history: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    recent = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-MAX_HISTORY_MESSAGES:]
        if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)
    ]
    topics = _topics(question)
    # Only prune explicitly independent lookup questions; ambiguous follow-ups
    # (including questions referring to earlier answers) keep all recent context.
    independent = bool(re.search(r"\b(o dau|nhu the nao|bang cach nao)\b", _normalize(question)))
    contextual = bool(re.search(r"\b(con|do|nay|vay|tren|truoc|tiep|so sanh|ca hai)\b", _normalize(question)))
    if not topics or not independent or contextual or len(recent) % 2:
        return recent
    # Repeated standalone lookup: its immediately preceding identical Q/A adds
    # no context. Removing it also lets the exact-request session cache hit.
    while len(recent) >= 2 and recent[-2] == {"role": "user", "content": question} and recent[-1]["role"] == "assistant":
        recent = recent[:-2]
    kept = []
    for i in range(0, len(recent), 2):
        user, assistant = recent[i:i + 2]
        if user["role"] != "user" or assistant["role"] != "assistant":
            return recent
        old_topics = _topics(user["content"])
        if not old_topics or old_topics & topics:
            kept.extend((user, assistant))
    return kept


def select_faq(question: str, history: Sequence[dict[str, str]]) -> tuple[str, int]:
    faq = load_faq()
    topics = _topics(question)
    if not topics:
        return faq, MAX_OUTPUT_TOKENS
    for message in history:
        topics.update(_topics(message["content"]))
    pieces = re.split(r"(?m)^## ", faq)
    sections = { _normalize(piece.splitlines()[0]): "## " + piece for piece in pieces[1:] }
    if set(sections) != set(TOPIC_TERMS):
        return faq, MAX_OUTPUT_TOKENS
    selected = [sections[name].strip() for name in sections if name in topics]
    return pieces[0].strip() + "\n\n" + "\n\n".join(selected), (
        SINGLE_TOPIC_OUTPUT_TOKENS if len(topics) == 1 else MAX_OUTPUT_TOKENS
    )


class HelpdeskError(Exception):
    """A concise, safe error that can be shown to the student."""


def load_faq() -> str:
    try:
        faq = _read_text(FAQ_PATH)
    except (OSError, UnicodeError) as exc:
        raise HelpdeskError("Không đọc được faq.md. Kiểm tra file FAQ trong thư mục project.") from exc
    if not faq:
        raise HelpdeskError("faq.md đang trống. Hãy thêm nội dung FAQ rồi thử lại.")
    return faq


def load_system_prompt() -> str:
    try:
        prompt = _read_text(SYSTEM_PROMPT_PATH)
    except (OSError, UnicodeError) as exc:
        raise HelpdeskError("Không đọc được system_prompt.txt trong thư mục project.") from exc
    if not prompt:
        raise HelpdeskError("system_prompt.txt đang trống. Hãy bổ sung hướng dẫn chatbot rồi thử lại.")
    return prompt


def _build_instructions(faq: str | None = None) -> str:
    return (
        f"{load_system_prompt()}\n\n"
        "<FAQ>\n"
        f"{load_faq() if faq is None else faq}\n"
        "</FAQ>"
    )


def _get_client_config() -> tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        raise HelpdeskError("Thiếu OPENAI_API_KEY. Mở file .env và thêm API key của bạn.")

    model = os.getenv("OPENAI_MODEL", "").strip()
    if not model or model == "your_model_here":
        raise HelpdeskError("Thiếu OPENAI_MODEL. Điền tên model bạn có quyền sử dụng vào file .env.")
    return api_key, model


def _get_provider_config() -> tuple[str, str, str, str]:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        key, model = _get_client_config()
        return provider, key, model, ""
    if provider != "ollama":
        raise HelpdeskError("LLM_PROVIDER phải là openai hoặc ollama trong .env.")
    base = os.getenv("OLLAMA_BASE_URL", "https://ollama.com").strip().rstrip("/")
    url = urlsplit(base)
    local = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username
            or url.password or url.query or url.fragment or url.path not in {"", "/api"}
            or (url.scheme == "http" and not local)):
        raise HelpdeskError("OLLAMA_BASE_URL phải là URL HTTPS hoặc http://localhost:11434, không chứa key.")
    if base.endswith("/api"):
        base = base[:-4]
    key = os.getenv("OLLAMA_API_KEY", "").strip()
    if key == "your_ollama_api_key_here":
        key = ""
    if not local and not key:
        raise HelpdeskError("Thiếu OLLAMA_API_KEY. Mở .env và thêm key Ollama của bạn.")
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not model or model == "your_model_here":
        raise HelpdeskError("Thiếu OLLAMA_MODEL. Điền tên model Ollama trong .env.")
    return provider, key, model, base


def _ask_ollama(base: str, key: str, model: str, instructions: str,
                messages: list[dict[str, str]], output_limit: int) -> SimpleNamespace:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        response = httpx.post(
            f"{base}/api/chat", headers=headers,
            json={"model": model, "messages": [{"role": "system", "content": instructions}, *messages],
                  "stream": False, "options": {"num_predict": output_limit}},
            timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise HelpdeskError("Ollama hết thời gian chờ. Kiểm tra mạng hoặc model rồi thử lại.") from exc
    except httpx.RequestError as exc:
        raise HelpdeskError("Không kết nối được Ollama. Kiểm tra OLLAMA_BASE_URL và kết nối mạng.") from exc
    if response.status_code in {401, 403}:
        raise HelpdeskError("Key Ollama không hợp lệ hoặc không có quyền dùng model. Kiểm tra .env.")
    if response.status_code == 404:
        raise HelpdeskError("Không tìm thấy model hoặc endpoint Ollama. Kiểm tra OLLAMA_MODEL và OLLAMA_BASE_URL.")
    if response.status_code == 429:
        raise HelpdeskError("Ollama đang giới hạn yêu cầu hoặc quota. Vui lòng thử lại sau.")
    if response.status_code != 200:
        raise HelpdeskError(f"Ollama không xử lý được yêu cầu (HTTP {response.status_code}). Kiểm tra model hoặc thử lại sau.")
    try:
        data = response.json()
        content = data["message"]["content"]
        if not isinstance(content, str) or data.get("error"):
            raise ValueError("Invalid Ollama response")
    except (ValueError, KeyError, TypeError) as exc:
        raise HelpdeskError("Ollama trả về dữ liệu không hợp lệ. Hãy thử lại.") from exc
    return SimpleNamespace(output_text=content, status=(
        "completed" if data.get("done") is True and data.get("done_reason") != "length" else "incomplete"
    ))


def _format_api_error(exc: Exception) -> HelpdeskError:
    if isinstance(exc, AuthenticationError):
        return HelpdeskError("API key không hợp lệ hoặc không có quyền truy cập. Kiểm tra OPENAI_API_KEY trong .env.")
    if isinstance(exc, NotFoundError):
        return HelpdeskError("Không tìm thấy model. Kiểm tra tên OPENAI_MODEL và quyền truy cập model.")
    if isinstance(exc, APITimeoutError):
        return HelpdeskError("Yêu cầu hết thời gian chờ. Kiểm tra kết nối Internet rồi thử lại.")
    if isinstance(exc, APIConnectionError):
        return HelpdeskError("Không kết nối được OpenAI API. Kiểm tra Internet rồi thử lại.")
    if isinstance(exc, RateLimitError):
        code = str(getattr(exc, "code", "") or "").lower()
        if code in {"insufficient_quota", "billing_hard_limit_reached"}:
            return HelpdeskError("Tài khoản API đã hết quota hoặc hạn mức thanh toán.")
        return HelpdeskError("OpenAI API đang giới hạn tốc độ yêu cầu. Vui lòng đợi một chút rồi thử lại.")
    if isinstance(exc, BadRequestError):
        return HelpdeskError("OpenAI API từ chối yêu cầu. Kiểm tra model và cấu hình trong file .env.")
    if isinstance(exc, APIStatusError):
        return HelpdeskError(f"OpenAI API tạm thời gặp lỗi (HTTP {exc.status_code}). Vui lòng thử lại sau.")
    return HelpdeskError("Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau.")


def ask_student(question: str, history: Sequence[dict[str, str]], *, response_cache: dict | None = None) -> str:
    """Ask using relevant FAQ/context; optionally reuse a session-local answer."""
    question = question.strip()
    if not question:
        raise HelpdeskError("Vui lòng nhập câu hỏi trước khi gửi.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HelpdeskError("Câu hỏi quá dài. Giới hạn là 2.000 ký tự.")

    recent_history = select_history(question, history)
    faq, output_limit = select_faq(question, recent_history)
    instructions = _build_instructions(faq)
    provider, api_key, model, base_url = _get_provider_config()
    input_messages = [*recent_history, {"role": "user", "content": question}]
    signature = json.dumps([provider, base_url, model, instructions, input_messages, output_limit,
                            hashlib.sha256(api_key.encode()).hexdigest()], ensure_ascii=False)
    cache_key = hashlib.sha256(signature.encode()).hexdigest()
    if response_cache is not None:
        now = time.monotonic()
        for key in list(response_cache):
            if now - response_cache[key][0] >= RESPONSE_CACHE_TTL:
                del response_cache[key]
        if cache_key in response_cache:
            return response_cache[cache_key][1]

    try:
        if provider == "ollama":
            response = _ask_ollama(base_url, api_key, model, instructions, input_messages, output_limit)
        else:
            client = OpenAI(
                api_key=api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=input_messages,
                max_output_tokens=output_limit,
                store=False,
            )
    except (
        AuthenticationError,
        NotFoundError,
        APITimeoutError,
        APIConnectionError,
        RateLimitError,
        BadRequestError,
        APIStatusError,
    ) as exc:
        raise _format_api_error(exc) from exc

    if getattr(response, "status", None) == "incomplete":
        raise HelpdeskError("API chưa hoàn thành câu trả lời. Hãy chia câu hỏi thành từng phần rồi thử lại.")
    answer = (response.output_text or "").strip()
    if not answer:
        raise HelpdeskError(f"{provider.title()} API trả về nội dung rỗng. Hãy thử gửi lại câu hỏi.")
    if response_cache is not None:
        while len(response_cache) >= RESPONSE_CACHE_SIZE:
            del response_cache[next(iter(response_cache))]
        response_cache[cache_key] = (time.monotonic(), answer)
    return answer
