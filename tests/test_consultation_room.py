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
from legal_rag.rag.citations import EvidenceQuote, GroundedClaim
from legal_rag.rag.issue_checklist import ChecklistItem, IssueChecklist
from legal_rag.rag.pipeline import AnswerStatus, GroundedAnswer
from legal_rag.ui import streamlit_app


class FakePipeline:
    def __init__(self, evidence=()):
        self.calls = []
        self.forgotten = []
        self.evidence = evidence

    def forget_conversation(self, thread_id):
        self.forgotten.append(thread_id)

    def converse(self, question, *, thread_id, category, top_k):
        self.calls.append((question, thread_id, category))
        answer = GroundedAnswer(AnswerStatus.ANSWERED, f"## 상황에 대한 법령·판례 안내\n\n답변 {len(self.calls)} [근거 1]")
        return answer, self.evidence


class FakeChecklistBuilder:
    def __init__(self):
        self.calls = 0

    def build(self, question, category, evidence):
        self.calls += 1
        claims = (
            ("해고 사유와 시기를 서면으로 통지해야 합니다.", "mentioned"),
            ("해고일로부터 3개월 안에 구제신청을 해야 합니다.", "unknown"),
        )
        items = tuple(
            ChecklistItem(
                GroundedClaim(f"{text} ({self.calls}차)", (1,), (EvidenceQuote(1, "서면으로 통지하여야"),)),
                status,
                f"{index + 1}번 사실을 확인했나요?",
            )
            for index, (text, status) in enumerate(claims)
        )
        return IssueChecklist(AnswerStatus.ANSWERED, items=items)


class ConsultationAppTestCase(unittest.TestCase):
    def setUp(self):
        self.index = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.dict(os.environ, {"GMS_KEY": "test-key"}),
            mock.patch.object(streamlit_app, "INDEX_PATH", Path(self.index.name)),
            # 판례 색인 유무가 PC마다 달라도 같은 결과가 나오게 고정한다.
            mock.patch.object(streamlit_app, "case_index_status", lambda path=None: (True, "법령·판례 색인 사용")),
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


class IntakeTests(ConsultationAppTestCase):
    def test_client_can_pick_a_category_in_the_room(self):
        intake = [button for button in self.app.button if button.key and button.key.startswith("intake_")]
        self.assertEqual(len(intake), 3)

        self.app.button(key="intake_labor").click().run()

        self.assertEqual(self.app.sidebar.selectbox(key="consult_category").value, LegalCategory.LABOR)
        examples = [button for button in self.app.button if button.key and button.key.startswith("example_labor")]
        self.assertEqual(len(examples), 3)

    def test_promises_show_real_dataset_numbers_until_the_first_question(self):
        promises = " ".join(md.value for md in self.app.markdown if 'class="trust-row"' in md.value)
        self.assertIn("381개 조문", promises)
        self.assertIn("판례 50건", promises)
        self.assertIn("근거가 없으면", promises)

        self.start_labor()
        self.ask("카톡으로 해고 통보를 받았어요")

        self.assertEqual([md for md in self.app.markdown if 'class="trust-row"' in md.value], [])

    def test_only_the_latest_answer_invites_a_follow_up(self):
        self.start_labor()
        self.ask("카톡으로 해고 통보를 받았어요")
        self.ask("서면으로 다시 받으면요?")

        invites = [caption for caption in self.app.caption if "이어서 물어보세요" in caption.value]
        self.assertEqual(len(invites), 1)


class NavigationTests(ConsultationAppTestCase):
    def intake_buttons(self):
        return [button for button in self.app.button if button.key and button.key.startswith("intake_")]

    def test_no_home_button_on_the_first_screen(self):
        self.assertEqual([button for button in self.app.button if button.key == "consult_home"], [])

    def test_home_goes_back_to_category_choice(self):
        self.app.button(key="intake_labor").click().run()
        self.assertEqual(self.intake_buttons(), [])

        self.app.button(key="consult_home").click().run()

        self.assertIsNone(self.app.sidebar.selectbox(key="consult_category").value)
        self.assertEqual(len(self.intake_buttons()), 3)

    def test_home_keeps_the_conversation_in_the_history(self):
        self.start_labor()
        self.ask("카톡으로 해고 통보를 받았어요")
        thread = self.pipeline.calls[0][1]

        self.app.button(key="consult_home").click().run()

        self.assertEqual(self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY], [])
        self.assertNotEqual(self.app.session_state[streamlit_app.CONSULT_THREAD_KEY], thread)
        self.assertEqual(len(self.intake_buttons()), 3)
        self.app.sidebar.button(key=f"open_{thread}").click().run()
        self.assertEqual(len(self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY]), 2)


class ArticleNavigationTests(ConsultationAppTestCase):
    def setUp(self):
        super().setUp()
        self.app.sidebar.radio(key="safelaw_view").set_value(streamlit_app.VIEW_ARTICLES).run()

    def test_back_to_the_consultation_room(self):
        self.app.button(key="back_to_consult").click().run()

        self.assertEqual(self.app.sidebar.radio(key="safelaw_view").value, streamlit_app.VIEW_CONSULT)
        self.assertEqual(len([b for b in self.app.button if b.key and b.key.startswith("intake_")]), 3)

    def test_back_from_an_article_to_the_list(self):
        self.app.selectbox(key="article_category").set_value(LegalCategory.LABOR).run()
        picker = self.app.selectbox(key="article_picker_labor")
        picker.set_value(picker.options[1]).run()
        self.assertEqual(len(self.app.chat_input), 1)

        self.app.button(key="article_back").click().run()

        self.assertEqual(len(self.app.chat_input), 0)
        self.assertIsNone(self.app.selectbox(key="article_picker_labor").value)


class CaseIndexNoticeTests(ConsultationAppTestCase):
    def test_missing_case_index_is_announced_and_promises_drop_cases(self):
        message = "판례 색인이 없어 법령만 검색합니다."
        with mock.patch.object(streamlit_app, "case_index_status", lambda path=None: (False, message)):
            self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
            self.app.session_state["safelaw_pipeline"] = self.pipeline
            self.app.run()

        self.assertIn(message, [warning.value for warning in self.app.sidebar.warning])
        promises = " ".join(md.value for md in self.app.markdown if 'class="trust-row"' in md.value)
        self.assertIn("381개 조문", promises)
        self.assertNotIn("판례 50건", promises)


class ChecklistPanelTests(ConsultationAppTestCase):
    def setUp(self):
        super().setUp()
        self.pipeline.evidence = (object(),)
        self.app.session_state["safelaw_checklist_builder"] = FakeChecklistBuilder()
        self.app.sidebar.selectbox(key="consult_category").set_value(LegalCategory.LABOR).run()

    def panel_claims(self):
        return [md.value for md in self.app.markdown if "차)" in md.value]

    def test_chat_shows_a_brief_summary_and_the_panel_holds_the_full_checklist(self):
        self.ask("카톡으로 해고 통보를 받았어요")

        answer = self.app.chat_message[-1]
        summary = " ".join(md.value for md in answer.markdown)
        self.assertIn("쟁점 체크리스트 2개", summary)
        self.assertIn("확인 필요 1", summary)
        self.assertEqual([checkbox for checkbox in answer.checkbox], [])
        self.assertEqual(len(self.app.checkbox), 2)
        self.assertEqual(len(self.panel_claims()), 2)

    def test_panel_follows_the_latest_answer_and_can_show_an_earlier_one(self):
        self.ask("카톡으로 해고 통보를 받았어요")
        self.ask("서면으로 다시 받으면요?")
        self.assertTrue(all("(2차)" in claim for claim in self.panel_claims()))

        first_token = self.app.session_state[streamlit_app.CONSULT_MESSAGES_KEY][1]["token"]
        self.app.button(key=f"focus_{first_token}").click().run()

        self.assertTrue(all("(1차)" in claim for claim in self.panel_claims()))
        self.assertEqual(len(self.panel_claims()), 2)

    def test_panel_explains_legal_terms_once(self):
        self.ask("카톡으로 해고 통보를 받았어요")

        glossary = [caption.value for caption in self.app.caption if "📖 **" in caption.value]
        self.assertEqual(len(glossary), 2)
        self.assertIn("**서면통지**", glossary[0])
        self.assertIn("**구제신청**", glossary[1])
        self.assertNotIn("서면통지", glossary[1])
        self.assertTrue(any("일반적인 설명" in caption.value for caption in self.app.caption))

    def test_no_panel_when_the_checklist_is_turned_off(self):
        self.app.sidebar.toggle[0].set_value(False).run()
        self.ask("카톡으로 해고 통보를 받았어요")

        self.assertEqual(self.panel_claims(), [])
        self.assertEqual(len(self.app.main.columns), 0)


if __name__ == "__main__":
    unittest.main()
