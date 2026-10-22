# 데이터·외부 API 현황

> 문서 기준일: 2026-10-21. 이 문서는 `python scripts/generate_data_source_inventory.py`로 manifest와 수집 설정에서 다시 생성한다.

## 한눈에 보는 외부 연동

| 구분 | 제공자·용도 | 요청 주소 | 인증값 | 저장 여부 |
|---|---|---|---|---|
| 현행법령 목록 | 법제처 국가법령정보 공동활용 | `GET https://www.law.go.kr/DRF/lawSearch.do` | `LAW_API_OC` | 응답을 조문 단위로 정규화 |
| 현행법령 본문 | 법제처 국가법령정보 공동활용 | `GET https://www.law.go.kr/DRF/lawService.do` | `LAW_API_OC` | 필요한 조문과 메타데이터 저장 |
| 판례 목록 | 법제처 국가법령정보 공동활용, 데이터출처 대법원 | `GET https://www.law.go.kr/DRF/lawSearch.do` | `LAW_API_OC` | 필터 통과 사건 식별자만 사용 |
| 판례 본문 | 법제처 국가법령정보 공동활용, 데이터출처 대법원 | `GET https://www.law.go.kr/DRF/lawService.do` | `LAW_API_OC` | 공개·비실명 판례를 정규화 |
| 임베딩 | SSAFY GMS OpenAI 호환 API | `POST https://gms.ssafy.io/gmsapi/api.openai.com/v1/embeddings` | `GMS_KEY` | 응답 벡터를 로컬 Chroma에 저장 |
| 검색어 변환 | SSAFY GMS OpenAI 호환 API | `POST https://gms.ssafy.io/gmsapi/api.openai.com/v1/chat/completions` | `GMS_KEY` | 응답 원문 미저장, 검색계획만 사용 |
| 근거 답변 생성 | SSAFY GMS OpenAI 호환 API | `POST https://gms.ssafy.io/gmsapi/api.openai.com/v1/chat/completions` | `GMS_KEY` | 검증을 통과한 답변만 화면 표시 |
| Vector DB | Chroma 로컬 저장소 | 네트워크 API 없음 | 없음 | 법령·판례 컬렉션 분리 |

실제 키 값은 `.env`에만 두며 이 문서, 로그, 데이터셋, Git에는 기록하지 않는다.

## 국가법령정보 API 요청 규격

### 현행법령(시행일)

- 목록 공식 가이드: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide)
- 본문 공식 가이드: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide)
- 목록 요청: `target=eflaw`, `type=JSON`, `search=1`, `query=<법령명>`, `nw=3`, `display=100`, `page=1`
- 본문 요청: `target=eflaw`, `type=JSON`, `ID=<법령ID>`
- 수집 필드: 법령 ID·일련번호·법령키, 조문키, 법령명, 조문번호·제목·본문, 시행일·공포일, 소관부처, 법종구분

### 판례

- 목록 공식 가이드: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precListGuide)
- 본문 공식 가이드: [https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=precInfoGuide)
- 목록 요청: `target=prec`, `type=JSON`, `search=2`, `query=<쟁점 검색어>`, `display=<설정 상한>`, `page=1`
- 본문 요청: `target=prec`, `type=JSON`, `ID=<판례일련번호>`
- 데이터출처명이 `대법원`인 결과만 허용하고 동일 카테고리·사건번호 중복을 제거한다.
- 수집 필드: 사건번호·사건명·사건종류, 법원·선고일·판결유형, 판시사항·판결요지·주문·원문, 참조조문·참조판례, 공식 URL

## 실제 수집 범위

| 도메인 | 법령 | 수집 조문 범위 | 쟁점 태그 |
|---|---|---|---|
| labor | 근로기준법 | 전체 조문 | 근로계약, 해고, 임금, 근로시간, 직장 내 괴롭힘 |
| labor | 기간제 및 단시간근로자 보호 등에 관한 법률 | 전체 조문 | 기간제, 단시간근로자, 차별, 무기계약 전환 |
| housing_lease | 주택임대차보호법 | 전체 조문 | 주택임대차, 보증금, 대항력, 우선변제권, 계약갱신 |
| housing_lease | 민법 | 제303조~제318조, 제618조~제654조 | 임대차, 전세, 보증금, 계약해지 |
| inheritance | 민법 | 제997조~제1118조 | 상속, 유언, 상속포기, 한정승인, 유류분 |

| 도메인 | API 본문 검색어 | 검색어별 상한 |
|---|---|---|
| labor | 부당해고, 해고 서면통지, 임금 체불 | 15 |
| housing_lease | 임대차보증금 반환, 주택임대차 우선변제, 임차권등기명령 | 15 |
| inheritance | 상속포기, 한정승인, 상속 순위 | 15 |

판례 검색 결과를 그대로 저장하지 않는다. 검색어의 핵심 단어가 판시사항·판결요지·참조조문에 나타나는지 검사한 뒤 저장한다. 현재 판례 데이터는 자동 수집본이며 법률 전문가 미검수 상태다.

## 현재 산출물 현황

| 산출물 | 건수 | 생성 기준 | 무결성 |
|---|---|---|---|
| `data/processed/statutes.json` | 381개 조문 | 2026-10-21 | SHA-256 `1817cc9544b12eac3bb7ccb9b846a4b3a665b97cd23a2fc0573bd291fa6855be` |
| `data/processed/statute_chunks.json` | 382개 청크 | 최대 1200자 / 중첩 150자 | SHA-256 `2fa3e00061dd8fec4b5ed3844a4294249e8671601a89adaf0dcc88cd895b27b1` |
| `data/processed/cases.json` | 50건 | 2023-08-17~2026-06-24 선고 | SHA-256 `eda97ce49a30d993a7429796936a81cc9d10c6f36d316d52e632722771aa6343` |
| `data/processed/case_chunks.json` | 652개 청크 | 최대 1400자 / 중첩 180자 | SHA-256 `8d92761c3f4a179cad283f3a984e4988b8537c2121eba4c90f2194001e0c352a` |
| 법령 Chroma | 382개 벡터 | `data/indexes/statutes/` | 재생성 가능·Git 제외 |
| 판례 Chroma | 652개 벡터 | `data/indexes/cases/` | 재생성 가능·Git 제외 |

- 법령 카테고리: 노동 158개, 임대차 96개, 상속 127개
- 판례 카테고리: 노동 12건, 임대차 27건, 상속 11건
- 판례 권위 등급: appellate 7건, other 18건, supreme_court 25건
- 법령 검색 평가: 30문항, Recall@5 `1.000`, MRR `0.781`, Hit@5 `1.000`

## 모델과 호출 단계

| 단계 | 기본 모델 | 외부로 전달되는 데이터 |
|---|---|---|
| 문서·질문 임베딩 | `text-embedding-3-small` | 공개 법령·판례 청크 또는 마스킹된 검색문 |
| 검색어 변환 | `gpt-5-nano` | 마스킹된 질문과 선택 도메인 |
| 근거 답변 생성 | `gpt-5.4-mini` | 마스킹된 질문과 검색된 공식 근거 |

동일 Chroma 컬렉션을 만들 때 사용한 임베딩 모델과 검색할 때 사용하는 모델은 같아야 한다. 모델을 바꾸면 전체 색인을 다시 생성한다.

## 이용 조건과 법적 효력

- 공식 안내: [국가법령정보센터 법적효력·저작권](https://www.law.go.kr/lawPetitionForm.do?menuId=13&subMenuId=79)
- 국가법령정보센터 제공 정보는 편의를 위한 참고자료이며, 법적 효력은 관보 등 공식 공포 자료에 있다.
- 공개 법령정보는 관련 법령과 이용조건, 제3자 권리를 준수하는 범위에서 활용한다.
- 출처를 국가법령정보센터·법제처로 표시하고 각 답변에 공식 원문 링크를 제공한다.
- 데이터를 위조·변조하거나 법적 효력이 있는 원문인 것처럼 표시하지 않는다.
- 배포·서비스 공개 전 최신 공동활용 이용조건과 신청 범위를 다시 확인한다.

## 비밀값·개인정보·Git 정책

| 항목 | 처리 |
|---|---|
| `LAW_API_OC` | `.env`에서만 읽고 URL 로그·manifest·Git에 저장하지 않음 |
| `GMS_KEY` | `.env`에서만 읽고 예외·객체 표현·Git에 저장하지 않음 |
| 사용자 원문 | 로컬 마스킹 후 폐기, 데이터셋·Chroma에 저장하지 않음 |
| `.env` | `.gitignore` 적용 |
| `data/raw/` | 원문 임시 저장 가능성을 고려해 Git 제외 |
| `data/indexes/` | 재생성 가능한 벡터 DB로 Git 제외 |
| `data/processed/` | 공개 법률 문서 정규화본과 manifest만 Git 제출 |

## 재현 명령

```powershell
python scripts/build_statute_dataset.py
python scripts/build_statute_chunks.py
python scripts/build_statute_index.py
python scripts/build_case_dataset.py
python scripts/build_case_chunks.py
python scripts/build_case_index.py
python scripts/evaluate_statute_retrieval.py --no-resume
python scripts/generate_data_source_inventory.py
python -m unittest discover -s tests -v
```

## 제출 전 갱신 체크

- [ ] 법령·판례를 최신 API 응답으로 다시 수집했는가?
- [ ] manifest의 수집일, 건수, SHA-256이 실제 파일과 일치하는가?
- [ ] 모델명이 `.env.example`, 실행 설정, 현황 문서에서 일치하는가?
- [ ] 검색 평가를 캐시 없이 다시 실행했는가?
- [ ] `.env`, Chroma, 원시 사용자 질문이 Git에 포함되지 않았는가?
- [ ] 공식 출처와 이용 조건 링크가 README와 화면에 표시되는가?
- [ ] 판례가 자동 수집본·전문가 미검수임을 명시했는가?
