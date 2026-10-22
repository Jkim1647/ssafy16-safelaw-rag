import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.citations import CaseEvidence, EvidenceQuote, GroundedClaim, StatuteEvidence
from legal_rag.rag.issue_checklist import ChecklistItem, IssueChecklist
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer
from legal_rag.web.api import WebServices, create_app


STATUTE = StatuteEvidence(1, "labor-27", "근로기준법", "제27조", "해고사유 등의 서면통지",
                          "해고사유와 해고시기를 서면으로 통지하여야 한다.", "https://www.law.go.kr/법령/근로기준법/제27조")
CASE = CaseEvidence(2, "case-1", "1", "2022누56601", "서울고등법원", "2023-12-21", ("법원의 판단",),
                    "카카오톡 공지는 서면통지가 아니다.", "https://www.law.go.kr/LSW/precInfoP.do?precSeq=1")


class FakePipeline:
    def __init__(self, status=AnswerStatus.ANSWERED):
        self.status = status
        self.received = None

    def answer_with_evidence(self, question, *, category, top_k):
        self.received = (question, category, top_k)
        answer = GroundedAnswer(
            status=self.status,
            content="## 상황에 대한 법령·판례 안내\n\n서면통지가 필요합니다. [근거 1]",
            sources=(STATUTE, CASE) if self.status is AnswerStatus.ANSWERED else (),
            retrieved_count=2,
        )
        return answer, (STATUTE, CASE)


class FakeChecklistBuilder:
    def __init__(self):
        self.calls = 0

    def build(self, question, category, evidence):
        self.calls += 1
        claim = GroundedClaim("서면 통지 여부", (1,), (EvidenceQuote(1, "해고사유와 해고시기를 서면으로 통지"),))
        return IssueChecklist(AnswerStatus.ANSWERED, items=(ChecklistItem(claim, "contradicted", "문서를 받았나요?"),),
                              sources=(STATUTE,), dropped_count=1)


def client(pipeline=None, checklist=None, ready=True):
    services = WebServices(
        readiness=lambda: (ready, "준비됨" if ready else ".env에 GMS_KEY를 설정해 주세요."),
        pipeline=lambda: pipeline or FakePipeline(),
        checklist_builder=lambda: checklist or FakeChecklistBuilder(),
        top_k=5,
    )
    return TestClient(create_app(services))


class WebApiTests(unittest.TestCase):
    def test_index_page_and_static_assets_are_served(self):
        api = client()

        page = api.get("/")
        script = api.get("/static/app.js")

        self.assertEqual(page.status_code, 200)
        self.assertIn("SafeLaw", page.text)
        self.assertIn('src="/static/app.js"', page.text)
        self.assertEqual(script.status_code, 200)

    def test_status_lists_categories_and_readiness(self):
        body = client(ready=False).get("/api/status").json()

        self.assertFalse(body["ready"])
        self.assertEqual(body["message"], ".env에 GMS_KEY를 설정해 주세요.")
        self.assertEqual([item["value"] for item in body["categories"]], [item.value for item in LegalCategory])
        self.assertTrue(all(item["examples"] for item in body["categories"]))

    def test_review_masks_question_and_returns_answer_sources_and_checklist(self):
        pipeline = FakePipeline()
        response = client(pipeline=pipeline).post("/api/review", json={
            "category": "labor",
            "question": "홍길동 팀장이 010-1234-5678로 해고를 알렸어요",
            "extra_terms": ["홍길동"],
            "include_checklist": True,
        })

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("홍길동", pipeline.received[0])
        self.assertNotIn("010-1234-5678", pipeline.received[0])
        self.assertEqual(pipeline.received[1:], (LegalCategory.LABOR, 5))
        self.assertEqual(body["redaction_count"], 2)
        self.assertEqual(body["status"], "answered")
        self.assertEqual([source["kind"] for source in body["sources"]], ["statute", "case"])
        self.assertEqual(body["checklist"]["items"][0]["label"], "상황과 다름")
        self.assertEqual(body["checklist"]["items"][0]["citations"], [1])
        self.assertEqual(body["checklist"]["dropped_count"], 1)

    def test_checklist_is_optional(self):
        builder = FakeChecklistBuilder()
        body = client(checklist=builder).post(
            "/api/review", json={"category": "labor", "question": "해고 통보", "include_checklist": False}
        ).json()

        self.assertIsNone(body["checklist"])
        self.assertEqual(builder.calls, 0)

    def test_blocked_answer_has_no_sources(self):
        body = client(pipeline=FakePipeline(AnswerStatus.INSUFFICIENT_EVIDENCE)).post(
            "/api/review", json={"category": "labor", "question": "점심 메뉴", "include_checklist": False}
        ).json()

        self.assertEqual(body["status"], "insufficient_evidence")
        self.assertEqual(body["status_label"], "근거 부족")
        self.assertEqual(body["sources"], [])

    def test_invalid_input_and_not_ready_return_safe_errors(self):
        invalid = client().post("/api/review", json={"category": "tax", "question": ""})
        not_ready = client(ready=False).post("/api/review", json={"category": "labor", "question": "해고"})

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(set(invalid.json()), {"error"})
        self.assertEqual(not_ready.status_code, 503)
        self.assertEqual(not_ready.json()["error"], ".env에 GMS_KEY를 설정해 주세요.")

    def test_unexpected_failure_hides_details(self):
        class BrokenPipeline:
            def answer_with_evidence(self, *args, **kwargs):
                raise KeyError("secret internal detail")

        response = client(pipeline=BrokenPipeline()).post(
            "/api/review", json={"category": "labor", "question": "해고"}
        )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()
