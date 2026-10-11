"""Shared response schema and strict validation for all LLM providers."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class HelpdeskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str
    category: Literal["concept", "programming", "study_planning", "study_skills", "career_guidance", "other"]
    status: Literal["answered", "unknown", "clarify", "out_of_scope", "error"]

    @field_validator("answer")
    @classmethod
    def nonempty_answer(cls, value: str) -> str:
        if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("answer contains unsupported control characters")
        value = value.strip()
        if not value or len(value) > 32000:
            raise ValueError("answer must contain 1–32000 characters")
        return value


RESPONSE_SCHEMA = HelpdeskResponse.model_json_schema()
JSON_INSTRUCTIONS = (
    'Chỉ trả một JSON object, không có văn bản bên ngoài JSON. Ví dụ hợp lệ: '
    '{"answer":"Đạo hàm của x^2 là 2x.","category":"concept","status":"answered"}. '
    'Chọn một giá trị enum: concept=kiến thức/bài tập, programming=lập trình, '
    'study_planning=kế hoạch/ôn thi, study_skills=kỹ năng học, career_guidance=định hướng, other=khác; answered=đã trả lời, '
    'unknown=không đủ dữ kiện đáng tin để trả lời, clarify=cần hỏi lại, out_of_scope=không thể hỗ trợ. '
    'Có thể trả answered cho kiến thức học tập dù không có trong tài liệu. '
    'Không thêm trường; không tự trả status=error. '
    'Trong answer có thể dùng Markdown/code; ưu tiên công thức Unicode hoặc văn bản thường. '
    'Escape JSON đúng một lần. Mẫu có xuống dòng và code (giữ cách escape như mẫu): '
    + json.dumps({"answer": 'Ví dụ:\n```python\nfor i in range(3):\n    print("Số", i)\n```',
                  "category": "programming", "status": "answered"}, ensure_ascii=False)
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _normalize_string_escapes(raw: str) -> str:
    """Losslessly quote invalid backslash escapes/control chars inside JSON strings.

    No fields, values, delimiters or missing closing quotes are invented. The
    resulting document must still pass JSON parsing and the full strict schema.
    """
    output = []
    in_string = False
    i = 0
    while i < len(raw):
        char = raw[i]
        if char == '"':
            in_string = not in_string
        elif in_string and char == "\\" and i + 1 < len(raw):
            following = raw[i + 1]
            if following in '"\\/bfnrtu':
                output.extend((char, following))
                i += 2
                continue
            output.append("\\")
        elif in_string and ord(char) < 32:
            output.append(json.dumps(char)[1:-1])
            i += 1
            continue
        output.append(char)
        i += 1
    return "".join(output)


def validate_response(raw: str, *, validation_info: dict | None = None) -> dict[str, str]:
    """Parse strict JSON; normalize only string escapes, then validate the schema."""
    if validation_info is not None:
        validation_info["json_normalized"] = False
    raw = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    try:
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except json.JSONDecodeError:
            normalized = _normalize_string_escapes(raw)
            if normalized == raw:
                raise
            data = json.loads(normalized, object_pairs_hook=_unique_object)
            if validation_info is not None:
                validation_info["json_normalized"] = True
        result = HelpdeskResponse.model_validate(data)
        if result.status == "error":
            raise ValueError("Model cannot supply an application error")
        return result.model_dump()
    except (ValueError, TypeError, ValidationError):
        return HelpdeskResponse(
            answer="Phản hồi AI không đúng cấu trúc JSON yêu cầu. Bạn hãy thử gửi lại câu hỏi.",
            category="other", status="error",
        ).model_dump()
