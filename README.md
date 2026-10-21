# SafeLaw

**개인정보 보호형 생활법률 판례 내비게이터**

사용자의 상황에서 개인정보를 먼저 비식별화하고, 관련 법령과 유사 판례를 찾아 판단 요소와 근거를 제시하는 RAG 서비스입니다.

## 범위

- 근로계약·부당해고
- 전세·임대차 보증금
- 상속

서비스는 승소·패소를 예측하거나 법률 자문을 제공하지 않습니다. 법령, 유사 판례, 유리·불리한 판단 요소와 추가로 확인할 사실을 근거와 함께 제시하는 것을 목표로 합니다.

## 현재 구현 단계

1. 프로젝트 공통 도메인 모델
2. LLM 호출 전 로컬 개인정보 마스킹
3. 보안 경계를 검증하는 자동화 테스트
4. 국가법령정보 현행법령 API 수집기
5. 3개 생활법률 도메인의 조문 단위 데이터셋
6. 조문 구조 기반 청킹과 GMS 임베딩·Chroma 색인 파이프라인
7. 자연어 검색어 확장·재정렬과 30문항 검색 평가셋
8. 검색 법령 한정 답변 생성과 인용·원문 문구 검증
9. 질문 입력·답변 상태·공식 근거 링크를 제공하는 Streamlit UI
10. 대법원 공개 판례 수집·정규화와 섹션 기반 청킹
11. 법령/판례 별도 Chroma 색인 및 통합 근거 답변

## 프로젝트 구조

```text
ai-2_safelaw_gwangju_03_kimjinyoung/
├─ app.py                         # Streamlit 실행 진입점
├─ pyproject.toml                 # Python 패키지·테스트 설정
├─ docs/
│  ├─ architecture.md             # 시스템 경계와 데이터 흐름
│  ├─ search-quality.md           # 평가셋·Recall@5·MRR 결과
│  ├─ model-routing.md            # 단계별 모델 분리 기준
│  └─ troubleshooting.md          # 검색 문제·원인·해결 기록
├─ src/legal_rag/
│  ├─ config.py                   # 환경변수·비밀값 설정
│  ├─ domain/                     # 순수 법률 도메인 모델
│  ├─ application/                # 사용자 요청 오케스트레이션
│  ├─ ports/                      # 외부 기술에 독립적인 인터페이스
│  ├─ collectors/                 # 법제처·대법원 공식 데이터 수집
│  ├─ rag/                        # 청킹·색인·검색·근거 검증
│  ├─ security/                   # 비식별화·출처 허용 정책
│  ├─ adapters/                   # Vector DB·GMS 구현체
│  └─ ui/                         # Streamlit 화면
├─ data/
│  ├─ statute_sources.json        # 수집 법령·카테고리·조문 범위 설정
│  ├─ case_sources.json           # 판례 본문 검색어·수집 상한 설정
│  ├─ raw/                        # 공식 원문(버전 관리 제외)
│  ├─ processed/                  # 정규화 조문 데이터셋·생성 명세
│  ├─ evaluation/                 # 검색 질문·정답과 Recall@5·MRR 결과
│  └─ indexes/                    # Vector DB 지속 데이터
├─ scripts/
│  ├─ build_statute_dataset.py    # API 수집·정규화·검증용 데이터 생성
│  ├─ build_statute_chunks.py     # 조문 구조 기반 청크 생성
│  ├─ build_statute_index.py      # GMS 임베딩·Chroma 색인
│  ├─ build_case_dataset.py       # 대법원 공개 판례 수집·정규화
│  ├─ build_case_chunks.py        # 판례 섹션 기반 청킹
│  ├─ build_case_index.py         # 별도 판례 Chroma 색인
│  ├─ search_statutes.py          # 자연어 검색어 확장·법령 검색
│  ├─ answer_statutes.py          # 근거 제한 답변 생성·검증
│  └─ evaluate_statute_retrieval.py # 고정 평가셋 검색 품질 측정
└─ tests/                          # 보안·도메인·RAG 검증
```

세부 시스템 흐름은 [`docs/architecture.md`](docs/architecture.md)에 정리했습니다.

## 실행 방법

Python 3.12 환경에서 프로젝트 의존성을 설치하고 `.env`에 `GMS_KEY`를 설정합니다. 법령 색인이 없다면 먼저 아래 색인 생성 단계까지 실행해야 합니다.

```powershell
python -m pip install -e .
streamlit run app.py
```

브라우저의 기본 주소는 `http://localhost:8501`입니다. 화면에서 다음 기능을 사용할 수 있습니다.

- 근로계약·부당해고, 전세·임대차 보증금, 상속 도메인 선택
- 최대 2,000자의 상황 입력과 추가 민감 단어 지정
- 개인정보 마스킹 건수와 답변 검증 상태 확인
- 검증된 법령 기반 답변과 국가법령정보센터 원문 링크 확인
- 근거 부족·인용 실패·외부 호출 실패 시 안전한 차단 메시지 확인

## 법령 데이터셋

국가법령정보센터의 현행법령 검색 API와 본문 API를 사용합니다. 인증값 `OC`는 환경변수로만 읽으며 URL, 로그, 데이터셋에는 저장하지 않습니다.

현재 수집 범위는 다음과 같습니다.

- 근로계약·부당해고: 근로기준법, 기간제 및 단시간근로자 보호 등에 관한 법률
- 전세·임대차 보증금: 주택임대차보호법 전체, 민법 제303조~제318조 및 제618조~제654조
- 상속: 민법 제997조~제1118조

2026-10-21 생성본은 총 381개 조문입니다: 노동 158개, 임대차 96개, 상속 127개. 각 레코드에는 법령·조문 식별자, 시행일, 공포일, 소관부처, 원문 링크가 포함됩니다.

### 데이터셋 다시 만들기

PowerShell에서 발급받은 국가법령정보 공동활용 `OC`를 현재 프로세스에만 설정한 뒤 실행합니다.

```powershell
$env:LAW_API_OC="발급받은-OC"
python scripts/build_statute_dataset.py
Remove-Item Env:LAW_API_OC
```

결과물:

- `data/processed/statutes.json`: 조문 단위 정규화 데이터
- `data/processed/statutes_manifest.json`: 건수, 법령별 통계, 생성일, SHA-256

수집 대상과 조문 범위를 바꾸려면 `data/statute_sources.json`을 수정합니다. 법령 데이터는 수시로 개정될 수 있으므로 시연·검증 전 데이터셋을 다시 생성하고 manifest의 생성일과 해시를 기록합니다.

## 청킹과 임베딩

법령은 문맥이 조문·항·호·목 단위로 구성되므로 무조건 같은 글자 수로 자르지 않습니다. 먼저 API에서 보존한 줄 단위 구조를 묶고, 1,200자를 넘는 긴 조문만 최대 150자의 문맥 중첩을 두어 나눕니다. 임베딩 입력에는 본문과 함께 도메인, 법령명, 조문 번호·제목, 쟁점 태그를 넣습니다.

```powershell
# 1. 381개 조문을 청크 데이터셋으로 변환
python scripts/build_statute_chunks.py

# 2. 의존성 설치
python -m pip install -e .

# 3. .env에 GMS_KEY를 입력한 후 임베딩·Chroma 색인 생성
python scripts/build_statute_index.py
```

현재 기본 설정은 다음과 같습니다.

- 청크 최대 길이: 1,200자
- 청크 중첩: 최대 150자
- 임베딩 모델: `text-embedding-3-small`
- Vector Store: Chroma, cosine 거리
- 법령 색인 위치: `data/indexes/statutes/` — 재생성 가능한 산출물이므로 Git 제외

현재 데이터에서는 381개 조문이 386개 청크로 변환됩니다. 길이가 기준을 넘은 5개 조문만 각각 2개로 분할됩니다. 임베딩 모델을 변경하면 기존 벡터와 차원·의미 공간이 달라지므로 전체 색인을 다시 생성합니다.

역할별 채팅 모델 배치와 임베딩 모델 혼용 시 주의점은 [`docs/model-routing.md`](docs/model-routing.md)에 정리했습니다.

## 판례 데이터셋과 색인

국가법령정보 판례 목록·본문 API에서 데이터출처가 대법원인 공개 판례만 수집합니다. 판시사항·판결요지·참조조문에 설정한 핵심 검색어가 나타나는지 확인하고 동일 사건번호 중복을 제거합니다. 현재 생성본은 50건(노동 12, 임대차 27, 상속 11), 652개 청크입니다.

판례는 사건번호, 법원, 선고일, 주문·결과, 판례 원문, 판결요지, 판시사항, 참조조문, 공식 원문 URL로 정규화합니다. 그 후 `법적 쟁점`, `법원의 판단`, `주문·결과`, `사실관계·판례 원문` 섹션을 분리하고 1,400자/180자 중첩 기준으로 청킹합니다.

또한 공식 API의 법원명과 판결유형을 이용해 `전원합의체 → 대법원 → 항소심 → 기타` 권위 등급을 저장합니다. 검색에서는 먼저 질문과 의미가 가까운 후보만 모은 뒤, 점수가 비슷한 후보 사이에서만 상급심·전원합의체 판례에 작은 가점을 줍니다. 따라서 유명하지만 질문과 무관한 판례가 관련 판례를 밀어내지 않습니다. 이 등급은 법적 구속력이나 승소 가능성을 뜻하지 않습니다.

```powershell
$env:LAW_API_OC="발급받은-OC"
python scripts/build_case_dataset.py
Remove-Item Env:LAW_API_OC
python scripts/build_case_chunks.py
python scripts/build_case_index.py
```

법령과 판례는 `data/indexes/statutes/`, `data/indexes/cases/`에 따로 저장합니다. 두 컬렉션은 독립적으로 검색하며 원시 유사도 점수를 직접 비교하지 않습니다. 최종 생성 컨텍스트에서 법령과 판례를 문서 유형으로 구분하고, 인용한 원문 문구가 실제 검색 근거에 존재할 때만 답변을 표시합니다.

## 자연어 법령 검색

사용자 질문은 로컬 개인정보 마스킹을 거친 후 검색어 확장 단계로 전달됩니다. 도메인 규칙과 GMS LLM이 일상 표현을 법률 용어로 바꾸고, 원문·재작성 질문은 가중 순위 결합에 사용합니다. 개별 법률 용어는 후보 조문을 넓게 수집하는 데 사용하며, 가장 강한 용어 신호와 조문 제목 일치도로 최종 순위를 보정합니다. 원문 질의를 함께 사용하므로 LLM이 부정확한 용어를 만들더라도 검색 신호가 하나로 고정되지 않습니다.

```powershell
python scripts/search_statutes.py `
  "회사에서 카카오톡으로 내일부터 나오지 말라고 했어요" `
  --category labor `
  --top-k 5
```

카테고리 값은 `labor`, `housing_lease`, `inheritance` 중 하나입니다. 현재 대표 질문 검증 결과와 한계는 [`docs/search-quality.md`](docs/search-quality.md)에 기록합니다.

## 검색 품질 평가

도메인별 자연어 질문 10개씩, 총 30개와 기대 법령·조문을 고정 평가셋으로 관리합니다. 각 질문의 Top-5 검색 결과로 `Recall@5`와 첫 정답 순위의 역수인 `MRR`을 계산합니다.

```powershell
# .env의 GMS_KEY와 data/indexes/statutes 색인이 필요
python scripts/evaluate_statute_retrieval.py
```

평가 산출물:

- `data/evaluation/statute_retrieval_cases.json`: 질문과 기대 조문
- `data/evaluation/statute_retrieval_results.json`: 질문별 Top-5와 최종 집계
- `data/evaluation/statute_retrieval_baseline.json`: 개선 전 기준선

현재 30문항 결과는 전체 `Recall@5 1.000`, `MRR 0.747`입니다. 이 수치는 자체 작성한 고정 평가셋에 대한 검색 성능이며, 실제 법률 판단의 정확도나 새로운 질문에 대한 일반화 성능을 뜻하지 않습니다.

RRF와 MRR의 계산 방식, 검색 품질이 악화됐던 시도와 해결 과정은 [`docs/troubleshooting.md`](docs/troubleshooting.md)에 정리했습니다.

## 근거 제한 답변 생성

검색된 법령을 CONTEXT로 전달하고 모든 주장에 근거 번호와 법령 원문의 인용문을 요구합니다. 생성 결과는 바로 표시하지 않고 다음 조건을 모두 검사합니다.

- 모든 주장에 하나 이상의 근거 번호가 있는가?
- 근거 번호가 실제 검색 결과에 존재하는가?
- 답변에서 언급한 조문 번호와 연결된 근거 조문이 일치하는가?
- 제출한 원문 인용문이 해당 검색 청크에 실제로 존재하는가?
- 출처가 국가법령정보센터의 HTTPS URL인가?

JSON 형식이나 근거 검증이 실패하면 첫 응답을 폐기하고 한 번만 다시 생성합니다. 두 번째도 실패하면 모델 문장을 노출하지 않고 고정된 차단 메시지를 반환합니다.

```powershell
python scripts/answer_statutes.py `
  "회사에서 카카오톡으로 내일부터 나오지 말라고 했어요" `
  --category labor `
  --top-k 5
```

답변 상태는 `answered`, `no_evidence`, `insufficient_evidence`, `invalid_citations`, `generation_failed` 중 하나입니다. 법률과 무관한 질문은 검색 결과가 형식적으로 존재하더라도 `insufficient_evidence`로 답변하지 않습니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## 데이터 출처와 이용 시 주의사항

- 출처: [국가법령정보 공동활용](https://open.law.go.kr/LSO/openApi/openApiManual.do)
- 검색 규격: 현행법령(시행일) 목록 조회 `target=eflaw`
- 본문 규격: 현행법령(시행일) 본문 조회 `target=eflaw`
- 서비스 공개 전 공동활용 신청 조건과 출처 표기 의무를 다시 확인합니다.
- 생성 데이터는 법률정보 검색 보조용이며 최신성·정확성을 보증하는 법률 자문이 아닙니다.
- 판례 목록·본문 규격: `target=prec`, 목록 본문검색 `search=2`

## 보안 원칙

- 원문 상담 내용은 Vector DB와 파일에 저장하지 않습니다.
- 마스킹은 검색·임베딩·LLM 호출보다 먼저 수행합니다.
- 마스킹 매핑은 현재 프로세스 메모리에서만 유지하고 로그에 남기지 않습니다.
- 법령·판례 저장소와 사용자 질문 저장소를 분리합니다.
- 공식 출처의 공개·비실명 문서만 색인합니다.
