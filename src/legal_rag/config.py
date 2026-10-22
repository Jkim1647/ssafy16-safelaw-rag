"""환경변수 기반 설정.

비밀값을 로그로 출력하지 않도록 설정 객체는 키의 존재 여부만 제공한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _int_env(name: str, default: int, *, minimum: int, below: int | None = None) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}는 정수여야 합니다.") from exc
    if value < minimum or (below is not None and value >= below):
        limit = f" {below} 미만" if below is not None else ""
        raise ValueError(f"{name}는 {minimum} 이상{limit}이어야 합니다.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    gms_key: str | None
    gms_base_url: str
    gms_embedding_model: str
    gms_chat_model: str
    law_api_oc: str | None
    gms_query_model: str | None = None
    gms_answer_model: str | None = None
    # 청크 크기를 바꾸면 기존 색인과 맞지 않으므로 청크 생성·색인 스크립트를 다시 실행해야 한다.
    statute_chunk_size: int = 1200
    statute_chunk_overlap: int = 150
    case_chunk_size: int = 1400
    case_chunk_overlap: int = 180
    rag_top_k: int = 5

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        chat_model = os.getenv("GMS_CHAT_MODEL", "gpt-5-nano")
        statute_chunk_size = _int_env("STATUTE_CHUNK_SIZE", 1200, minimum=200)
        case_chunk_size = _int_env("CASE_CHUNK_SIZE", 1400, minimum=200)
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            gms_key=os.getenv("GMS_KEY") or None,
            gms_base_url=os.getenv(
                "GMS_BASE_URL",
                "https://gms.ssafy.io/gmsapi/api.openai.com/v1",
            ),
            gms_embedding_model=os.getenv(
                "GMS_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
            gms_chat_model=chat_model,
            law_api_oc=os.getenv("LAW_API_OC") or None,
            gms_query_model=os.getenv("GMS_QUERY_MODEL") or chat_model,
            gms_answer_model=os.getenv("GMS_ANSWER_MODEL") or "gpt-5.4-mini",
            statute_chunk_size=statute_chunk_size,
            statute_chunk_overlap=_int_env(
                "STATUTE_CHUNK_OVERLAP", 150, minimum=0, below=statute_chunk_size
            ),
            case_chunk_size=case_chunk_size,
            case_chunk_overlap=_int_env("CASE_CHUNK_OVERLAP", 180, minimum=0, below=case_chunk_size),
            rag_top_k=_int_env("RAG_TOP_K", 5, minimum=1),
        )

    @property
    def has_gms_key(self) -> bool:
        return bool(self.gms_key)

    @property
    def has_law_api_key(self) -> bool:
        return bool(self.law_api_oc)

    def __repr__(self) -> str:
        return (
            "Settings("
            f"app_env={self.app_env!r}, "
            f"gms_embedding_model={self.gms_embedding_model!r}, "
            f"gms_chat_model={self.gms_chat_model!r}, "
            f"gms_query_model={self.query_model!r}, "
            f"gms_answer_model={self.answer_model!r}, "
            f"has_gms_key={self.has_gms_key!r}, "
            f"has_law_api_key={self.has_law_api_key!r})"
        )

    @property
    def query_model(self) -> str:
        """검색어 변환용 모델. 미설정 시 기존 채팅 모델을 사용한다."""

        return self.gms_query_model or self.gms_chat_model

    @property
    def answer_model(self) -> str:
        """근거 기반 답변 생성용 모델. 미설정 시 기존 채팅 모델을 사용한다."""

        return self.gms_answer_model or self.gms_chat_model

