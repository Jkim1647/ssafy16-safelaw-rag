"""외부 문서 출처 허용 정책."""

from __future__ import annotations

from urllib.parse import urlparse

OFFICIAL_SOURCE_HOSTS = frozenset({"law.go.kr", "scourt.go.kr"})


def is_official_source(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == allowed or host.endswith("." + allowed)
        for allowed in OFFICIAL_SOURCE_HOSTS
    )

