# Vector DB 선택 결정: Chroma 유지

## 결정

현재 SafeLaw의 제출·시연 버전은 로컬 `Chroma PersistentClient`를 유지한다. Pinecone은 기능적으로 사용할 수 있지만 현재 데이터 규모와 평가 목적에는 필수적이지 않다. 서비스가 여러 서버에서 동시에 운영되거나 팀이 하나의 원격 색인을 공유해야 할 때 재검토한다.

## 현재 조건

- 기준 색인: 법령 386청크 + 판례 652청크
- 검색 단위: `labor`, `housing_lease`, `inheritance` 메타데이터 필터
- 실행 형태: 단일 PC의 Streamlit 시연과 고정 평가셋 재현
- 색인 대상: 공개 법령·공개 판례만 저장
- 사용자 상담 원문: 마스킹 후 검색에만 사용하고 Vector DB에 저장하지 않음

## 비교

| 기준 | 로컬 Chroma | Pinecone |
|---|---|---|
| 현재 규모 | 충분함 | 가능하지만 관리형 서비스의 이점이 작음 |
| 설치·재현 | 프로젝트 안에서 즉시 재생성 가능 | 계정, API 키, 원격 인덱스 생성 필요 |
| 네트워크 장애 | 검색은 로컬에서 가능 | 모든 색인·검색에 네트워크 의존 |
| 비용·제한 | 로컬 저장공간 사용 | 플랜별 읽기·쓰기 단위와 rate limit 고려 |
| 개인정보 경계 | 법률 문서 벡터가 PC 밖으로 나가지 않음 | 업로드할 필드와 메타데이터를 별도로 통제해야 함 |
| 확장성·공동 사용 | 단일 노드 중심 | 관리형 Serverless, namespace, 원격 공동 사용에 유리 |
| 운영 보안 | OS·배포 서버 보안 책임 | API key, RBAC, private endpoint, CMEK 등의 운영 기능 제공 |

Pinecone 공식 운영 가이드는 Serverless 인덱스에 요청 제한과 플랜별 읽기·쓰기 단위 제한이 있으며, 운영 시 namespace·메타데이터 필터·재시도·모니터링을 함께 설계하도록 안내한다. 보안 기능으로 private endpoint, CMEK, RBAC, SSO, audit log 등을 제공한다. 이는 운영 환경에는 장점이지만 이번 로컬 제출판에는 추가 계정·키·네트워크 경계를 만든다.

Chroma 공식 문서는 `PersistentClient`가 지정 경로에 데이터를 저장하고 시작할 때 다시 불러오는 로컬 개발·테스트용 클라이언트라고 설명한다. 현재 프로젝트는 문서, 임베딩, 메타데이터 필터를 로컬에서 재현하는 것이 평가와 디버깅에 더 유리하다.

## Pinecone으로 전환할 조건

다음 중 하나가 생기면 `VectorStore` 포트의 Pinecone 어댑터를 추가한다.

1. Streamlit 인스턴스를 여러 대 운영해 동일 색인을 공유해야 한다.
2. 색인 규모나 질의량이 단일 노드 운영 범위를 넘어선다.
3. 팀 단위 접근 제어, 감사 로그, SLA와 백업이 필요하다.
4. 배포 서버의 로컬 디스크가 영속적이지 않다.

전환 시에도 사용자 상담 원문은 저장하지 않는다. 공개 법령·판례 청크만 업로드하고, namespace 또는 메타데이터로 문서 유형과 도메인을 분리하며, 기존과 동일한 30문항 평가로 검색 품질 회귀를 확인한다.

## 공식 참고자료

- [Pinecone production checklist](https://docs.pinecone.io/guides/production/production-checklist)
- [Pinecone index configuration](https://docs.pinecone.io/reference/api/2025-10/control-plane/configure_index)
- [Chroma Python client reference](https://docs.trychroma.com/reference/python/client)
- [Chroma architecture overview](https://docs.trychroma.com/docs/overview/architecture)
