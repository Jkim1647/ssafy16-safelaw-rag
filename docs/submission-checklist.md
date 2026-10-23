# 최종 제출 체크리스트

## 명세서 6장 산출물

- [x] 1) 요구사항 정의서: [`requirements-definition.md`](requirements-definition.md) — 기능별 요구사항 표, 도메인 조건 충족 근거
- [x] 2) RAG 파이프라인 설계문서: [`rag-pipeline-design.md`](rag-pipeline-design.md) (계층·보안 경계는 [`architecture.md`](architecture.md))
- [x] 3) 검증 결과: [`verification-results.md`](verification-results.md) — 4장 항목별 실행 결과, 요구사항 대조표, 테스트 결과표, 화면 캡처
- [ ] 3) 셀프·상호 체크리스트 — 셀프 [`self_check/`](self_check/) 작성(통과 27, 증빙 `self_check/screenshots/`), 상호 양식 [`cross_check/`](cross_check/) 준비, 점검자 작성 대기
- [x] 3) 심화 결과 비교: MMR(README), RAG 전후([`rag-before-after.md`](rag-before-after.md))
- [x] 4) 소스코드, 수집·색인 스크립트, 심화 기능 코드
- [ ] 5) 셀프 체크리스트 결과 — [`self_checklist.md`](self_check/self_checklist.md)와 배포 양식에 채운 [`self_checklist.xlsx`](self_check/self_checklist.xlsx) 작성, 작성자 최종 확인 대기
- [x] 6) README: 개요·실행 방법, 필수/심화 기능 구분, 데이터 준비·색인 절차, 출처·이용 조건, 심화 요약
- [ ] 제출 형식 확인: 명세서는 `AI코어프로젝트2_[주제명]_지역_반_성명.zip`을 lab.ssafy.com에 업로드, 안내받은 방식은 GitLab 레포. 2026-10-22 GitLab push를 제출로 판단했으나 공식 확인은 대기

## 아직 못 한 항목

- [x] F2013 HTML/CSS/JS 프론트엔드 — FastAPI + 정적 화면, [`web-api.md`](web-api.md)
- [x] NF2001 응답 시간 개선 — 31.8~64.0초 → 8.3~16.7초 (검색어 변환 모델 `gpt-5.4-mini`)
- [x] 삭제된 조문 4건(근로기준법 제35조, 주택임대차보호법 제5조, 민법 제651조·제1002조) 색인 제외 후 재색인·재평가
- [x] 유류분 질문에서 민법 제1112조가 검색되지 않는 문제 — 검색어 규칙 추가, 1위
- [x] LangGraph·FastAPI 의존성 추가 이후 새 환경 재확인 — 빈 Python 3.12 venv에서 `pip install -e .`(웹 테스트 건너뜀)과 `pip install -e ".[web]"` 모두 테스트 통과
- [x] 8501 Streamlit 최신 코드로 재시작
- [x] 검색어 변환 모델 결정 — 2026-10-22 속도를 우선해 `gpt-5.4-mini` 유지 (법령 MRR 0.781 → 0.740, E2E 0.750 → 0.667을 감수하고 응답 시간 8.3~16.7초 확보)
- [x] GitLab push — 2026-10-22 제출, 개인 GitHub(`Jkim1647/ssafy16-safelaw-rag`)와 같은 커밋으로 동기화
- [ ] 법률 전문가 또는 지도 리뷰어의 평가셋 라벨 검수

## GitLab 제출물

- [x] 프로젝트 소스 코드
- [x] `.env`, API 키, 로컬 Chroma, 원시 상담 질문 Git 제외
- [x] RAG 파이프라인 설계 문서: `docs/rag-pipeline-design.md`, `docs/architecture.md`
- [x] 검색 및 End-to-End 검증 결과
- [x] 데이터 출처·API·이용 조건 현황
- [x] 실행 방법, 도메인 선정 이유, 데이터 준비·색인 절차, 전체 기능을 포함한 README
- [x] README용 화면 캡처 또는 GIF 파일 추가
- [x] 4K 전체 시스템 아키텍처를 README·설계 문서에 연결
- [x] 새 환경에서 README 순서대로 설치·실행 확인 (2026-10-22 LangGraph 추가 후 새 venv에서 재확인, 당시 테스트 125개 / 2026-10-23 `.env`·색인 없는 깨끗한 checkout에서 전체 177개 재실행)
- [ ] 법률 전문가 또는 지도 리뷰어의 평가셋 라벨 검수

전문가 검수 준비 상태:

- [x] 30문항·도메인별 10문항 구성 확인
- [x] 기대·허용 사건번호 100% 원본 데이터 존재 확인
- [x] 국가법령정보 공식 원문 URL 연결
- [x] 자동 감사 오류 0건
- [ ] 실제 검수자의 질문-쟁점·최신성·후속 판례 확인 및 서명

새 환경 검증은 2026-10-22 Python 3.12에서 `pip install -e .`, 전체 테스트, `streamlit`·`chromadb`·`legal_rag` import 순서로 완료했다. LangGraph 의존성을 추가한 뒤 빈 venv에서 다시 확인해 125개 테스트가 통과했다. API 키가 필요한 실제 외부 질의는 기존 UI 점검 결과로 검증했다.

전문가 검수용 30문항 서명표는 `docs/case-evaluation-review-sheet.md`에 준비했고, 자동 사전 감사 결과와 공식 원문 링크는 `docs/case-evaluation-label-audit.md`에 생성했다. 검수자 서명과 수정 의견을 받기 전에는 전문가 검수 항목을 완료 처리하지 않는다.

## 실제 UI 점검 결과

2026-10-22 로컬 Streamlit에서 다음 시나리오를 확인했다.

| 시나리오 | 기대 결과 | 확인 결과 |
|---|---|---|
| 카카오톡 해고·서면 미통지 | 법령·판례 답변과 공식 링크 | `answered`, 근로기준법 제27·26·28조와 서울고법 2022누56601 표시 |
| 가상 이름·전화번호·주소 포함 | 외부 호출 전 마스킹 | 마스킹 1건 표시, 원문을 색인하지 않음 |
| 생성 인용문 불일치 | 생성 문장 차단 | `invalid_citations`, 고정 차단 문구 표시 |
| 점심 메뉴 질문 | 법률 답변 거부 | `insufficient_evidence`, 근거 부족 문구 표시 |

화면 캡처에는 실제 개인정보나 API 키를 사용하지 않는다. 정상 답변, 개인정보 마스킹 상태, 근거 부족 거부 상태를 각각 캡처하고 README의 기능 설명 아래에 상대 경로로 연결한다.

사용자 승인 후 로컬 Chrome DevTools Protocol을 이용해 다음 세 화면을 `docs/assets/`에 저장하고 README에 연결했다.

- `safelaw-grounded-answer.png`: 카카오톡 해고 질문의 `answered` 답변과 근거 링크
- `safelaw-privacy-mask.png`: 가상 전화번호 입력 후 개인정보 마스킹 건수
- `safelaw-refusal.png`: 점심 메뉴 질문의 `insufficient_evidence` 화면

화면은 `scripts/capture_ui_screenshots.py`로 재생성할 수 있으며 입력 데이터는 모두 가상 사례다. 2026-10-22 최종 UI(로펌 상담실 테마, 접수 카드, 오른쪽 체크리스트 패널, 지난 상담, 처음으로 버튼)로 Streamlit 화면 9장을 실제 서버에서 다시 캡처했다.

## 기술 결정

- [x] Chroma와 Pinecone의 현재 요구사항 적합성 비교
- [x] 제출판은 로컬 Chroma 유지, 운영 확장 시 Pinecone 재검토

결정 근거는 `docs/vector-store-decision.md`에 기록했다.

## 제출 직전 명령

```powershell
# 자동 테스트
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# 비밀값·로컬 산출물 추적 여부
git status --short
git ls-files .env "data/indexes/**" "data/raw/**"

# 최종 커밋 확인
git log -1 --oneline
```

README에 화면 자료를 추가한 뒤 마지막 체크를 완료하고 GitLab 저장소에 푸시한다.
