"""환경변수 기반 설정.

비밀값을 로그로 출력하지 않도록 설정 객체는 키의 존재 여부만 제공한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    gms_key: str | None
    gms_base_url: str
    gms_embedding_model: str
    law_api_oc: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
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
            law_api_oc=os.getenv("LAW_API_OC") or None,
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
            f"has_gms_key={self.has_gms_key!r}, "
            f"has_law_api_key={self.has_law_api_key!r})"
        )

