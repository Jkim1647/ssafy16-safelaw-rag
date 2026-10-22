"""로컬 Streamlit의 제출용 화면을 Chrome DevTools Protocol로 캡처한다."""

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
# 오른쪽 체크리스트 패널이 대화 옆에 놓이는 데스크톱 폭으로 캡처한다.
VIEWPORT_WIDTH = 1440
VIEWPORT_HEIGHT = 960


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


def _connect(port: int, url: str) -> CdpClient:
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
                and str(item.get("url", "")).startswith(url)
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
    _wait_for_text(client, "생활법률 상담실", timeout=30)
    _wait_until(
        lambda: bool(client.evaluate(
            "Boolean(document.querySelector('[data-testid=stSidebar] input[aria-label=\"상담 분야\"]'))"
        )),
        timeout=15,
        message="상담 분야 입력이 준비되지 않았습니다.",
    )


def _choose_option(client: CdpClient, open_button: str, label: str) -> None:
    """open_button은 선택 목록을 여는 버튼을 반환하는 JS 식이다."""
    if not client.evaluate(f"(() => {{ const b = {open_button}; if (!b) return false; b.click(); return true; }})()"):
        raise RuntimeError("선택 목록 버튼을 찾지 못했습니다.")
    _wait_until(
        lambda: bool(client.evaluate("Boolean(document.querySelector('[role=option]'))")),
        timeout=5,
        message="선택 목록이 열리지 않았습니다.",
    )
    label_json = json.dumps(label, ensure_ascii=False)
    if not client.evaluate(
        f"(() => {{ const o = Array.from(document.querySelectorAll('[role=option]'))"
        f".find(el => el.textContent.trim() === {label_json}); if (!o) return false; o.click(); return true; }})()"
    ):
        raise RuntimeError(f"선택 항목을 찾지 못했습니다: {label}")
    time.sleep(1)


def _send_chat(client: CdpClient, text: str, *, expected_messages: int, timeout: float = 180) -> None:
    """채팅 입력창에 질문을 보내고 마지막 답변에 상태 코드가 나타날 때까지 기다린다."""
    text_json = json.dumps(text, ensure_ascii=False)
    filled = client.evaluate(
        f"""
        (() => {{
          const area = document.querySelector('[data-testid=stChatInput] textarea');
          if (!area) return false;
          Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(area, {text_json});
          area.dispatchEvent(new Event('input', {{bubbles: true}}));
          return true;
        }})()
        """
    )
    if not filled:
        raise RuntimeError("채팅 입력창을 찾지 못했습니다.")
    time.sleep(0.5)
    client.evaluate("document.querySelector('[data-testid=stChatInputSubmitButton]').click()")
    _wait_until(
        lambda: bool(client.evaluate(
            f"(() => {{ const m = document.querySelectorAll('[data-testid=stChatMessage]');"
            f" const last = m[m.length - 1];"
            f" return m.length >= {expected_messages} && Boolean(last)"
            f" && (last.innerText.includes('상태 코드') || last.innerText.includes('처리하지 못했습니다'))"
            f" && !document.body.innerText.includes('확인하고 있어요'); }})()"
        )),
        timeout=timeout,
        message="상담 답변을 확인하지 못했습니다.",
    )
    time.sleep(1.5)


def _choose_intake(client: CdpClient, category: str) -> None:
    """상담실 안 접수 카드에서 분야를 고른다."""
    category_json = json.dumps(category, ensure_ascii=False)
    clicked = client.evaluate(
        f"""
        (() => {{
          const title = Array.from(document.querySelectorAll('p.intake-title'))
            .find(el => el.textContent.trim() === {category_json});
          let card = title;
          while (card && !card.querySelector('button')) card = card.parentElement;
          const button = card && card.querySelector('button');
          if (!button) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not clicked:
        raise RuntimeError(f"접수 카드를 찾지 못했습니다: {category}")
    _wait_for_text(client, "이런 상황을 많이 물어보세요", timeout=15)
    time.sleep(1)


def _set_checklist(client: CdpClient, enabled: bool) -> None:
    """사이드바 체크리스트 토글을 원하는 상태로 맞춘다. 끄면 GMS 호출이 한 번 줄어든다."""
    client.evaluate(
        f"""
        (() => {{
          const box = document.querySelector('[data-testid=stSidebar] input[type=checkbox]');
          if (box && box.checked !== {str(enabled).lower()}) box.click();
        }})()
        """
    )
    time.sleep(1)


def _ask_consultation(client: CdpClient, *, category: str, query: str) -> None:
    _choose_intake(client, category)
    # 첫 화면의 상담 안내 메시지 1개 + 질문 + 답변
    _send_chat(client, query, expected_messages=3)


def _click_sidebar_button(client: CdpClient, text: str) -> None:
    text_json = json.dumps(text, ensure_ascii=False)
    if not client.evaluate(
        f"(() => {{ const b = Array.from(document.querySelectorAll('[data-testid=stSidebar] button'))"
        f".find(el => el.textContent.includes({text_json})); if (!b) return false; b.click(); return true; }})()"
    ):
        raise RuntimeError(f"사이드바 버튼을 찾지 못했습니다: {text}")
    time.sleep(1.5)


def _scroll_top(client: CdpClient) -> None:
    client.evaluate(
        "(() => { const c = document.querySelector('[data-testid=stAppScrollToBottomContainer]'); if (c) c.scrollTop = 0; })()"
    )
    time.sleep(0.5)


def _scroll_to_message(client: CdpClient, index: int) -> None:
    _scroll_to(client, f"document.querySelectorAll('[data-testid=stChatMessage]')[{index}]")


def _scroll_to(client: CdpClient, finder: str) -> None:
    """finder는 요소를 반환하는 JS 식이다. 찾으면 화면 맨 위로 스크롤한다."""
    found = client.evaluate(
        f"""
        (() => {{
          const node = {finder};
          if (node) {{ node.scrollIntoView({{block: 'start'}}); let box = node.parentElement; while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement; if (box) box.scrollBy(0, -90); }}
          return Boolean(node);
        }})()
        """
    )
    if not found:
        raise RuntimeError("캡처 기준 요소를 찾지 못했습니다.")
    time.sleep(0.5)


def _screenshot(client: CdpClient, output: Path) -> None:
    result = client.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    output.write_bytes(base64.b64decode(result["data"]))


# 채팅 입력창이 화면 아래에 고정되면 stMain 대신 stMainBlockContainer만 남는다.
ACTIVE_PANEL = (
    "(document.querySelector('[data-testid=stMain]') || document.querySelector('[data-testid=stMainBlockContainer]'))"
)


def _set_value(client: CdpClient, selector: str, value: str) -> None:
    selector_json = json.dumps(selector)
    value_json = json.dumps(value, ensure_ascii=False)
    filled = client.evaluate(
        f"""
        (() => {{
          const node = {ACTIVE_PANEL}?.querySelector({selector_json});
          if (!node) return false;
          const proto = node.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(proto, 'value').set.call(node, {value_json});
          node.dispatchEvent(new Event('input', {{bubbles: true}}));
          node.dispatchEvent(new Event('change', {{bubbles: true}}));
          return true;
        }})()
        """
    )
    if not filled:
        raise RuntimeError(f"입력 요소를 찾지 못했습니다: {selector}")
    time.sleep(0.5)


def _click_button(client: CdpClient, text: str) -> None:
    text_json = json.dumps(text, ensure_ascii=False)
    clicked = client.evaluate(
        f"""
        (() => {{
          const button = Array.from({ACTIVE_PANEL}?.querySelectorAll('button') || [])
            .find(el => el.textContent.includes({text_json}));
          if (!button) return false;
          button.click();
          return true;
        }})()
        """
    )
    if not clicked:
        raise RuntimeError(f"버튼을 찾지 못했습니다: {text}")


def _run_article_scenario(client: CdpClient, url: str, output_dir: Path) -> None:
    _load_fresh(client, url)
    client.evaluate(
        "Array.from(document.querySelectorAll('[data-testid=stSidebar] label'))"
        ".find(label => label.textContent.includes('조문 찾아보기')).click()"
    )
    _wait_for_text(client, "조건으로 조문을 찾고", timeout=15)
    _choose_option(client, f"{ACTIVE_PANEL}.querySelector('button[aria-label=\"Open\"]')", "근로계약·부당해고")
    _wait_for_text(client, "또는 목록에서 직접 선택", timeout=15)
    _set_value(
        client,
        'input[aria-label="찾고 싶은 조문의 조건을 자연어로 적어주세요"]',
        "해고할 때 회사가 지켜야 하는 통보 절차를 정한 조문",
    )
    _click_button(client, "조건에 맞는 조문 찾기")
    _wait_for_text(client, "개 조문을 골랐습니다")
    # 상태 문구가 먼저 그려지고 카드는 같은 실행의 뒤쪽에서 그려진다.
    _wait_for_text(client, "이 조문으로 상담하기", timeout=30)
    time.sleep(1)
    _scroll_to(client, f"Array.from({ACTIVE_PANEL}.querySelectorAll('p')).find(el => el.textContent.startsWith('조건: '))")
    _screenshot(client, output_dir / "safelaw-condition-search.png")

    _click_button(client, "이 조문으로 상담하기")
    _wait_until(
        lambda: bool(client.evaluate("Boolean(document.querySelector('[data-testid=stChatInput] textarea'))")),
        timeout=15,
        message="조문별 채팅 입력창이 나타나지 않았습니다.",
    )
    _send_chat(client, "팀장이 카카오톡으로만 해고를 알렸어요. 이 통보도 효력이 있나요?", expected_messages=2)
    _scroll_to(client, "Array.from(document.querySelectorAll('h3')).find(el => el.textContent.startsWith('💬'))")
    _screenshot(client, output_dir / "safelaw-article-chat.png")


def _run_web_scenario(client: CdpClient, web_url: str, output_dir: Path) -> None:
    """심화 F2013 HTML·CSS·JS 화면에서 질문을 제출하고 결과를 캡처한다."""
    client.call("Page.navigate", {"url": web_url})
    _wait_until(
        lambda: bool(client.evaluate(
            "Boolean(document.getElementById('submit')) && !document.getElementById('submit').disabled"
        )),
        timeout=30,
        message="웹 화면이 준비되지 않았습니다. uvicorn 서버와 GMS_KEY를 확인해 주세요.",
    )
    question = json.dumps(
        "팀장이 카카오톡으로 내일부터 나오지 말라고 했어요. 연락처는 010-0000-0000입니다. "
        "해고 사유와 날짜가 적힌 문서는 받지 못했습니다.",
        ensure_ascii=False,
    )
    client.evaluate(
        f"""
        (() => {{
          const category = document.getElementById('category');
          category.value = 'labor';
          category.dispatchEvent(new Event('change', {{bubbles: true}}));
          document.getElementById('question').value = {question};
          document.getElementById('submit').click();
        }})()
        """
    )
    _wait_until(
        lambda: bool(client.evaluate(
            "document.getElementById('status-badge').textContent.length > 0"
            " || document.getElementById('form-error').textContent.length > 0"
        )),
        timeout=180,
        message="웹 화면 검토 결과를 확인하지 못했습니다.",
    )
    time.sleep(1)
    _scroll_to(client, "document.getElementById('result')")
    _screenshot(client, output_dir / "safelaw-web-frontend.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeLaw README용 Streamlit 화면 캡처")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "assets")
    parser.add_argument(
        "--scenario",
        choices=("all", "grounded", "privacy", "refusal", "article", "web"),
        default="all",
        help="캡처할 화면. 기본값은 전체입니다.",
    )
    parser.add_argument("--web-url", default="http://localhost:8000", help="F2013 웹 화면 주소 (web 장면 전용)")
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
            f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
            "--hide-scrollbars",
            args.url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client: CdpClient | None = None
    try:
        client = _connect(port, args.url)
        client.call("Page.enable")
        client.call("Runtime.enable")
        client.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT, "deviceScaleFactor": 1, "mobile": False},
        )

        if args.scenario in ("all", "grounded"):
            _load_fresh(client, args.url)
            # 첫 질문 전 화면: 문패, 상담실 약속, 접수 카드
            time.sleep(1.5)
            _scroll_top(client)
            _screenshot(client, args.output_dir / "safelaw-lawfirm-room.png")
            _set_checklist(client, True)
            _ask_consultation(
                client,
                category="근로계약·부당해고",
                query=(
                    "5명 이상 회사에서 8개월 일했는데 팀장이 카카오톡으로 내일부터 나오지 말라고 했어요. "
                    "해고 사유와 날짜가 적힌 문서는 받지 못했어요. 이런 해고도 효력이 있나요?"
                ),
            )
            _scroll_to_message(client, 1)
            _screenshot(client, args.output_dir / "safelaw-grounded-answer.png")
            if client.evaluate("document.body.innerText.includes('확인한 항목')"):
                # 대화 안 요약 카드와 오른쪽 패널의 전체 체크리스트를 한 화면에 담는다.
                _scroll_to(
                    client,
                    "Array.from(document.querySelectorAll('[data-testid=stChatMessage] p'))"
                    ".find(el => el.textContent.startsWith('📋 쟁점 체크리스트'))",
                )
                _screenshot(client, args.output_dir / "safelaw-issue-checklist.png")
            # 앞선 상담을 이어받는 질문: LangGraph 상담 스레드가 맥락을 붙인다.
            _send_chat(client, "그럼 회사가 나중에 서면으로 다시 보내면 효력이 생기나요?", expected_messages=5)
            _scroll_to_message(client, 3)
            _screenshot(client, args.output_dir / "safelaw-consult-followup.png")

        if args.scenario in ("all", "privacy"):
            _load_fresh(client, args.url)
            _set_checklist(client, False)
            _ask_consultation(
                client,
                category="전세·임대차 보증금",
                query=(
                    "이름: 홍길동, 주민번호 991332-1234567, 전화 010-0000-0000, "
                    "메일 gildong@example.com, 주소 서울특별시 강남구 테헤란로 000입니다. "
                    "전입신고와 확정일자를 마친 세입자인데 집이 경매로 넘어갔습니다."
                ),
            )
            client.evaluate(
                "Array.from(document.querySelectorAll('summary'))"
                ".find(el => el.textContent.includes('원문과 외부 모델 전달문 비교')).click()"
            )
            time.sleep(1)
            _scroll_to_message(client, 1)
            _screenshot(client, args.output_dir / "safelaw-privacy-mask.png")
            # 처음으로 돌아간 뒤 사이드바 지난 상담에서 같은 상담을 다시 연다. GMS 호출은 없다.
            _click_button(client, "← 처음으로")
            _wait_for_text(client, "어떤 일로 오셨나요?", timeout=15)
            _click_sidebar_button(client, "이름:")
            _wait_for_text(client, "원문과 외부 모델 전달문 비교", timeout=15)
            _scroll_to_message(client, 1)
            _screenshot(client, args.output_dir / "safelaw-consult-history.png")

        if args.scenario in ("all", "refusal"):
            _load_fresh(client, args.url)
            _set_checklist(client, False)
            _ask_consultation(
                client,
                category="근로계약·부당해고",
                query="오늘 점심 메뉴로 김치찌개와 샌드위치 중 무엇이 더 좋을까요?",
            )
            _scroll_to_message(client, 1)
            _screenshot(client, args.output_dir / "safelaw-refusal.png")

        if args.scenario in ("all", "article"):
            _run_article_scenario(client, args.url, args.output_dir)

        if args.scenario == "web":
            _run_web_scenario(client, args.web_url, args.output_dir)

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
