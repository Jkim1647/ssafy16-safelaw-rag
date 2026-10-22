"""상담실 채팅 화면을 Streamlit AppTest로 실행해 대화가 쌓이고 스레드가 이어지는지 확인한다."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from streamlit.testing.v1 import AppTest

from legal_rag.domain.models import LegalCategory
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer
from legal_rag.ui import streamlit_app


class FakePipeline:
    def __init__(self):
        self.calls = []
        self.forgotten = []

    def forget_conversation(self, thread_id):
        self.forgotten.append(thread_id)

    def converse(self, question, *, thread_id, category, top_k):
        self.calls.append((question, thread_id, category))
        answer = GroundedAnswer(AnswerStatus.ANSWERED, f"## 상황에 대한 법령·판례 안내\n\n답변 {len(self.calls)} [근거 1]")
        return answer, ()


class ConsultationAppTestCase(unittest.TestCase):
    def setUp(self):
        self.index = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.dict(os.environ, {"GMS_KEY": "test-key"}),
            mock.patch.object(streamlit_app, "INDEX_PATH", Path(self.index.name)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.index.cleanup)
        self.pipeline = FakePipeline()
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        self.app.session_state["safelaw_pipeline"] = self.pipeline
        self.app.run()

    def ask(self, text):
        self.app.chat_input(key="consult_chat_input").set_value(text).run()

    def start_labor(self):
        self.app.sidebar.selectbox(key="consult_category").set_value(LegalCategory.LABOR).run()
        self.app.sidebar.toggle[0].set_value(False).run()


class ConsultationRoomTests(ConsultationAppTestCase):
    def test_greets_and_asks_for_category_first(self):
        self.app.run()

        self.assertIn("상담 분야", self.app.chat_message[0].markdown[0].value)
        self.ask("해고 통보를 받았어요")
        self.assertEqual(self.pipeline.calls, [])
        self.assertIn("상담 분야를 먼저", self.app.warning[0].value)

    def test_conversation_accumulates_in_one_masked_thread(self):
        self.app.sidebar.selectbox(key="consult_category").set_value(LegalCategory.LABOR).run()
        self.app.sidebar.toggle[0].set_value(False).run()

        self.ask("팀장이 010-1234-5678로 카톡 해고를 알렸어요")
        self.ask("서면으로 받았다면 달라지나요?")

        questions = [call[0] for call in self.pipeline.calls]
        threads = {call[1] for call in self.pipeline.calls}
        self.assertEqual(len(questions), 2)
        self.assertNotIn("010-1234-5678", questions[0])
        self.assertEqual(len(threads), 1)
        messages = self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual(len(self.app.chat_message), 5)

    def test_new_consultation_starts_a_new_thread(self):
        self.app.sidebar.selectbox(key="consult_category").set_value(LegalCategory.LABOR).run()
        self.app.sidebar.toggle[0].set_value(False).run()
        self.ask("첫 상담")

        self.app.sidebar.button(key="new_consultation").click().run()
        self.ask("새 상담")

        self.assertNotEqual(self.pipeline.calls[0][1], self.pipeline.calls[1][1])
        self.assertEqual(len(self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY]), 2)


class ConsultationHistoryTests(ConsultationAppTestCase):
    def history_buttons(self):
        return [button for button in self.app.sidebar.button if button.key and button.key.startswith("open_")]

    def test_past_consultations_are_listed_newest_first_and_can_be_restored(self):
        self.start_labor()
        self.ask("첫 번째 상담 질문")
        self.app.sidebar.button(key="new_consultation").click().run()
        self.ask("두 번째 상담 질문")
        first_thread = self.pipeline.calls[0][1]

        labels = [button.label for button in self.history_buttons()]
        self.assertEqual(len(labels), 2)
        self.assertIn("두 번째 상담 질문", labels[0])
        self.assertIn("첫 번째 상담 질문", labels[1])

        self.history_buttons()[1].click().run()
        self.ask("첫 상담 이어서 질문")

        self.assertEqual(self.pipeline.calls[-1][1], first_thread)
        restored = self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY]
        self.assertEqual([m["content"] for m in restored if m["role"] == "user"],
                         ["첫 번째 상담 질문", "첫 상담 이어서 질문"])

    def test_deleting_a_consultation_removes_it_and_its_thread(self):
        self.start_labor()
        self.ask("삭제할 상담")
        thread = self.pipeline.calls[0][1]

        self.app.sidebar.button(key=f"delete_{thread}").click().run()

        self.assertEqual(self.history_buttons(), [])
        self.assertEqual(self.pipeline.forgotten, [thread])
        self.assertEqual(self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY], [])


if __name__ == "__main__":
    unittest.main()
