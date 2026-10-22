import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus, StatuteRagPipeline
from legal_rag.rag.retrieval import RetrievalResult, RetrievedChunk, SearchPlan


class FakeRetriever:
    def __init__(self, hits):
        self.hits = tuple(hits)
        self.received_query = None

    def retrieve(self, sanitized_query, *, category, top_k=5):
        self.received_query = sanitized_query
        return RetrievalResult(
            plan=SearchPlan(sanitized_query, sanitized_query, (), False),
            hits=self.hits[:top_k],
        )


class FakeLlm:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0
        self.messages = None

    def invoke(self, messages):
        self.calls += 1
        self.messages = messages
        if self.error:
            raise self.error
        return self.response


class SequenceLlm:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return next(self.responses)


def evidence_hit():
    return RetrievedChunk(
        chunk_id="labor-27",
        document="사용자는 해고사유와 해고시기를 서면으로 통지하여야 한다.",
        metadata={
            "law_name": "근로기준법",
            "article_no": "제27조",
            "article_title": "해고사유 등의 서면통지",
            "source_url": "https://www.law.go.kr/법령/근로기준법/제27조",
        },
        distance=0.1,
        score=0.1,
    )


def valid_response():
    quote = [{"citation_id": 1, "quote": "해고사유와 해고시기를 서면으로 통지"}]
    return json.dumps(
        {
            "answerable": True,
            "summary": {
                "text": "제27조는 해고의 서면 통지를 요구합니다.",
                "citations": [1],
                "evidence_quotes": quote,
            },
            "issues": [
                {
                    "text": "서면 통지가 있었는지가 쟁점입니다.",
                    "citations": [1],
                    "evidence_quotes": quote,
                }
            ],
            "favorable_factors": [],
            "unfavorable_factors": [],
            "additional_facts": [],
            "next_steps": [
                {
                    "text": "통지 내용을 확인해야 합니다.",
                    "citations": [1],
                    "evidence_quotes": quote,
                }
            ],
        },
        ensure_ascii=False,
    )


class StatuteRagPipelineTests(unittest.TestCase):
    def test_does_not_call_llm_without_official_evidence(self):
        llm = FakeLlm(valid_response())
        pipeline = StatuteRagPipeline(FakeRetriever([]), llm)

        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.NO_EVIDENCE)
        self.assertEqual(llm.calls, 0)
        self.assertFalse(answer.is_answered)

    def test_returns_only_validated_grounded_answer(self):
        llm = FakeLlm(valid_response())
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)

        answer = pipeline.answer("카톡으로 해고 통지를 받았습니다", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.ANSWERED)
        self.assertIn("[근거 1]", answer.content)
        self.assertEqual(len(answer.sources), 1)
        self.assertNotIn("승소 확률", answer.content)

    def test_blocks_response_with_unknown_citation(self):
        payload = json.loads(valid_response())
        payload["summary"]["citations"] = [99]
        llm = FakeLlm(json.dumps(payload, ensure_ascii=False))
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)

        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.INVALID_CITATIONS)
        self.assertNotIn("제27조는", answer.content)
        self.assertEqual(answer.sources, ())

    def test_retries_invalid_structure_and_returns_only_valid_second_answer(self):
        llm = SequenceLlm(("{invalid json", valid_response()))
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)

        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.ANSWERED)
        self.assertEqual(llm.calls, 2)

    def test_blocks_when_model_says_evidence_is_insufficient(self):
        llm = FakeLlm('{"answerable": false}')
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)

        answer = pipeline.answer("전혀 다른 질문", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.INSUFFICIENT_EVIDENCE)
        self.assertFalse(answer.is_answered)
        self.assertEqual(llm.calls, 3)

    def test_retry_message_contains_specific_validation_failure(self):
        llm = SequenceLlm(("{invalid json", valid_response()))
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)
        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)
        self.assertEqual(answer.generation_attempts, 2)
        self.assertEqual(answer.validation_failures, 1)

    def test_third_attempt_can_repair_repeated_invalid_citations(self):
        llm = SequenceLlm(("{invalid", "{still invalid", valid_response()))
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)
        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)
        self.assertEqual(answer.status, AnswerStatus.ANSWERED)
        self.assertEqual(answer.generation_attempts, 3)
        self.assertEqual(answer.validation_failures, 2)

    def test_blocks_generation_failure(self):
        llm = FakeLlm(error=RuntimeError("external failure"))
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), llm)

        answer = pipeline.answer("해고 통지를 받았습니다", category=LegalCategory.LABOR)

        self.assertEqual(answer.status, AnswerStatus.GENERATION_FAILED)

    def test_graph_has_only_retrieve_and_generate_nodes(self):
        pipeline = StatuteRagPipeline(FakeRetriever([evidence_hit()]), FakeLlm(valid_response()))

        graph = pipeline.graph.get_graph()

        self.assertEqual(set(graph.nodes) - {"__start__", "__end__"}, {"retrieve", "generate"})
        self.assertEqual(
            {(edge.source, edge.target) for edge in graph.edges},
            {("__start__", "retrieve"), ("retrieve", "generate"), ("generate", "__end__")},
        )

    def test_generate_node_receives_evidence_from_retrieve_node(self):
        retriever = FakeRetriever([evidence_hit()])
        llm = FakeLlm(valid_response())
        pipeline = StatuteRagPipeline(retriever, llm)

        state = pipeline.graph.invoke(
            {"question": "  해고 통지를 받았습니다  ", "category": LegalCategory.LABOR, "top_k": 5}
        )

        self.assertEqual(retriever.received_query, "해고 통지를 받았습니다")
        self.assertEqual(len(state["evidence"]), 1)
        self.assertIn("제27조", llm.messages[-1]["content"])
        self.assertEqual(state["answer"].status, AnswerStatus.ANSWERED)


if __name__ == "__main__":
    unittest.main()
