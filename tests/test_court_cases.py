import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.collectors.court_cases import (
    CaseSourceConfig, CourtCaseOpenApiClient, normalize_case,
)
from legal_rag.domain.models import LegalCategory
from legal_rag.rag.case_chunking import chunk_case


class CourtCaseCollectorTests(unittest.TestCase):
    def test_search_and_detail_are_normalized_without_credential(self):
        captured = []

        def transport(url, timeout):
            captured.append(url)
            if "lawSearch" in url:
                payload = {"PrecSearch": {"prec": [{
                    "판례일련번호": "123", "사건번호": "2024다123",
                    "사건명": "보증금반환", "법원명": "대법원", "선고일자": "2024.01.02",
                    "판결유형": "판결", "데이터출처명": "대법원",
                }]}}
            else:
                payload = {"PrecService": {"판례정보일련번호": "123", "사건번호": "2024다123",
                    "법원명": "대법원", "선고일자": "20240102", "판결유형": "판결",
                    "판시사항": "[1] 보증금 반환 쟁점", "판결요지": "임차인을 보호한다.",
                    "참조조문": "주택임대차보호법 제3조", "판례내용": "【주 문】<br/>상고를 기각한다.<br/>【이 유】<br/>판단한다."}}
            return json.dumps(payload, ensure_ascii=False).encode()

        client = CourtCaseOpenApiClient("secret", transport=transport)
        search = client.search("보증금")[0]
        document = normalize_case(client.fetch(search.case_id), LegalCategory.HOUSING_LEASE, search)

        self.assertEqual(document.result, "상고를 기각한다.")
        self.assertEqual(document.decision_date, date(2024, 1, 2))
        self.assertNotIn("secret", repr(document))
        self.assertTrue(all("OC=secret" in url for url in captured))

    def test_source_config_validates_queries(self):
        config = CaseSourceConfig.from_dict({"category": "labor", "queries": ["부당해고"]})
        self.assertEqual(config.category, LegalCategory.LABOR)
        with self.assertRaises(ValueError):
            CaseSourceConfig.from_dict({"category": "labor", "queries": []})

    def test_case_chunking_separates_sections(self):
        detail = {"판례정보일련번호": "123", "사건번호": "2024다123", "법원명": "대법원",
            "선고일자": "20240102", "판결유형": "판결", "판시사항": "[1] 쟁점",
            "판결요지": "법원의 판단이다.", "참조조문": "민법 제1조",
            "판례내용": "【주 문】<br/>상고를 기각한다.<br/>【이 유】<br/>사실관계와 판단이다."}
        chunks = chunk_case(normalize_case(detail, LegalCategory.INHERITANCE), max_chars=200)
        self.assertEqual({item.section for item in chunks}, {"issues", "reasoning", "result", "facts"})
        self.assertTrue(all("판례:" in item.embedding_text for item in chunks))


if __name__ == "__main__":
    unittest.main()
