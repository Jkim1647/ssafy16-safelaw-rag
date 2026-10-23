import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.citations import CitationValidationError, StatuteEvidence
from legal_rag.rag.issue_checklist import IssueChecklistBuilder, parse_issue_checklist
from legal_rag.rag.pipeline import AnswerStatus


EVIDENCE = (
    StatuteEvidence(
        citation_id=1,
        chunk_id="labor-27",
        law_name="근로기준법",
        article_no="제27조",
        article_title="해고사유 등의 서면통지",
        text="사용자는 근로자를 해고하려면 해고사유와 해고시기를 서면으로 통지하여야 한다.",
        source_url="https://www.law.go.kr/법령/근로기준법/제27조",
    ),
    StatuteEvidence(
        citation_id=2,
        chunk_id="labor-26",
        law_name="근로기준법",
        article_no="제26조",
        article_title="해고의 예고",
        text="사용자는 근로자를 해고하려면 적어도 30일 전에 예고를 하여야 한다.",
        source_url="https://www.law.go.kr/법령/근로기준법/제26조",
    ),
)


def item(text, status, question, citation_id, quote):
    return {
        "text": text,
        "status": status,
        "check_question": question,
        "citations": [citation_id],
        "evidence_quotes": [{"citation_id": citation_id, "quote": quote}],
    }


def checklist_response(*items):
    return json.dumps({"answerable": True, "items": list(items)}, ensure_ascii=False)


VALID = checklist_response(
    item("해고사유와 해고시기를 서면으로 통지했는지", "contradicted",
         "해고 사유와 날짜가 적힌 문서를 받았나요?", 1, "해고사유와 해고시기를 서면으로 통지"),
    item("30일 전에 해고를 예고했는지", "unknown",
         "해고 통보를 받은 날과 마지막 근무일 사이가 30일 이상인가요?", 1 + 1, "적어도 30일 전에 예고를 하여야"),
)


class FakeLlm:
    def __init__(self, *responses, error=None):
        self.responses = list(responses)
        self.error = error
        self.calls = 0
        self.messages = None

    def invoke(self, messages):
        self.calls += 1
        self.messages = messages
        if self.error:
            raise self.error
        return self.responses.pop(0)


class ParseIssueChecklistTests(unittest.TestCase):
    def test_parses_items_with_status_question_and_citations(self):
        parsed = parse_issue_checklist(VALID, EVIDENCE)
        items = parsed.items

        self.assertEqual([entry.status for entry in items], ["contradicted", "unknown"])
        self.assertEqual(items[0].claim.citation_ids, (1,))
        self.assertEqual(items[1].claim.citation_ids, (2,))
        self.assertEqual(items[0].check_question, "해고 사유와 날짜가 적힌 문서를 받았나요?")
        self.assertEqual(parsed.dropped_count, 0)

    def test_drops_only_items_that_fail_validation(self):
        raw = checklist_response(
            item("서면 통지", "unknown", "문서를 받았나요?", 1, "해고사유와 해고시기를 서면으로 통지"),
            item("구두 해고", "unknown", "말로 들었나요?", 1, "해고는 구두로도 효력이 있다"),
            item("결과", "won", "이겼나요?", 2, "적어도 30일 전에 예고를 하여야"),
        )

        parsed = parse_issue_checklist(raw, EVIDENCE)

        self.assertEqual([entry.claim.text for entry in parsed.items], ["서면 통지"])
        self.assertEqual(parsed.dropped_count, 2)

    def test_answerable_false_returns_none(self):
        self.assertIsNone(parse_issue_checklist('{"answerable": false}', EVIDENCE))

    def test_rejects_unknown_status(self):
        raw = checklist_response(item("요건", "won", "확인할 질문인가요?", 1, "해고사유와 해고시기를 서면으로 통지"))

        with self.assertRaises(CitationValidationError):
            parse_issue_checklist(raw, EVIDENCE)

    def test_rejects_quote_missing_from_evidence(self):
        raw = checklist_response(item("요건", "unknown", "확인할 질문인가요?", 1, "해고는 구두로도 효력이 있다"))

        with self.assertRaises(CitationValidationError):
            parse_issue_checklist(raw, EVIDENCE)

    def test_rejects_internal_prompt_term_in_check_question(self):
        raw = checklist_response(
            item("요건", "unknown", "CONTEXT에 나온 문서를 받았나요?", 1, "해고사유와 해고시기를 서면으로 통지")
        )

        with self.assertRaisesRegex(CitationValidationError, "내부 용어"):
            parse_issue_checklist(raw, EVIDENCE)

    def test_rejects_empty_question_and_empty_items(self):
        with self.assertRaises(CitationValidationError):
            parse_issue_checklist(
                checklist_response(item("요건", "unknown", " ", 1, "해고사유와 해고시기를 서면으로 통지")), EVIDENCE
            )
        with self.assertRaises(CitationValidationError):
            parse_issue_checklist(checklist_response(), EVIDENCE)


class IssueChecklistBuilderTests(unittest.TestCase):
    def test_builds_checklist_with_only_cited_sources(self):
        raw = checklist_response(
            item("서면 통지 여부", "unknown", "문서를 받았나요?", 1, "해고사유와 해고시기를 서면으로 통지"),
        )
        llm = FakeLlm(raw)

        checklist = IssueChecklistBuilder(llm).build("[PERSON_1]이 카톡으로 해고", LegalCategory.LABOR, EVIDENCE)

        self.assertEqual(checklist.status, AnswerStatus.ANSWERED)
        self.assertEqual([source.citation_id for source in checklist.sources], [1])
        self.assertIn("[PERSON_1]이 카톡으로 해고", llm.messages[-1]["content"])
        self.assertIn("해고의 예고", llm.messages[-1]["content"])

    def test_retries_once_after_validation_failure(self):
        llm = FakeLlm("{invalid", VALID)

        checklist = IssueChecklistBuilder(llm).build("해고 통보", LegalCategory.LABOR, EVIDENCE)

        self.assertEqual(checklist.status, AnswerStatus.ANSWERED)
        self.assertEqual(checklist.attempts, 2)
        self.assertIn("직전 응답은 폐기됐다", llm.messages[-1]["content"])

    def test_blocks_after_repeated_validation_failure(self):
        llm = FakeLlm("{invalid", "{still invalid")

        checklist = IssueChecklistBuilder(llm).build("해고 통보", LegalCategory.LABOR, EVIDENCE)

        self.assertEqual(checklist.status, AnswerStatus.INVALID_CITATIONS)
        self.assertEqual(checklist.items, ())

    def test_insufficient_evidence_and_generation_failure(self):
        insufficient = IssueChecklistBuilder(FakeLlm('{"answerable": false}')).build(
            "점심 메뉴", LegalCategory.LABOR, EVIDENCE
        )
        failed = IssueChecklistBuilder(FakeLlm(error=RuntimeError("down"))).build(
            "해고 통보", LegalCategory.LABOR, EVIDENCE
        )

        self.assertEqual(insufficient.status, AnswerStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(failed.status, AnswerStatus.GENERATION_FAILED)

    def test_does_not_call_llm_without_evidence(self):
        llm = FakeLlm(VALID)

        checklist = IssueChecklistBuilder(llm).build("해고 통보", LegalCategory.LABOR, ())

        self.assertEqual(checklist.status, AnswerStatus.NO_EVIDENCE)
        self.assertEqual(llm.calls, 0)


if __name__ == "__main__":
    unittest.main()
