"""전체 시스템 아키텍처 그림의 SVG 원본을 만들고 Chrome으로 4K PNG를 렌더링한다.

그림 내용을 바꿀 때는 이 파일의 문구만 고친 뒤 다시 실행한다.

    .\\.venv\\Scripts\\python.exe scripts\\render_architecture.py
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "docs" / "assets" / "safelaw-hd-system-architecture.svg"
PNG_PATH = ROOT / "docs" / "assets" / "safelaw-hd-system-architecture.png"

WIDTH, HEIGHT = 1920, 1080
MARGIN = 44
FONT = "'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Segoe UI', sans-serif"
INK, MUTED, LINE = "#111827", "#5b6472", "#d6dae0"

LANE_TOP, LANE_BOTTOM, LANE_HEAD = 278, 772, 64
LANE_GAP = 16
LANE_WIDTH = (WIDTH - 2 * MARGIN - 4 * LANE_GAP) / 5
CARD_PAD = 16
LINE_HEIGHT = 16


def lane_x(index: int) -> float:
    return MARGIN + index * (LANE_WIDTH + LANE_GAP)


class Svg:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def text(self, x: float, y: float, value: str, *, size: float = 13, weight: int = 400,
             fill: str = INK, anchor: str = "start", spacing: float = 0) -> None:
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" letter-spacing="{spacing}">{escape(value)}</text>'
        )

    def rect(self, x: float, y: float, w: float, h: float, *, fill: str, stroke: str = "none",
             radius: float = 10, width: float = 1.2, dash: str = "") -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'
        )

    def arrow(self, points: list[tuple[float, float]], *, color: str = "#4b5563", dash: str = "",
              width: float = 2) -> None:
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker = "arrow-dash" if dash else "arrow"
        self.add(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}"{dash_attr} '
            f'marker-end="url(#{marker})"/>'
        )


def card_height(lines: int) -> float:
    return 30 + LINE_HEIGHT * lines + 10


def draw_card(svg: Svg, x: float, y: float, w: float, title: str, lines: list[str], *,
              dot: str, fill: str = "#ffffff", stroke: str = "#e3e6ea") -> float:
    h = card_height(len(lines))
    svg.rect(x, y, w, h, fill=fill, stroke=stroke, radius=9)
    svg.add(f'<circle cx="{x + 18:.1f}" cy="{y + 20:.1f}" r="5.5" fill="{dot}"/>')
    svg.text(x + 32, y + 25, title, size=15.5, weight=600)
    for index, line in enumerate(lines):
        svg.text(x + 32, y + 46 + index * LINE_HEIGHT, line, size=12, fill=MUTED)
    return h


def draw_pair(svg: Svg, x: float, y: float, w: float, boxes: list[tuple[str, list[str]]], *,
              fill: str, stroke: str, title_fill: str = INK) -> float:
    """한 줄에 나란히 놓는 작은 상자 두 개. 높이를 돌려준다."""
    gap = 10
    box_w = (w - gap) / 2
    h = 28 + LINE_HEIGHT * max(len(box[1]) for box in boxes) + 12
    for index, (title, lines, *colors) in enumerate(boxes):
        bx = x + index * (box_w + gap)
        box_fill, box_stroke, box_title = colors if colors else (fill, stroke, title_fill)
        svg.rect(bx, y, box_w, h, fill=box_fill, stroke=box_stroke, radius=9)
        svg.text(bx + box_w / 2, y + 24, title, size=15, weight=700, fill=box_title, anchor="middle")
        for line_index, line in enumerate(lines):
            svg.text(bx + box_w / 2, y + 44 + line_index * LINE_HEIGHT, line, size=11.5, fill=MUTED,
                     anchor="middle")
    return h


def draw_chips(svg: Svg, x: float, y: float, w: float, chips: list[tuple[str, str]]) -> float:
    gap = 8
    chip_w = (w - gap * (len(chips) - 1)) / len(chips)
    h = 44
    for index, (title, sub) in enumerate(chips):
        cx = x + index * (chip_w + gap)
        svg.rect(cx, y, chip_w, h, fill="#ffffff", stroke="#d7dbe0", radius=8)
        svg.text(cx + chip_w / 2, y + 19, title, size=13.5, weight=600, anchor="middle")
        svg.text(cx + chip_w / 2, y + 35, sub, size=11, fill=MUTED, anchor="middle")
    return h


def draw_lane(svg: Svg, index: int, number: str, title: str, subtitle: str, color: str, tint: str,
              items: list[tuple]) -> dict[str, tuple[float, float, float, float]]:
    """레인을 그리고 항목별 위치(x, y, w, h)를 돌려준다."""
    x = lane_x(index)
    svg.rect(x, LANE_TOP, LANE_WIDTH, LANE_BOTTOM - LANE_TOP, fill=tint, stroke=color, radius=14, width=1.6)
    svg.add(
        f'<path d="M{x:.1f},{LANE_TOP + LANE_HEAD} V{LANE_TOP + 14} a14,14 0 0 1 14,-14 '
        f'H{x + LANE_WIDTH - 14:.1f} a14,14 0 0 1 14,14 V{LANE_TOP + LANE_HEAD} Z" fill="{color}"/>'
    )
    svg.text(x + 20, LANE_TOP + 31, f"{number} {title}", size=20, weight=700, fill="#ffffff")
    svg.text(x + 20, LANE_TOP + 52, subtitle, size=12.5, fill="#ffffff")

    inner_x, inner_w = x + CARD_PAD, LANE_WIDTH - 2 * CARD_PAD
    heights = []
    for kind, *payload in items:
        if kind == "card":
            heights.append(card_height(len(payload[1])))
        elif kind == "pair":
            heights.append(28 + LINE_HEIGHT * max(len(box[1]) for box in payload[0]) + 12)
        elif kind == "chips":
            heights.append(44)
        elif kind == "pill":
            heights.append(38)
    available = LANE_BOTTOM - LANE_TOP - LANE_HEAD - 32
    gap = min(30.0, (available - sum(heights)) / max(len(items) - 1, 1))

    positions: dict[str, tuple[float, float, float, float]] = {}
    y = LANE_TOP + LANE_HEAD + 16
    for item_index, ((kind, *payload), h) in enumerate(zip(items, heights)):
        key = payload[-1] if isinstance(payload[-1], str) and payload[-1].startswith("#") else f"{index}-{item_index}"
        if kind == "card":
            title, lines, *rest = payload
            style = rest[0] if rest and isinstance(rest[0], dict) else {}
            draw_card(svg, inner_x, y, inner_w, title, lines, dot=style.get("dot", color),
                      fill=style.get("fill", "#ffffff"), stroke=style.get("stroke", "#e3e6ea"))
        elif kind == "pair":
            boxes, *rest = payload
            style = rest[0] if rest and isinstance(rest[0], dict) else {}
            draw_pair(svg, inner_x, y, inner_w, boxes, fill=style.get("fill", "#e9f1fb"),
                      stroke=style.get("stroke", "#a9c6e8"), title_fill=style.get("title", INK))
        elif kind == "chips":
            draw_chips(svg, inner_x, y, inner_w, payload[0])
        elif kind == "pill":
            svg.rect(inner_x + 24, y, inner_w - 48, h, fill="#ffffff", stroke=color, radius=19, width=1.6)
            svg.text(x + LANE_WIDTH / 2, y + 25, payload[0], size=15.5, weight=700, anchor="middle")
        positions[key] = (inner_x, y, inner_w, h)
        if item_index < len(items) - 1:
            mid = x + LANE_WIDTH / 2
            svg.arrow([(mid, y + h + 3), (mid, y + h + gap - 4)], color="#6b7280", width=1.8)
        y += h + gap
    return positions


def build_svg() -> str:
    svg = Svg()
    svg.add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">'
    )
    svg.add(
        '<defs>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4b5563"/></marker>'
        '<marker id="arrow-dash" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#7c6bc4"/></marker>'
        '</defs>'
    )
    svg.rect(0, 0, WIDTH, HEIGHT, fill="#ffffff", radius=0)

    # 머리말
    svg.text(MARGIN, 52, "END-TO-END SYSTEM MAP · 2026-10-22 구현 기준", size=13, fill=MUTED, spacing=1.5)
    svg.text(MARGIN, 96, "SafeLaw Privacy-First Legal RAG", size=38, weight=700)
    svg.text(MARGIN, 127, "개인정보 보호형 생활법률 상담 — 법령과 판례 원문으로 검증되는 내용만 답변", size=17, fill="#4b5563")
    svg.rect(1528, 52, 348, 44, fill="#eef2f7", stroke="#d1d5db", radius=22)
    svg.add('<circle cx="1554" cy="74" r="7" fill="#2c74c9"/>')
    svg.text(1570, 80, "LangGraph · Dual RAG · Multi-turn", size=16.5, weight=600)
    svg.add(f'<line x1="{MARGIN}" y1="148" x2="{WIDTH - MARGIN}" y2="148" stroke="{LINE}" stroke-width="1"/>')

    # 외부 데이터·모델과 사용자 화면
    svg.text(MARGIN, 176, "EXTERNAL SOURCES & MODELS / 외부 데이터·모델", size=13, fill=MUTED, spacing=1.2)
    svg.text(1004, 176, "USER SURFACES / 사용자 화면", size=13, fill=MUTED, spacing=1.2)
    externals = [
        ("National Law Open API", "국가법령정보 법령·판례 원문 · LAW_API_OC", "#e8f1fb", "#9cc3ea"),
        ("Embedding Endpoint", "text-embedding-3-small · 1,536차원", "#fbeee6", "#eab89a"),
        ("SSAFY GMS LLM · gpt-5.4-mini", "검색어 변환 · 답변 · 체크리스트 · 선별", "#eaf5ec", "#a6d3ae"),
    ]
    surfaces = [
        ("Streamlit 상담실", "접수 카드 · 채팅 · 지난 상담"),
        ("Streamlit 조문 찾아보기", "조건 탐색 · 조문별 채팅"),
        ("FastAPI 웹 화면", "HTML·CSS·JS · /api/review"),
    ]
    box_w = (912 - 2 * 16) / 3
    for index, (title, sub, fill, stroke) in enumerate(externals):
        bx = MARGIN + index * (box_w + 16)
        svg.rect(bx, 188, box_w, 64, fill=fill, stroke=stroke, radius=10)
        svg.text(bx + box_w / 2, 214, title, size=16.5, weight=600, anchor="middle")
        svg.text(bx + box_w / 2, 237, sub, size=12.5, fill=MUTED, anchor="middle")
    surface_w = (WIDTH - MARGIN - 1004 - 2 * 16) / 3
    for index, (title, sub) in enumerate(surfaces):
        bx = 1004 + index * (surface_w + 16)
        svg.rect(bx, 188, surface_w, 64, fill="#f3f1fa", stroke="#c5bce6", radius=10)
        svg.text(bx + surface_w / 2, 214, title, size=16.5, weight=600, anchor="middle")
        svg.text(bx + surface_w / 2, 237, sub, size=12.5, fill=MUTED, anchor="middle")

    # 다섯 레인
    draw_lane(svg, 0, "01", "Knowledge Preparation", "지식 준비 · 청킹 · 오프라인 색인", "#c46a2a", "#fdf4ec", [
        ("card", "Collect & Normalize / 수집·정규화", ["Open API로 조문·판례 수집·정규화", "법령 4개 법률 381조 · 판례 50건"]),
        ("card", "Structure-aware Chunking / 구조 청킹", ["법령: 조·항·호 기준 1,200자 / 150자", "판례: 사실·쟁점·판단·결론 1,400자 / 180자"]),
        ("card", "Context-rich Embedding / 문맥 임베딩", ["도메인 + 법령·조문 제목 + 쟁점 + 본문", "삭제 조문 4개는 색인에서 제외"]),
        ("pair", [("STATUTE INDEX", ["safelaw_statutes", "382 chunks · cosine"]),
                  ("CASE INDEX", ["safelaw_cases", "652 chunks · authority"])]),
    ])
    lane2 = draw_lane(svg, 1, "02", "Privacy & Context", "개인정보 보호 · 상담 맥락 · 질의 확장", "#3e8e57", "#eff7f1", [
        ("card", "User Question / 사용자 질문", ["상담 분야(접수 카드) + 자연어 상황", "이어지는 질문도 같은 상담 스레드로"]),
        ("card", "Privacy Guard / 로컬 마스킹", ["규칙: 주민번호·전화·이메일·주소·카드·계좌", "이름·회사명(표시 뒤)·사용자 지정 단어", "날짜·금액은 유지 · 원문 미저장"],
         {"dot": "#d64545", "fill": "#fdf1f1", "stroke": "#e9a3a3"}),
        ("card", "Conversation Thread / 상담 스레드", ["LangGraph InMemorySaver · thread_id", "최근 질문 3개 + 현재 질문으로 검색"]),
        ("card", "Legal Query Expansion / 법률 질의 확장", ["일상어 → 법률 용어 JSON", "규칙 용어 보강 · 실패 시 규칙으로 대체"]),
        ("chips", [("Original", "원문 · 0.7"), ("Rewrite", "재작성 · 1.3"), ("Legal Terms", "법률어 · 1.0")], "#chips"),
    ])
    lane3 = draw_lane(svg, 2, "03", "Dual Retrieval", "LangGraph retrieve 노드 · RRF · 재정렬", "#2c74c9", "#eef4fc", [
        ("pair", [("Statute Search", ["safelaw_statutes", "분야 필터 · 고정 조문"]),
                  ("Case Search", ["safelaw_cases", "권위 등급 · 증분 보강"])], {}, "#search"),
        ("card", "Weighted Reciprocal Rank Fusion", ["가중 RRF: weight ÷ (60 + rank)", "세 질의 결과를 문서 ID 기준으로 통합"]),
        ("card", "Legal Reranking / 법률 재정렬", ["조문 제목·본문 일치 + 판례 권위 + 도메인"]),
        ("card", "MMR Option / 다양성 선택", ["RAG_SEARCH_MODE=mmr · 후보 30개에서 선택"]),
        ("pill", "Top-K Evidence · 법령 5 + 판례 5", "#topk"),
    ])
    lane4 = draw_lane(svg, 3, "04", "Grounded Generation", "LangGraph generate 노드 · 인용 검증 · 차단", "#b04f8a", "#fcf1f7", [
        ("card", "Evidence Pack / 근거 패키지", ["원문 청크 + 메타데이터 + [근거 N] + 공식 URL"], {}, "#evidence"),
        ("card", "Grounded Generation / 근거 제한 생성", ["검색된 법령·판례 밖의 사실 주장 금지", "쟁점 · 유리/불리 요소 · 추가 확인 사실"]),
        ("card", "Citation Validator / 인용 검증", ["인용 ID 존재 · 원문 글자 일치 · 조문 번호", "실패 시 교정 생성 최대 3회 → 계속 실패면 차단"]),
        ("pair", [("PASS / 검증 통과", ["답변 + 인용", "공식 근거 링크"], "#ecf7ee", "#8cc79a", "#24723a"),
                  ("BLOCK / 안전 차단", ["근거 부족 · 인용 실패", "범위 밖 질문"], "#fdeeee", "#e39a9a", "#b42323")],
         {}, "#verdict"),
    ])
    lane5 = draw_lane(svg, 4, "05", "Checklist & Consultation UI", "도메인 특화 기능 · 상담 화면", "#6d5ab0", "#f4f2fb", [
        ("card", "Issue Checklist / 쟁점 체크리스트", ["같은 근거 재사용 · 판단 요소 3~6개", "항목별 인용 검증 · 실패 항목만 제외"], {}, "#checklist"),
        ("card", "Glossary / 법률 용어 풀이", ["로컬 용어집 50개 · LLM 미사용", "조문식 표현도 같은 용어로 연결"]),
        ("card", "Consultation Room / 상담실", ["채팅 · 지난 상담 복구·삭제 · 처음으로", "대화엔 요약, 오른쪽 패널에 체크리스트"], {}, "#room"),
        ("card", "Article Explorer / 조문 찾아보기", ["조건 탐색: 후보 10 → LLM 선별 → 카드", "선택 조문을 [근거 1]로 고정한 채팅"]),
    ])

    # 레인 사이 흐름: 질의 → 검색, Top-K → 근거 패키지, 통과 답변 → 상담실, 같은 근거 → 체크리스트
    def gap_x(left_lane: int) -> float:
        return lane_x(left_lane) + LANE_WIDTH + LANE_GAP / 2

    cx, cy, cw, ch = lane2["#chips"]
    sx, sy, sw, sh = lane3["#search"]
    svg.arrow([(cx + cw + 4, cy + ch / 2), (gap_x(1), cy + ch / 2), (gap_x(1), sy + sh / 2), (sx - 4, sy + sh / 2)])
    tx, ty, tw, th = lane3["#topk"]
    ex, ey, ew, eh = lane4["#evidence"]
    svg.arrow([(tx + tw - 20, ty + th / 2), (gap_x(2), ty + th / 2), (gap_x(2), ey + eh / 2), (ex - 4, ey + eh / 2)])
    vx, vy, vw, vh = lane4["#verdict"]
    rx, ry, rw, rh = lane5["#room"]
    svg.arrow([(vx + vw / 4, vy + vh + 4), (vx + vw / 4, LANE_BOTTOM + 12), (gap_x(3), LANE_BOTTOM + 12),
               (gap_x(3), ry + rh / 2), (rx - 4, ry + rh / 2)])
    kx, ky, kw, kh = lane5["#checklist"]
    shared_y = min(max(ky + kh / 2, ey + 10), ey + eh - 10)
    svg.arrow([(ex + ew + 4, shared_y), (kx - 4, shared_y)], color="#7c6bc4", dash="6 5")

    # 운영·저장·품질 피드백
    band_y, band_h = 798, 216
    svg.rect(MARGIN, band_y, WIDTH - 2 * MARGIN, band_h, fill="#f1f8f7", stroke="#a7d3cc", radius=14, width=1.4)
    svg.text(MARGIN + 26, band_y + 32, "OPERATIONS, STORAGE & QUALITY LOOP / 운영·저장·품질 피드백", size=13, fill=MUTED, spacing=1.2)
    groups = [
        (MARGIN + 26, 640, "Live Case Enrichment / 판례 증분 보강",
         [("질문 캐시 확인", "같은 질문은 재사용"), ("Case API", "용어 3개 · 있는 판례 제외"), ("LLM 후보 선별", "선택·탈락 기록"), ("Incremental Upsert", "없는 판례만 색인")],
         "새 질문마다 retrieve 검색 전에 실행 · LAW_API_OC 필요 · 실패해도 기존 판례로 검색", True),
        (MARGIN + 700, 560, "Local Security & Persistence / 로컬 보안·저장",
         [(".env · Git 제외", "GMS_KEY · OC"), ("원문 미저장", "마스킹 문장만 외부로"), ("세션 메모리", "상담 기록·체크포인터"), ("Chroma", "SQLite + HNSW")],
         "파일·로그·Vector DB에 상담 원문과 마스킹 매핑을 남기지 않음", False),
        (MARGIN + 1294, 512, "Evaluation / 검색·생성 품질 평가",
         [("Recall@5", "법령 1.000"), ("MRR", "법령 0.740"), ("Citation Acc.", "1.000"), ("Refusal Acc.", "1.000")],
         "30문항 · 라벨은 개발자 작성, 전문가 검수 전 · 결과로 검색·검증 기준 조정", False),
    ]
    for gx, gw, title, chips, note, chained in groups:
        svg.text(gx, band_y + 68, title, size=17, weight=600)
        chip_gap = 22 if chained else 10
        chip_w = (gw - chip_gap * (len(chips) - 1)) / len(chips)
        for index, (name, sub) in enumerate(chips):
            chip_x = gx + index * (chip_w + chip_gap)
            fill = "#e8f1fb" if index == 0 and chained else "#ffffff"
            svg.rect(chip_x, band_y + 86, chip_w, 52, fill=fill, stroke="#cfd6dd", radius=9)
            svg.text(chip_x + chip_w / 2, band_y + 108, name, size=14, weight=600, anchor="middle")
            svg.text(chip_x + chip_w / 2, band_y + 126, sub, size=11.5, fill=MUTED, anchor="middle")
            if chained and index < len(chips) - 1:
                svg.arrow([(chip_x + chip_w + 3, band_y + 112), (chip_x + chip_w + chip_gap - 3, band_y + 112)], width=1.6)
        svg.text(gx, band_y + 166, note, size=12, fill=MUTED)
    for divider in (MARGIN + 676, MARGIN + 1272):
        svg.add(f'<line x1="{divider}" y1="{band_y + 52}" x2="{divider}" y2="{band_y + band_h - 24}" stroke="#cfe3df" stroke-width="1.2"/>')

    # 범례
    svg.text(MARGIN, 1052, "실선: 실행 흐름   ·   점선: 답변과 같은 근거를 체크리스트가 재사용   ·   03·04 레인이 LangGraph StateGraph의 두 노드",
             size=12.5, fill=MUTED)
    svg.text(WIDTH - MARGIN, 1052, "원본: docs/assets/safelaw-hd-system-architecture.svg → scripts/render_architecture.py로 4K PNG 렌더링",
             size=12.5, fill=MUTED, anchor="end")
    svg.add("</svg>")
    return "\n".join(svg.parts) + "\n"


def find_chrome() -> Path:
    for candidate in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Google Chrome 실행 파일을 찾을 수 없습니다.")


def render_png(svg_path: Path, png_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="safelaw-architecture-") as profile:
        subprocess.run(
            [
                str(find_chrome()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                f"--user-data-dir={profile}", f"--window-size={WIDTH},{HEIGHT}",
                "--force-device-scale-factor=2", f"--screenshot={png_path}", svg_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeLaw 아키텍처 SVG 원본과 4K PNG 생성")
    parser.add_argument("--svg-only", action="store_true", help="PNG 렌더링 없이 SVG만 만든다")
    args = parser.parse_args()
    SVG_PATH.write_text(build_svg(), encoding="utf-8")
    print(f"{SVG_PATH.relative_to(ROOT)}")
    if not args.svg_only:
        render_png(SVG_PATH, PNG_PATH)
        print(f"{PNG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
