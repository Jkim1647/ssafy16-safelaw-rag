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

## 프로젝트 구조

```text
AI코어프로젝트2_SafeLaw_Gwangju_03_Kimjinyoung/
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
│  ├─ raw/                        # 공식 원문(버전 관리 제외)
│  ├─ processed/                  # 정규화·청킹 결과
│  └─ indexes/                    # Vector DB 지속 데이터
└─ tests/                          # 보안·도메인·RAG 검증
```

세부 시스템 흐름은 [`docs/architecture.md`](docs/architecture.md)에 정리했습니다.

## 실행

```powershell
python -m unittest discover -s tests -v
```

## 보안 원칙

- 원문 상담 내용은 Vector DB와 파일에 저장하지 않습니다.
- 마스킹은 검색·임베딩·LLM 호출보다 먼저 수행합니다.
- 마스킹 매핑은 현재 프로세스 메모리에서만 유지하고 로그에 남기지 않습니다.
- 법령·판례 저장소와 사용자 질문 저장소를 분리합니다.
- 공식 출처의 공개·비실명 문서만 색인합니다.
