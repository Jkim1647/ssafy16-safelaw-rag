# 검증 결과 — SafeLaw

명세서 4장의 확인 항목을 실행 결과로 기록한다. 결과는 `통과`·`부분`·`실패`·`미확인`·`미구현`으로 표시한다. 기준일 2026-10-22, 로컬 Streamlit(8502)과 레포 `.venv`(Python 3.12)에서 확인했다.

## 1. 요약

| 구분 | 결과 |
|---|---|
| 필수 기능 F2001~F2012 | 12개 모두 통과 |
| 심화 기능 | F2013 HTML/CSS/JS 화면 통과, F2014 MMR 통과, F2015 RAG 전후 비교 통과, F2016 부분 |
| 비기능 NF2001~NF2007 | 7개 모두 통과 |
| 자동 테스트 | 168개 통과 |
| 남은 항목 | [7장](#7-남은-항목) 참고 |

## 2. 확인 항목별 결과 (명세서 4.1~4.7)

### 4.1 데이터와 색인 (F2001~F2002)

| 확인 항목 | 결과 | 증빙 |
|---|---|---|
| 로드한 항목 수와 색인 청크 수 | 통과 | 수집 조문 381건 중 본문이 "삭제"뿐인 4건 제외 → 377개 조문, 청크 382개, 실제 법령 Chroma 382건. 1,200자를 넘는 5개 조문만 2개로 나뉘어 차이 5 |
| 색인을 두 번 실행해도 청크 수가 늘지 않음 | 통과 | 같은 382개 청크를 새 Chroma에 두 번 upsert → 1회 382, 2회 382 (청크 ID 고정) |
| 항목 1건의 색인 텍스트에 의도한 속성 포함 | 통과 | `labor:001872:0027001:000` = 도메인·법령명·조문 번호·제목·쟁점 태그·본문 ([설계문서 2.1](rag-pipeline-design.md#21-safelaw_statutes--항목-메타데이터-rag-1)) |

### 4.2 문서 수집과 색인 (F2003~F2005)

| 확인 항목 | 결과 | 증빙 |
|---|---|---|
| 프롬프트1이 뽑은 검색어 목록 | 통과 | 카카오톡 해고 질문 → `해고, 해고 통보, 서면통지, 해고사유, 해고시기, 해고 효력, 근로계약 해지, 부당해고` (`show_evidence.py --compare-search` 출력) |
| 프롬프트2에 따라 색인된 문서와 버려진 문서 구분 | 통과 | 임대차 갱신 거절 질문: 목록 후보 8건 중 2023다307024만 `indexed`, 양도소득세·가맹사업 등 7건 `rejected` (`enrich_case_index.py` 출력, [case-retrieval-evaluation.md](case-retrieval-evaluation.md#후보-선별-프롬프트)) |
| 같은 질문을 다시 물으면 수집이 일어나지 않음 | 통과 | 같은 질문 재실행 → `cache_hit: true`, 같은 결정 목록 반환 |
| 선택한 항목 자체를 다룬 문서가 빠지지 않음 | 통과 | 조문별 채팅에서 선택 조문이 항상 `[근거 1]` (단위 테스트 `test_pinned_article_is_always_first_evidence`, 화면 확인) |
| 청크 크기·중복 길이를 바꾸면 청크 수가 달라짐 | 통과 | 법령 1200/150 → 382, 800/150 → 397, 500/100 → 432, 300/50 → 527. 판례 1400/180 → 652, 1000/200 → 912, 700/100 → 1265 (`.env` 값만 변경) |

### 4.3 답변과 근거 (F2006~F2008)

| 확인 항목 | 결과 | 증빙 |
|---|---|---|
| Top-k를 바꾸면 근거 목록이 달라짐 | 통과 | Top-k 1 → 법령 1·판례 1, 3 → 3·3, 5 → 5·5, 8 → 8·7 (`show_evidence.py --top-k 1 3 5 8`) |
| LangGraph가 retrieve·generate 두 노드 | 통과 | `show_rag_graph.py` → `nodes: retrieve, generate` / `__start__ -> retrieve -> generate -> __end__` |
| 답변의 근거 번호와 화면 근거 목록 일치 | 통과 | 인용된 근거만 `확인된 근거`에 표시. 존재하지 않는 번호·원문에 없는 인용은 코드가 차단 (`test_citations`, `test_pipeline`) |
| 항목 메타데이터와 외부 문서 구분 | 통과 | 근거 링크를 `법령 근거` / `유사 판례`로 나눠 표시, CONTEXT에 `document_type` 구분 |
| 문서에 없는 것을 물으면 확인되지 않는다고 답함 | 통과 | "근로기준법 제200조는?" → `insufficient_evidence`, 점심 메뉴 질문 → 근거 부족 화면 (![거부](assets/safelaw-refusal.png)) |
| 인용된 근거가 없을 때 안내 | 통과 | 인용 없는 주장은 검증에서 실패 → 재생성 → 3회 실패 시 `invalid_citations` 안내. E2E 30문항에서 검증되지 않은 답변 노출 0건 |

![근거 검증된 답변](assets/safelaw-grounded-answer.png)

### 4.4 서비스 기능과 화면 (F2009~F2012)

| 확인 항목 | 결과 | 증빙 |
|---|---|---|
| 상담실에서 이어지는 질문이 앞선 상담 맥락을 유지 | 통과 | "그럼 회사가 나중에 서면으로 다시 보내면 효력이 생기나요?"에 "어제 카카오톡으로 해고 통지를 받았더라도…"라고 첫 질문 상황을 이어 답함. 같은 상담은 같은 `thread_id`, 새 상담은 새 `thread_id` (`test_pipeline`, `test_consultation_room`) |
| 지난 상담 목록에서 복구·삭제 | 통과 | 브라우저에서 상담 2개를 만든 뒤 첫 상담을 다시 열어 "그럼 회사가 나중에 서면으로 다시 보내면 어떻게 돼요?"를 묻자 카카오톡 해고 통보 맥락을 이어 답함. 목록은 최근 순, 🗑️ 삭제 시 목록과 체크포인터 스레드가 함께 지워짐 (`test_consultation_room`, `test_pipeline`) |
| 항목을 바꿔도 이전 대화가 섞이지 않음 | 통과 | 제27조 대화 2개 → 제26조로 전환 시 0개 → 제27조로 복귀 시 2개 유지 (브라우저 확인) |
| 조건 탐색 결과에 조건과 맞지 않는 항목이 섞이지 않음 | 통과 | "해고할 때 회사가 지켜야 하는 통보 절차" → 후보 10개 중 제27조·제26조만 선정 이유와 함께 표시. 후보 밖 번호는 코드가 무시 |
| 도메인 특화 기능의 결과에도 근거 제시 | 통과 | 쟁점 체크리스트 항목마다 `[근거 N]`과 원문 인용 문구, 근거 링크 목록 |
| 체크리스트는 대화에 요약, 전체는 오른쪽 패널 | 통과 | 답변 안에는 상태별 개수 요약만 있고 체크박스는 패널에만 있음. 새 답변이 오면 패널이 최신 답변으로 바뀌고, 이전 답변의 `오른쪽 패널에서 보기`로 전환됨 (`test_consultation_room`). 1440px에서 패널 고정(sticky), 375px에서 대화 아래로 내려감을 GMS 호출 없는 가짜 파이프라인으로 확인 |
| 처음으로·뒤로 이동 | 통과 | 상담실 `← 처음으로`는 분야 선택 화면으로 돌아가고 진행 중인 대화는 지난 상담에 남음. 조문 찾아보기의 `← 상담실로`, 조문 채팅의 `← 다른 조문 고르기` 동작을 브라우저와 AppTest로 확인 (`test_consultation_room`) |
| 첫 화면에서 신뢰 근거와 질문 진입점 제시 | 통과 | 첫 질문 전에 `원문으로만 답해요`·`근거가 없으면 답하지 않아요`·`개인정보는 가리고 남기지 않아요` 약속을 보여 주고, 숫자(법률 4개·조문 381개·판례 50건·2023~2026년 선고·기준일 2026-10-21)는 데이터셋 manifest에서 읽음. 판례 미검수 사실과 대한법률구조공단(132) 안내를 함께 표시. 상담 분야를 상담실 안에서 바로 고르고, 마지막 답변 아래에만 이어 묻기 안내 (`test_consultation_room`, `test_streamlit_ui`) |
| 체크리스트 법률 용어를 쉬운 말로 풀이 | 통과 | 미리 작성한 용어집(50개)에서 항목에 나온 용어만 골라 `📖`로 표시, 같은 용어는 한 번만. 풀이의 기간·비율(해고예고 30일, 구제신청 3개월, 휴업수당 70%, 대항력 다음 날, 상속 승인·포기 3개월, 상속회복 3년·10년, 임금 시효 3년 등)은 색인된 조문 원문과 대조함 (`test_glossary`, `test_consultation_room`) |
| 문서 수집·답변 생성 중 진행 상태 표시 | 통과 | 답변·체크리스트·조문 채팅은 spinner, 조건 탐색은 `st.status`로 "후보 N개 중 M개 조문을 골랐습니다" |
| 색인 없음·API 키 없음 안내 | 통과 | `GMS_KEY` 없이 실행 → 사이드바 ".env에 GMS_KEY를 설정해 주세요.", 검토 버튼 비활성 (Streamlit AppTest). 색인 경로가 없으면 "법령 색인이 없습니다. build_statute_index.py를 먼저 실행해 주세요." |
| 위험 도메인 면책 안내 | 통과 | 모든 답변 끝과 화면 하단에 "법률 자문이나 승소 가능성 예측이 아닙니다", 판례 인용 시 법령 개정·후속 판례 확인 경고 |

![조건 기반 조문 탐색](assets/safelaw-condition-search.png)

![조문별 채팅](assets/safelaw-article-chat.png)

![내 상황 쟁점 체크리스트](assets/safelaw-issue-checklist.png)

![개인정보 마스킹 비교](assets/safelaw-privacy-mask.png)

### 4.5 심화 기능 (F2013~F2016)

| 번호 | 결과 | 증빙 |
|---|---|---|
| F2013 HTML/CSS/JS 화면 | 통과 | FastAPI(`/api/status`, `/api/review`)와 정적 HTML·CSS·JS 분리. 실제 질문에서 마스킹 2건, `answered`, 법령·판례 근거 링크, 체크리스트 5개 표시 확인, `test_web_api` 7개 ([web-api.md](web-api.md)) |
| F2014 MMR | 통과 | 같은 검색 계획으로 비교: 카카오톡 해고 질문에서 법령 5번째 근거가 제104조 → 제76조의3, 경매 질문에서 판례 5번째가 2025다213466 → 2022다247378로 바뀜 (README MMR 절) |
| F2015 RAG 전후 비교 | 통과 | 6문항 2회 비교. RAG 미사용은 형제자매 유류분(2024 삭제)을 두 번 모두 잘못 안내하고, 1차에서는 존재하지 않는 제200조를 지어냄. RAG는 2차에서 제1112조로 정확히 안내 ([rag-before-after.md](rag-before-after.md)) |
| F2016 여러 출처 결합 | 부분 | 법령 조문·판례를 다른 청킹 방식으로 함께 색인하고 근거에 종류를 구분. 다만 두 문서 모두 국가법령정보 API 출처 |

### 4.6 RAG 사용 전후 품질 비교

[rag-before-after.md](rag-before-after.md)에 6문항 결과와 사실 정확성·근거 제시·모름 표시 비교를 기록했다.

### 4.7 비기능 요구사항 (NF2001~NF2007)

| 번호 | 결과 | 증빙 |
|---|---|---|
| NF2001 응답 시간 | 통과 | 분야별 예시 질문 2회씩, 답변+체크리스트 전체 8.3~16.7초 (아래 표). 검색어 변환 모델 변경 전에는 31.8~64.0초였다 |
| NF2002 수집 캐시 | 통과 | 같은 질문 재실행 `cache_hit: true`, 보유 사건번호는 본문 미조회 (`test_case_enrichment`) |
| NF2003 API 키 관리 | 통과 | `.env`는 `.gitignore` 대상, `git ls-files .env data/indexes data/raw data/cache` 결과 없음, 추적 파일에서 키 패턴 검색 결과 없음 |
| NF2004 내부 정보 비노출 | 통과 | 처리한 오류는 고정 문구만 표시. `.streamlit/config.toml`에 `showErrorDetails = "none"`을 두어 처리하지 못한 예외도 추적 정보를 화면에 보이지 않음. 실행 정보에는 모델명만 표시 |
| NF2005 모듈 분리 | 통과 | `collectors`·`rag`(chunking/indexing/retrieval/pipeline)·`adapters`·`security`·`ui` 분리, 수집 범위는 `data/*_sources.json` |
| NF2006 외부 API 예절 | 통과 | 법령·판례 API 클라이언트에 재시도(지연 0.5초×시도), 요청 간격, `User-Agent: SafeLaw/0.1 (SSAFY AI Core Project)` |
| NF2007 출처·이용 조건 | 통과 | [data-source-inventory.md](data-source-inventory.md) |

응답 시간 측정 (판례 실시간 보강 켬, 답변·체크리스트 `gpt-5.4-mini`):

| 분야 | 실행 | 이전 합계 (검색어 변환 nano) | 현재 답변 | 현재 체크리스트 | 현재 합계 | 비고 |
|---|---|---:|---:|---:|---:|---|
| 근로 | 1 | 38.9s | 14.3s | 2.4s | 16.7s | 3회 교정 |
| 근로 | 2 | 33.7s | 6.8s | 2.6s | 9.4s | 1회 생성 |
| 임대차 | 1 | 60.9s | 11.1s | 2.7s | 13.7s | 3회 교정 |
| 임대차 | 2 | 64.0s | 11.5s | 2.3s | 13.8s | 3회 실패 → `invalid_citations` |
| 상속 | 1 | 33.4s | 5.7s | 2.6s | 8.3s | 1회 생성 |
| 상속 | 2 | 31.8s | 6.2s | 2.9s | 9.1s | 1회 생성 |

구간별로 재 보니 검색(22~29초)이 답변 생성(4~5초)보다 훨씬 길었고, 검색 시간의 대부분이 `gpt-5-nano` 검색어 변환(호출당 26~34초)이었다. 같은 프롬프트에서 `gpt-5.4-mini`는 대부분 1.1~1.3초였다. 대신 검색 품질이 조금 낮아졌다(4.2절 표). `.env`의 `GMS_QUERY_MODEL=gpt-5-nano`로 되돌릴 수 있다.

## 3. 요구사항 대조표

| 번호 | 구현 위치 | 검증 | 결과 |
|---|---|---|---|
| F2001 | `collectors/law_api.py`, `scripts/build_statute_dataset.py`, `rag/chunking.py` | 381조문, 색인 텍스트 출력 | 통과 |
| F2002 | `adapters/vector_store.py`, `scripts/build_statute_index.py` | 382건, 재색인 중복 없음 | 통과 |
| F2003 | `rag/retrieval.py` `LegalQueryExpander` | 검색어 목록 출력, `test_retrieval` | 통과 |
| F2004 | `rag/case_selection.py`, `rag/case_enrichment.py` | 선택·탈락 기록, 캐시, `test_case_selection`·`test_case_enrichment` | 통과 |
| F2005 | `rag/case_chunking.py`, `scripts/build_case_index.py`, `.env` 청크 설정 | 청크 수 변화, `test_config` | 통과 |
| F2006 | `rag/retrieval.py`, `rag/pipeline.py` `evidence_from_retrieval` | Top-k 비교, 고정 조문, `test_pipeline` | 통과 |
| F2007 | `rag/pipeline.py` LangGraph, `rag/prompts.py` | 그래프 출력, 거부 동작 | 통과 |
| F2008 | `rag/citations.py`, `ui/streamlit_app.py` | 인용 검증, 근거 링크 | 통과 |
| F2009 | `rag/statute_catalog.py`, `ui/streamlit_app.py` 조문 찾아보기·상담실 | 조문별 대화 분리, 상담 스레드 이어짐(`test_consultation_room`) | 통과 |
| F2010 | `rag/issue_checklist.py` | 체크리스트 화면, `test_issue_checklist` | 통과 |
| F2011 | `rag/condition_search.py` | 조건 탐색 카드, `test_statute_items` | 통과 |
| F2012 | `ui/streamlit_app.py` | 진행 상태, 키·색인 없음 안내, 면책 | 통과 |
| F2013 | `web/api.py`, `web/static/*` | API·화면 동작, `test_web_api` | 통과 |
| F2014 | `rag/mmr.py`, `RAG_SEARCH_MODE` | 유사도·MMR 비교, `test_mmr` | 통과 |
| F2015 | `scripts/compare_rag_baseline.py` | [rag-before-after.md](rag-before-after.md) | 통과 |
| F2016 | 법령·판례 별도 컬렉션 | 근거 종류 구분 | 부분 |
| NF2001 | `config.py` 검색어 변환 모델 | 응답 시간 측정 8.3~16.7초 | 통과 |
| NF2002 | `rag/case_enrichment.py` | 캐시 재실행 | 통과 |
| NF2003 | `config.py`, `.gitignore` | Git 추적 검사 | 통과 |
| NF2004 | `ui/streamlit_app.py`, `.streamlit/config.toml` | 오류 문구 | 통과 |
| NF2005 | `src/legal_rag/*` 계층 | 구조 확인 | 통과 |
| NF2006 | `collectors/*` | 재시도·간격·User-Agent | 통과 |
| NF2007 | `docs/data-source-inventory.md` | 문서 | 통과 |

## 4. 테스트 결과표

### 4.1 자동 테스트

`.\.venv\Scripts\python.exe -m unittest discover -s tests` → **168개 통과** (2026-10-22). 빈 venv에서 `pip install -e .` 후에도 통과를 확인했다.

| 모듈 | 개수 | 대상 |
|---|---:|---|
| test_pipeline | 18 | LangGraph 노드, 상담 스레드 맥락·삭제, 재시도, 고정 조문, Top-k |
| test_consultation_room | 17 | 상담실 채팅 AppTest: 분야 안내·상담실 안 분야 선택, 처음으로·상담실로·다른 조문 고르기 이동, 상담 약속 문구, 대화 누적·마스킹, 이어 묻기 안내, 새 상담 스레드, 지난 상담 복구·삭제, 체크리스트 요약·오른쪽 패널 전환·용어 풀이 |
| test_glossary | 7 | 체크리스트 용어 풀이: 등장 순서, 긴 용어 우선, 조문식 표현 연결, 중복 제거 |
| test_retrieval | 13 | 검색어 확장·규칙(유류분 포함), RRF, 판례 재정렬 |
| test_issue_checklist | 11 | 체크리스트 파싱·항목 단위 검증·재시도 |
| test_statute_items | 11 | 조문 카탈로그, 조건 탐색 |
| test_redaction | 8 | 개인정보 마스킹, 추가 단어 증폭 방지 |
| test_web_api | 7 | F2013 API 요청·응답·오류 처리 |
| test_mmr | 7 | MMR 선택, 검색 방식 |
| test_config | 6 | `.env` 설정, 검색어 변환 모델 기본값 |
| test_streamlit_ui | 8 | 화면 문구, 조문별 대화 분리, 데이터셋 manifest 숫자 읽기 |
| test_citations | 6 | 인용 검증 |
| test_case_enrichment | 6 | 판례 보강, 선택·탈락 기록, 캐시 |
| test_chunking | 5 | 조문 청킹, 삭제 조문 제외 |
| test_case_selection | 5 | 판례 후보 선별 프롬프트 |
| 그 외 11개 모듈 | 33 | 수집기, 데이터셋, 색인, 평가, 데이터 현황 |

### 4.2 평가 지표

| 평가 | 문항 | 지표 | 결과 |
|---|---:|---|---|
| 법령 검색 | 30 | Recall@5 / MRR | 1.000 / 0.740 (검색어 변환 nano 때 1.000 / 0.781) |
| 판례 검색 | 30 | Recall@5 / MRR / 오염률@5 | 0.933 / 0.673 / 0.555 (이전 0.900 / 0.681 / 0.527) |
| End-to-End | 30 | 답변 성공률 / 인용 정확성 / 근거 없는 주장 차단률 / 거부 정확성 | 0.667 / 1.000 / 1.000 / 1.000 (이전 0.750 / 1.000 / 1.000 / 1.000) |
| RAG 전후 비교 | 6 | 사실 정확성 (RAG 미사용 → 사용) | 1차 4/6, 2차 5/6 → 두 번 모두 답한 5개 정확 + 1개 올바르게 거부 |

현재 결과 파일은 `data/evaluation/*_fast_query.json`(삭제 조문 제외·제1112조 규칙·검색어 변환 `gpt-5.4-mini` 반영), 이전 결과는 `statute_retrieval_results.json`, `case_retrieval_optimized.json`, `end_to_end_results_final.json`이다. 판례 평가는 질문 시 보강된 판례를 포함한 로컬 색인 기준이다. 정답 라벨은 개발자가 작성했고 법률 전문가 검수 전이다. 판례 라벨의 자동 사전 감사는 오류 0건이다 ([case-evaluation-label-audit.md](case-evaluation-label-audit.md)).

## 5. 제출 전 점검 (명세서 4.8)

| 항목 | 상태 |
|---|---|
| 필수 기능 F2001~F2012가 모두 동작 | 완료 |
| 선택한 심화 기능이 동작하고 필수 기능 결과와 비교 | 완료 (F2014 유사도 대비, F2015 RAG 미사용 대비) |
| 증명용 스크린샷 첨부 | 완료 (위 화면 6장 + 아키텍처) |
| 요구사항 정의서·RAG 파이프라인 설계문서·소스코드·README.md | 완료 ([requirements-definition.md](requirements-definition.md), [rag-pipeline-design.md](rag-pipeline-design.md)) |
| 검증 결과(요구사항 대조표, 테스트 결과표, 셀프·상호 체크리스트) | 대조표·결과표 완료, 셀프·상호 체크리스트는 3일차 오후 배포 후 작성 |

## 6. 셀프·상호 체크리스트

3일차 오후에 배포되는 체크리스트로 작성한다. 상호 점검 결과(점검자, 점검일, 지적 사항, 반영 여부)를 이 절에 추가한다.

## 7. 남은 항목

| 항목 | 상태 | 비고 |
|---|---|---|
| F2013 HTML/CSS/JS 프론트엔드 | 완료 | 2026-10-22 구현 |
| NF2001 응답 시간 | 완료 | 31.8~64.0초 → 8.3~16.7초. 대신 검색 품질 소폭 하락(4.2절) |
| 삭제된 조문 4건 색인 제외 | 완료 | 청킹 단계 제외, 재색인 382건 |
| 유류분 질문에서 민법 제1112조 미검색 | 완료 | 검색어 규칙 추가, 실제 색인에서 1위 |
| 검색어 변환 모델 결정 | 완료 | 속도를 우선해 `gpt-5.4-mini` 유지. 법령 MRR 0.740, E2E 0.667을 감수. 프롬프트 보강(용어 6~10개)은 MRR 0.708로 더 낮아 되돌림 |
| 법률 전문가 라벨 검수 | 대기 | [case-evaluation-review-sheet.md](case-evaluation-review-sheet.md) 서명 필요 |
| 셀프·상호 체크리스트 | 대기 | 3일차 오후 배포 |
| 최종 UI 화면 캡처 | 완료 | 2026-10-22 실제 서버에서 Streamlit 9장 재캡처(첫 화면, 답변, 체크리스트, 이어지는 질문, 지난 상담, 마스킹, 거부, 조건 탐색, 조문 채팅). 웹 화면은 변경 없어 기존 캡처 유지 |
| 답변에 프롬프트 용어 `CONTEXT` 노출 | 알려진 한계 | 근거가 부족한 부분을 설명할 때 "CONTEXT에 없습니다"처럼 내부 용어가 나오는 경우가 있음. 인용 검증과 결론에는 영향 없음. 고치려면 답변 프롬프트 수정과 재평가가 필요 |
| 제출 형식 확인 | 확인 필요 | 명세서는 `AI코어프로젝트2_[주제명]_지역_반_성명.zip`을 lab.ssafy.com에 업로드, 안내받은 방식은 GitLab 레포. zip은 `git archive`로 생성 |
