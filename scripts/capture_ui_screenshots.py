"""로컬 Streamlit의 제출용 화면 3장을 Chrome DevTools Protocol로 캡처한다."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websocket


ROOT = Path(__file__).resolve().parents[1]


class CdpClient:
    def __init__(self, url: str) -> None:
        self._socket = websocket.create_connection(url, timeout=10)
        self._next_id = 0

    def close(self) -> None:
        self._socket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            response = json.loads(self._socket.recv())
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(f"CDP {method} 실패: {response['error']}")
            return response.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")


def _find_chrome() -> Path:
    candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Google Chrome 실행 파일을 찾을 수 없습니다.")


def _wait_until(predicate, *, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise TimeoutError(message)


def _connect(port: int) -> CdpClient:
    target: dict[str, Any] | None = None

    def find_target() -> bool:
        nonlocal target
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                targets = json.load(response)
        except OSError:
            return False
        target = next(
            (
                item
                for item in targets
                if item.get("type") == "page"
                and str(item.get("url", "")).startswith("http://localhost:8501")
            ),
            None,
        )
        return target is not None

    _wait_until(find_target, timeout=15, message="Chrome 디버깅 페이지를 찾지 못했습니다.")
    assert target is not None
    return CdpClient(target["webSocketDebuggerUrl"])


def _wait_for_text(client: CdpClient, text: str, timeout: float = 120) -> None:
    _wait_until(
        lambda: bool(client.evaluate(f"document.body?.innerText.includes({json.dumps(text)})")),
        timeout=timeout,
        message=f"화면에서 '{text}' 상태를 확인하지 못했습니다.",
    )


def _load_fresh(client: CdpClient, url: str) -> None:
    client.call("Page.navigate", {"url": url})
    _wait_for_text(client, "상황을 적으면 관련 법령과 판례를 확인합니다", timeout=30)
    _wait_until(
        lambda: bool(client.evaluate("Boolean(document.querySelector('input[aria-label=\"상담 분야\"]'))")),
        timeout=15,
        message="상담 분야 입력이 준비되지 않았습니다.",
    )


def _submit(client: CdpClient, *, category: str, query: str) -> None:
    category_json = json.dumps(category, ensure_ascii=False)
    query_json = json.dumps(query, ensure_ascii=False)
    selected = client.evaluate(
        """
        (() => {
          const button = document.querySelector('button[aria-label="Open"]');
          if (!button) return false;
          button.click();
          return true;
        })()
        """
    )
    if not selected:
        raise RuntimeError("상담 분야 입력을 찾지 못했습니다.")
    _wait_until(
        lambda: bool(client.evaluate("Boolean(document.querySelector('[role=option]'))")),
        timeout=5,
        message="상담 분야 선택 목록이 열리지 않았습니다.",
    )
    clicked = client.evaluate(
        f"""
        (() => {{
          const option = Array.from(document.querySelectorAll('[role=option]'))
            .find(el => el.textContent.trim() === {category_json});
          if (!option) return false;
          option.click();
          return true;
        }})()
        """
    )
    if not clicked:
        raise RuntimeError(f"상담 분야 항목을 찾지 못했습니다: {category}")
    _wait_until(
        lambda: client.evaluate(
            f"document.querySelector('input[aria-label=\"상담 분야\"]')?.value === {category_json}"
        ),
        timeout=5,
        message=f"상담 분야를 선택하지 못했습니다: {category}",
    )
    time.sleep(1)
    filled = client.evaluate(
        f"""
        (() => {{
          const area = document.querySelector('textarea[aria-label="상황을 구체적으로 적어주세요"]');
          if (!area) return false;
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(area, {query_json});
          area.dispatchEvent(new Event('input', {{bubbles: true}}));
          area.dispatchEvent(new Event('change', {{bubbles: true}}));
          return true;
        }})()
        """
    )
    if not filled:
        raise RuntimeError("질문 입력창을 찾지 못했습니다.")
    time.sleep(0.5)
    submitted = client.evaluate(
        """
        (() => {
          const button = Array.from(document.querySelectorAll('button'))
            .find(el => el.textContent.includes('관련 법령·판례 검토하기'));
          if (!button) return false;
          button.click();
          return true;
        })()
        """
    )
    if not submitted:
        raise RuntimeError("검토 버튼을 찾지 못했습니다.")


def _capture(client: CdpClient, output: Path, *, anchor_text: str) -> None:
    anchor_json = json.dumps(anchor_text, ensure_ascii=False)
    client.evaluate(
        f"""
        (() => {{
          const node = Array.from(document.querySelectorAll('h1,h2,h3,div,p'))
            .find(el => el.textContent.trim() === {anchor_json});
          if (node) node.scrollIntoView({{block: 'start'}});
          return Boolean(node);
        }})()
        """
    )
    time.sleep(0.5)
    result = client.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    output.write_bytes(base64.b64decode(result["data"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeLaw README용 Streamlit 화면 캡처")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "assets")
    parser.add_argument(
        "--scenario",
        choices=("all", "grounded", "privacy", "refusal"),
        default="all",
        help="캡처할 화면. 기본값은 전체입니다.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    chrome = _find_chrome()
    profile = Path(tempfile.mkdtemp(prefix="safelaw-capture-"))
    port = 9223
    process = subprocess.Popen(
        [
            str(chrome),
            "--headless=new",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile}",
            "--window-size=900,1200",
            "--hide-scrollbars",
            args.url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client: CdpClient | None = None
    try:
        client = _connect(port)
        client.call("Page.enable")
        client.call("Runtime.enable")
        client.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 900, "height": 1200, "deviceScaleFactor": 1, "mobile": False},
        )

        if args.scenario in ("all", "grounded"):
            _load_fresh(client, args.url)
            _submit(
                client,
                category="근로계약·부당해고",
                query=(
                    "회사에서 카카오톡으로 내일부터 나오지 말라고 했습니다. "
                    "해고 사유와 시기를 적은 서면 통지를 받지 못했는데 해고 효력은 어떻게 되나요?"
                ),
            )
            _wait_for_text(client, "근거 검증 완료")
            _capture(client, args.output_dir / "safelaw-grounded-answer.png", anchor_text="검토 결과")

        if args.scenario in ("all", "privacy"):
            _load_fresh(client, args.url)
            _submit(
                client,
                category="전세·임대차 보증금",
                query=(
                    "이름: 홍길동, 주민번호 991332-1234567, 전화 010-0000-0000, "
                    "메일 gildong@example.com, 주소 서울특별시 강남구 테헤란로 000입니다. "
                    "전입신고와 확정일자를 마친 세입자인데 집이 경매로 넘어갔습니다."
                ),
            )
            _wait_for_text(client, "개인정보 마스킹 5건")
            _wait_for_text(client, "외부 모델 전달문")
            _capture(client, args.output_dir / "safelaw-privacy-mask.png", anchor_text="검토 결과")

        if args.scenario in ("all", "refusal"):
            _load_fresh(client, args.url)
            _submit(
                client,
                category="근로계약·부당해고",
                query="오늘 점심 메뉴로 김치찌개와 샌드위치 중 무엇이 더 좋을까요?",
            )
            _wait_for_text(client, "근거 부족")
            _capture(client, args.output_dir / "safelaw-refusal.png", anchor_text="검토 결과")

        for path in sorted(args.output_dir.glob("safelaw-*.png")):
            print(f"{path.relative_to(ROOT)}: {path.stat().st_size:,} bytes")
    finally:
        if client is not None:
            client.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
