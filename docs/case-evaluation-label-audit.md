# 판례 평가셋 라벨 사전 감사

> 이 문서는 평가셋의 파일·사건번호·카테고리·공식 URL 일관성을 자동 검사한 결과다. 법률적 관련성, 판례의 변경·폐기 여부, 최신·상급심 판례 누락 여부에 대한 전문가 승인을 대체하지 않는다.

## 검사 결과

- 기계적 검사: **pass**
- 평가 문항: **30개**
- 원본 판례: **50개**
- 고유 ID: **30개**
- 도메인별 문항: `{'housing_lease': 10, 'inheritance': 10, 'labor': 10}`
- 검수 상태: `{'developer_labeled': 30}`
- 오류: **0개** · 경고: **2개**

자동 검사 범위는 다음과 같다.

- 30문항 및 도메인별 10문항 구성
- 문항 ID 중복 여부
- 기대·허용 사건번호의 원본 데이터 존재 여부
- 평가 문항과 판례의 카테고리 일치 여부
- 국가법령정보 공식 원문 URL 여부
- 검수 상태 값과 기대·허용 사건번호 중복 여부

## 문항별 원문 연결

| ID | 질문 | 기대 판례 | 허용 판례 | 기계 검사 | 전문가 상태 |
|---|---|---|---|---|---|
| labor-01 | 계약기간이 이미 끝난 뒤에도 노동위원회에 부당해고 구제를 신청할 실익이 있나요? | [2025두33276 · 대법원 · 2025-10-16](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612851) | [2023누60218 · 서울고등법원 · 2024-08-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605563)<br>[2022누56601 · 서울고등법원 · 2023-12-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241399) | pass | developer_labeled |
| labor-02 | 회사가 해고한 동안 다른 직장에서 번 돈은 해고기간 임금이나 손해액에서 공제되나요? | [2025나11545 · 수원고법 · 2025-12-17](https://www.law.go.kr/LSW/precInfoP.do?precSeq=622235) | [2023누60218 · 서울고등법원 · 2024-08-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605563)<br>[2022누56601 · 서울고등법원 · 2023-12-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241399) | pass | developer_labeled |
| labor-03 | 공익신고를 했다는 이유로 해고당했다면 징벌적 손해배상을 청구할 때 중간수입은 어떻게 계산하나요? | [2025나11545 · 수원고법 · 2025-12-17](https://www.law.go.kr/LSW/precInfoP.do?precSeq=622235) | - | pass | developer_labeled |
| labor-04 | 노동위원회가 내린 부당해고 재심판정을 법원에서 취소해 달라고 다툰 사례를 찾고 싶어요. | [2023누60218 · 서울고등법원 · 2024-08-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605563) | [2022누56601 · 서울고등법원 · 2023-12-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241399)<br>[2025두33276 · 대법원 · 2025-10-16](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612851) | pass | developer_labeled |
| labor-05 | 회사 측이 중앙노동위원회의 부당해고 구제판정을 취소해 달라고 소송한 판례가 있나요? | [2022누56601 · 서울고등법원 · 2023-12-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241399) | [2023누60218 · 서울고등법원 · 2024-08-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605563)<br>[2025두33276 · 대법원 · 2025-10-16](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612851) | pass | developer_labeled |
| labor-06 | 여러 근로자가 회사에 월별 미지급 임금을 청구한 판례를 알려주세요. | [2023나2058221 · 서울고등법원 · 2025-05-30](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619303) | [2022나54724 · 서울남부지방법원 · 2023-08-17](https://www.law.go.kr/LSW/precInfoP.do?precSeq=239681) | pass | developer_labeled |
| labor-07 | 건설현장에서 근로자 임금을 지급하지 않아 근로기준법 위반으로 처벌된 사례가 있나요? | [2023고단584 · 의정부지방법원 남양주지원 · 2024-06-26](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615823) | [2024노2125 · 의정부지방법원 · 2025-02-11](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615825) | pass | developer_labeled |
| labor-08 | 근로기준법 위반 사건의 항소심에서 원심 형을 파기한 판례를 찾고 있어요. | [2024노2125 · 의정부지방법원 · 2025-02-11](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615825) | [2023고단584 · 의정부지방법원 남양주지원 · 2024-06-26](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615823)<br>[2021노904(분리) · 서울서부지방법원 · 2024-02-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241141) | pass | developer_labeled |
| labor-09 | 임금 미지급 혐의로 유죄를 받았지만 항소심에서 무죄가 선고된 근로기준법 판례가 있나요? | [2021노904(분리) · 서울서부지방법원 · 2024-02-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=241141) | [2024노2125 · 의정부지방법원 · 2025-02-11](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615825) | pass | developer_labeled |
| labor-10 | 퇴직 후 받지 못한 임금과 지연손해금을 청구한 민사 판례를 알려주세요. | [2022나54724 · 서울남부지방법원 · 2023-08-17](https://www.law.go.kr/LSW/precInfoP.do?precSeq=239681) | [2023나2058221 · 서울고등법원 · 2025-05-30](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619303) | pass | developer_labeled |
| housing-01 | 전세보증보험에 가입했는데 집을 돌려주기 전에도 보증금과 지연손해금을 받을 수 있나요? | [2026다201978 · 대법원 · 2026-06-24](https://www.law.go.kr/LSW/precInfoP.do?precSeq=622971) | [2025다207128 · 대법원 · 2025-09-11](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618187) | pass | developer_labeled |
| housing-02 | 임대인이 사망한 뒤 상속인들과 임대차를 연장하면 보증금 반환 책임과 단순승인은 어떻게 되나요? | [2025다220329 · 대법원 · 2026-05-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=621911) | - | pass | developer_labeled |
| housing-03 | 상가 임대차가 끝난 뒤 건물 주인이 바뀌어도 새 주인에게 보증금을 청구할 수 있나요? | [2023다307116 · 대법원 · 2026-04-09](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619451) | - | pass | developer_labeled |
| housing-04 | 임차인이 주민등록을 잘못했다면 주택임대차 대항력이 인정되는지 궁금합니다. | [2025다213466 · 대법원 · 2026-01-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615767) | [2025다210305 · 대법원 · 2026-02-26](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618185) | pass | developer_labeled |
| housing-05 | 법인 직원이 임차주택에 살다가 퇴거하면 법인 임차인의 대항력과 우선변제권이 없어지나요? | [2025다210305 · 대법원 · 2026-02-26](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618185) | [2025다213466 · 대법원 · 2026-01-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615767) | pass | developer_labeled |
| housing-06 | 공인중개사가 전세보증금을 돌려받기 어려운 위험을 설명하지 않은 경우 배상받을 수 있나요? | [2024다305087 · 대법원 · 2025-12-04](https://www.law.go.kr/LSW/precInfoP.do?precSeq=613167) | - | pass | developer_labeled |
| housing-07 | 임대차가 끝난 뒤 보증금을 받을 때까지 계약이 계속되는 것으로 볼 수 있는 보험금 판례가 있나요? | [2025다207128 · 대법원 · 2025-09-11](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618187) | [2026다201978 · 대법원 · 2026-06-24](https://www.law.go.kr/LSW/precInfoP.do?precSeq=622971)<br>[2023다307116 · 대법원 · 2026-04-09](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619451) | pass | developer_labeled |
| housing-08 | 우선변제를 받으려고 실제로 살지 않으면서 임대차 모양만 만든 경우 대항력이 있나요? | [2024다268508 · 대법원 · 2025-08-14](https://www.law.go.kr/LSW/precInfoP.do?precSeq=615697) | [2022도3103 · 대법원 · 2025-01-09](https://www.law.go.kr/LSW/precInfoP.do?precSeq=600289) | pass | developer_labeled |
| housing-09 | 이사해서 점유를 잃은 뒤 임차권등기를 하면 다시 대항력이 생기나요? | [2024다326398 · 대법원 · 2025-04-15](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605771) | [2024마8598 · 대법원 · 2025-04-15](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612117)<br>[2024다221455 · 대법원 · 2025-04-24](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605931) | pass | developer_labeled |
| housing-10 | 보증금을 못 받은 채 이미 이사했어도 주택임차권등기명령을 신청할 수 있나요? | [2024마8598 · 대법원 · 2025-04-15](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612117) | [2024다326398 · 대법원 · 2025-04-15](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605771)<br>[2024다221455 · 대법원 · 2025-04-24](https://www.law.go.kr/LSW/precInfoP.do?precSeq=605931) | pass | developer_labeled |
| inheritance-01 | 부모가 남긴 임대차계약을 상속인들이 연장하면 상속재산 처분으로 보아 단순승인이 되나요? | [2025다220329 · 대법원 · 2026-05-08](https://www.law.go.kr/LSW/precInfoP.do?precSeq=621911) | - | pass | developer_labeled |
| inheritance-02 | 소송 도중 상속포기가 수리된 자녀를 망인의 소송수계인으로 삼아도 되나요? | [2025다220458 · 대법원 · 2026-04-30](https://www.law.go.kr/LSW/precInfoP.do?precSeq=620419) | - | pass | developer_labeled |
| inheritance-03 | 채무자가 파산한 뒤 사망하면 상속인이 자동으로 한정승인한 것으로 볼 수 있나요? | [2024그834 · 대법원 · 2026-04-10](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619467) | [2024그775 · 대법원 · 2026-06-16](https://www.law.go.kr/LSW/precInfoP.do?precSeq=623027) | pass | developer_labeled |
| inheritance-04 | 한정승인자가 가등기권자에게 본등기를 해준 것이 다른 상속채권자에 대한 부당변제인가요? | [2023다267355 · 대법원 · 2026-04-02](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618665) | - | pass | developer_labeled |
| inheritance-05 | 상속받은 재산이 전혀 없는데도 돌아가신 분의 국세와 지방세를 납부해야 하나요? | [2024그775 · 대법원 · 2026-06-16](https://www.law.go.kr/LSW/precInfoP.do?precSeq=623027) | [2024그834 · 대법원 · 2026-04-10](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619467) | pass | developer_labeled |
| inheritance-06 | 산재 장해급여를 받을 유족도 사망했다면 그 미지급 급여가 다시 상속인에게 상속되나요? | [2024두39189 · 대법원 · 2026-03-12](https://www.law.go.kr/LSW/precInfoP.do?precSeq=618535) | [2023구단73901 · 서울행법 · 2024-08-21](https://www.law.go.kr/LSW/precInfoP.do?precSeq=242119) | pass | developer_labeled |
| inheritance-07 | 상속포기를 했는데 오래된 판결을 근거로 채권자가 강제집행하려는 경우 막을 수 있나요? | [2025나20009 · 광주고등법원 · 2025-10-01](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619483) | [2025다220458 · 대법원 · 2026-04-30](https://www.law.go.kr/LSW/precInfoP.do?precSeq=620419) | pass | developer_labeled |
| inheritance-08 | 상속받았다는 이유로 이전된 부동산 등기를 말소해 달라는 소송 판례를 찾고 싶어요. | [2022가단67571 · 제주지방법원 · 2025-02-07](https://www.law.go.kr/LSW/precInfoP.do?precSeq=619231) | - | pass | developer_labeled |
| inheritance-09 | 신탁된 부동산을 상속받은 경우 취득세 부과가 적법한지 다룬 판례가 있나요? | [2023구단62970 · 서울행정법원 · 2024-10-25](https://www.law.go.kr/LSW/precInfoP.do?precSeq=612935) | - | pass | developer_labeled |
| inheritance-10 | 공동담보 부동산 일부를 상속한 뒤 경매 배당에 이의를 제기한 사례가 있나요? | [2024가단116437 · 서울북부지법 · 2024-09-05](https://www.law.go.kr/LSW/precInfoP.do?precSeq=242115) | - | pass | developer_labeled |

## 외부 검수자가 확인할 항목

- 질문의 사실관계와 기대 판례의 핵심 쟁점이 직접 연결되는가
- 허용 판례가 Top-5 정답으로 인정될 만큼 관련성이 있는가
- 더 최신이거나 권위 있는 대법원·전원합의체 판례가 누락되지 않았는가
- 후속 판례로 변경·제한·폐기된 법리가 없는가
- 검수 결과와 수정 사유를 `case-evaluation-review-sheet.md`에 기록했는가

외부 검수와 서명이 끝날 때까지 JSON의 `review_status`는 `developer_labeled`로 유지한다.
