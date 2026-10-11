"""Shared response schema and strict validation for all LLM providers."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class HelpdeskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str
    category: Literal["tuition", "course_registration", "student_services", "other"]
    status: Literal["answered", "unknown", "clarify", "out_of_scope", "error"]

    @field_validator("answer")
    @classmethod
    def nonempty_answer(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 32000:
            raise ValueError("answer must contain 1–32000 characters")
        return value


RESPONSE_SCHEMA = HelpdeskResponse.model_json_schema()
JSON_INSTRUCTIONS = (
    'Chỉ trả một JSON object, không Markdown: {"answer":"câu trả lời tiếng Việt",'
    '"category":"tuition|course_registration|student_services|other",'
    '"status":"answered|unknown|clarify|out_of_scope"}. '
    'Chọn một giá trị enum: tuition=học phí, course_registration=đăng ký môn, '
    'student_services=dịch vụ sinh viên, other=khác; answered=đã trả lời, '
    'unknown=không đủ dữ kiện đáng tin để trả lời, clarify=cần hỏi lại, out_of_scope=không thể hỗ trợ. '
    'Nếu FAQ không đủ dữ kiện, trả unknown và nói: Mình chưa tìm thấy thông tin trong bộ FAQ hiện có. '
    'Không thêm trường; không tự trả status=error.'
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def validate_response(raw: str) -> dict[str, str]:
    """Accept a JSON object (or an enclosing JSON fence), otherwise safe fallback."""
    raw = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        result = HelpdeskResponse.model_validate(data)
        if result.status == "error":
            raise ValueError("Model cannot supply an application error")
        return result.model_dump()
    except (ValueError, TypeError, ValidationError):
        return HelpdeskResponse(
            answer="Phản hồi AI không đúng cấu trúc JSON yêu cầu. Bạn hãy thử gửi lại câu hỏi.",
            category="other", status="error",
        ).model_dump()
