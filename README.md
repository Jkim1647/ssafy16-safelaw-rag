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

## 프로젝트 구조

```text
ai-2_safelaw_gwangju_03_kimjinyoung/
├─ app.py                         # Streamlit 실행 진입점
├─ pyproject.toml                 # Python 패키지·테스트 설정
├─ docs/
│  └─ architecture.md             # 시스템 경계와 데이터 흐름
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
│  ├─ raw/                        # 공식 원문(버전 관리 제외)
│  ├─ processed/                  # 정규화 조문 데이터셋·생성 명세
│  └─ indexes/                    # Vector DB 지속 데이터
├─ scripts/
│  ├─ build_statute_dataset.py    # API 수집·정규화·검증용 데이터 생성
│  ├─ build_statute_chunks.py     # 조문 구조 기반 청크 생성
│  └─ build_statute_index.py      # GMS 임베딩·Chroma 색인
└─ tests/                          # 보안·도메인·RAG 검증
```

세부 시스템 흐름은 [`docs/architecture.md`](docs/architecture.md)에 정리했습니다.

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

## 보안 원칙

- 원문 상담 내용은 Vector DB와 파일에 저장하지 않습니다.
- 마스킹은 검색·임베딩·LLM 호출보다 먼저 수행합니다.
- 마스킹 매핑은 현재 프로세스 메모리에서만 유지하고 로그에 남기지 않습니다.
- 법령·판례 저장소와 사용자 질문 저장소를 분리합니다.
- 공식 출처의 공개·비실명 문서만 색인합니다.
