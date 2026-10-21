"""GMS OpenAI 호환 Chat Completions 어댑터."""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Sequence
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Transport = Callable[[Request, float], bytes]


class GmsLlmError(RuntimeError):
    """키나 외부 응답 본문을 노출하지 않는 GMS 호출 오류."""


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return response.read()


class GmsChatClient:
    def __init__(
        self,
        api_key: str,
        *,
        model_name: str = "gpt-5-nano",
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
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._retry_delay = max(0.0, retry_delay)
        self._transport = transport or _default_transport

    def invoke(self, messages: Sequence[dict[str, str]]) -> str:
        if not messages:
            raise ValueError("메시지가 필요합니다.")
        body = json.dumps(
            {
                "model": self.model_name,
                "messages": list(messages),
            }
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
                return self._parse_response(payload)
            except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)
        error_name = type(last_error).__name__ if last_error else "UnknownError"
        raise GmsLlmError(f"GMS 채팅 요청에 실패했습니다({error_name}).") from last_error

    @staticmethod
    def _parse_response(payload: Any) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GmsLlmError("GMS 채팅 응답 형식이 올바르지 않습니다.") from exc
        if not isinstance(content, str) or not content.strip():
            raise GmsLlmError("GMS 채팅 응답이 비어 있습니다.")
        return content.strip()

    def __repr__(self) -> str:
        return f"GmsChatClient(model_name={self.model_name!r}, endpoint={self._endpoint!r})"

