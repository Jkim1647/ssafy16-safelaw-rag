"""GMS OpenAI 호환 Embeddings API 어댑터."""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Sequence
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Transport = Callable[[Request, float], bytes]


class EmbeddingApiError(RuntimeError):
    """인증값을 노출하지 않는 임베딩 API 오류."""


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class GmsEmbeddingClient:
    def __init__(
        self,
        api_key: str,
        *,
        model_name: str = "text-embedding-3-small",
        base_url: str = "https://gms.ssafy.io/gmsapi/api.openai.com/v1",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        transport: Transport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("GMS_KEY가 필요합니다.")
        if not base_url.startswith("https://"):
            raise ValueError("GMS_BASE_URL은 HTTPS 주소여야 합니다.")
        self._api_key = api_key.strip()
        self.model_name = model_name
        self._endpoint = f"{base_url.rstrip('/')}/embeddings"
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._retry_delay = max(0.0, retry_delay)
        self._transport = transport or _default_transport

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("임베딩할 텍스트는 비어 있을 수 없습니다.")
        body = json.dumps(
            {"model": self.model_name, "input": list(texts), "encoding_format": "float"}
        ).encode("utf-8")
        request = Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SafeLaw/0.1 (SSAFY AI Core Project)",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                payload = json.loads(self._transport(request, self._timeout).decode("utf-8"))
                return self._parse_response(payload, len(texts))
            except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)
        error_name = type(last_error).__name__ if last_error else "UnknownError"
        raise EmbeddingApiError(f"GMS 임베딩 요청에 실패했습니다({error_name}).") from last_error

    @staticmethod
    def _parse_response(payload: Any, expected_count: int) -> list[list[float]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise EmbeddingApiError("임베딩 응답 형식이 올바르지 않습니다.")
        ordered = sorted(payload["data"], key=lambda item: int(item.get("index", -1)))
        if len(ordered) != expected_count:
            raise EmbeddingApiError("임베딩 응답 개수가 요청과 다릅니다.")
        vectors: list[list[float]] = []
        for item in ordered:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise EmbeddingApiError("임베딩 벡터가 비어 있습니다.")
            vectors.append([float(value) for value in vector])
        return vectors

    def __repr__(self) -> str:
        return f"GmsEmbeddingClient(model_name={self.model_name!r}, endpoint={self._endpoint!r})"
