"""Configurable request budgets; estimates are not model-tokenizer counts."""

import math
import os
from dataclasses import dataclass


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} phải là số nguyên.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} phải nằm trong khoảng {minimum}–{maximum}.")
    return value


@dataclass(frozen=True)
class Budget:
    history_pairs: int
    input_estimate: int
    short_output: int
    normal_output: int
    detailed_output: int
    timeout: int

    @classmethod
    def from_env(cls):
        cfg = cls(
            min(_integer("LLM_MAX_HISTORY_PAIRS", 5, 1, 48), 5),
            _integer("LLM_INPUT_BUDGET", 12000, 1500, 32000),
            _integer("LLM_OUTPUT_SHORT", 350, 150, 4000),
            _integer("LLM_OUTPUT_NORMAL", 900, 150, 4000),
            _integer("LLM_OUTPUT_DETAILED", 2400, 150, 8000),
            _integer("LLM_TIMEOUT_SECONDS", 90, 10, 300),
        )
        if not cfg.short_output <= cfg.normal_output <= cfg.detailed_output:
            raise ValueError("Giới hạn đầu ra cần SHORT ≤ NORMAL ≤ DETAILED.")
        return cfg


def estimate_input(instructions: str, messages: list[dict], schema: dict) -> int:
    import json
    # UTF-8 byte heuristic for mixed Vietnamese/code, plus envelope allowance.
    # Model usage returned by the API is the authority, not this estimate.
    text = instructions + json.dumps(messages, ensure_ascii=False) + json.dumps(schema, ensure_ascii=False)
    return math.ceil(len(text.encode("utf-8")) / 3) + 64 + 8 * len(messages)


def output_limit(normalized_question: str, selected_limit: int, cfg: Budget) -> int:
    if any(term in normalized_question for term in (
        "chi tiet", "tung buoc", "viet code", "vi du code", "phan tich", "so sanh", "lo trinh", "ke hoach",
    )) or len(normalized_question) > 1200:
        return cfg.detailed_output
    if any(term in normalized_question for term in ("ngan gon", "tom tat", "ngan", "mot cau")):
        return cfg.short_output
    return cfg.normal_output if selected_limit >= 600 else min(selected_limit, cfg.normal_output)
