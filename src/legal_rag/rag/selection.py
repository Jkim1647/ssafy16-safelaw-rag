"""LLM이 번호로 고른 후보 선별 응답을 해석한다.

후보는 `C1`, `P1`처럼 번호로만 보여주고 응답도 번호만 받는다. 목록 밖의 번호와
중복은 버리므로 LLM이 후보에 없는 항목을 만들어 넣을 수 없다.
"""

from __future__ import annotations

import json
import re


class SelectionParseError(ValueError):
    """선별 응답에서 신뢰할 수 있는 selected 배열을 찾지 못했다."""


def parse_numbered_selection(raw_response: str, candidate_count: int, prefix: str) -> list[tuple[int, str]]:
    """`{"selected":[{"id":"P1","reason":"..."}]}`를 (0부터 시작하는 후보 위치, 이유) 목록으로 바꾼다."""

    match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    if not match:
        raise SelectionParseError("선별 응답에 JSON 객체가 없습니다.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise SelectionParseError("선별 응답을 해석하지 못했습니다.") from exc
    selected = payload.get("selected") if isinstance(payload, dict) else None
    if not isinstance(selected, list):
        raise SelectionParseError("선별 응답에 selected 배열이 없습니다.")

    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    for entry in selected:
        if not isinstance(entry, dict):
            continue
        id_match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", str(entry.get("id", "")).strip())
        if not id_match:
            continue
        index = int(id_match.group(1)) - 1
        if not 0 <= index < candidate_count or index in seen:
            continue
        seen.add(index)
        result.append((index, str(entry.get("reason", "")).strip()))
    return result
