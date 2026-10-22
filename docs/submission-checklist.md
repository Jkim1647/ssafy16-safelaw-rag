# 최종 제출 체크리스트

## GitLab 제출물

- [x] 프로젝트 소스 코드
- [x] `.env`, API 키, 로컬 Chroma, 원시 상담 질문 Git 제외
- [x] RAG 파이프라인 설계 문서: `docs/architecture.md`
- [x] 검색 및 End-to-End 검증 결과
- [x] 데이터 출처·API·이용 조건 현황
- [x] 실행 방법, 도메인 선정 이유, 데이터 준비·색인 절차, 전체 기능을 포함한 README
- [x] README용 화면 캡처 또는 GIF 파일 추가
- [x] 4K 전체 시스템 아키텍처를 README·설계 문서에 연결
- [x] 새 환경에서 README 순서대로 설치·실행 확인
- [ ] 법률 전문가 또는 지도 리뷰어의 평가셋 라벨 검수

전문가 검수 준비 상태:

- [x] 30문항·도메인별 10문항 구성 확인
- [x] 기대·허용 사건번호 100% 원본 데이터 존재 확인
- [x] 국가법령정보 공식 원문 URL 연결
- [x] 자동 감사 오류 0건
- [ ] 실제 검수자의 질문-쟁점·최신성·후속 판례 확인 및 서명

새 환경 검증은 2026-10-22 Python 3.12에서 `pip install -e .`, 전체 73개 테스트, `streamlit`·`chromadb`·`legal_rag` import 순서로 완료했다. API 키가 필요한 실제 외부 질의는 기존 UI 점검 결과로 검증했다.

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

화면은 `scripts/capture_ui_screenshots.py`로 재생성할 수 있으며 입력 데이터는 모두 가상 사례다.

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
