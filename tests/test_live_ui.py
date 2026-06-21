import sys
import os
import time
from seleniumbase import BaseCase
import pytest

# Ensure workspace is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.orchestrator import Orchestrator
from core.session_state import Phase, SessionState
from tests.conftest import FakeLLMClient
from llm.schemas import Question, QuestionSet, WeaknessAnalysis, WeakTopic, EvaluationResult, FinalReport, JudgeScores, JudgeScore
import ui.views


class TestQuizMindLiveUI(BaseCase):
    demo = None

    def setUp(self):
        super().setUp()
        # Mock the orchestrator in ui.views to use FakeLLMClient
        self.fake_client = FakeLLMClient()
        ui.views._orch = Orchestrator(client=self.fake_client)

        # Set up default handlers for the fake client
        self.setup_fake_client_defaults(self.fake_client)

        # Build blocks and launch in background thread
        self.demo = ui.views.build_blocks()
        self.port = 7866
        self.demo.launch(
            prevent_thread_lock=True,
            server_name="127.0.0.1",
            server_port=self.port,
        )
        
        # Wait for the local server port to open
        import socket
        connected = False
        for i in range(50):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    connected = True
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)
        if not connected:
            raise RuntimeError("Failed to connect to Gradio server port.")
        time.sleep(0.5)

    def tearDown(self):
        if self.demo:
            self.demo.close()
        super().tearDown()

    def setup_fake_client_defaults(self, client):
        def make_question(qid, topic, correct="A"):
            return Question(
                id=qid,
                topic=topic,
                prompt=f"Stub question {qid} on {topic}?",
                choices=["A", "B", "C", "D"],
                correct_answer=correct,
                explanation="Explanation text",
            )

        client.set(QuestionSet, lambda prompt: QuestionSet(
            questions=[
                make_question("d1", "Physics"),
                make_question("d2", "Chemistry")
            ]
        ))
        client.set(WeaknessAnalysis, lambda prompt: WeaknessAnalysis(
            weak_topics=[WeakTopic(topic="Physics", accuracy=0.0, explanation="Physics is weak.")],
            summary="Weak in Physics."
        ))
        client.set(EvaluationResult, lambda prompt: EvaluationResult(
            graded=[],
            score=0.0,
            improvement_delta=0.0,
            passed=False,
            rationale="Evaluation stub rationale."
        ))
        client.set(FinalReport, lambda prompt: FinalReport(
            mastered_topics=["Chemistry"],
            still_needs_work=["Physics"],
            recommended_next_steps=["Step 1", "Step 2"],
            summary="Final learning summary report."
        ))
        s_score = JudgeScore(score=8, justification="good calibration")
        client.set(JudgeScores, lambda prompt: JudgeScores(
            relevance=s_score,
            difficulty_calibration=s_score,
            improvement_validity=s_score,
            overall_comment="Nice job on this session."
        ))

    def test_full_adaptive_quiz_flow(self):
        # 1. Open the local Gradio page
        url = f"http://127.0.0.1:{self.port}"
        self.open(url)

        # Assert page title contains QuizMind
        self.assert_title_contains("QuizMind")

        # 2. Select "Custom..." from the category dropdown
        self.click("#category-dropdown input")
        self.type("#category-dropdown input", "Custom...\n")

        # Wait for custom subject textbox to appear and type "Quantum Mechanics"
        self.wait_for_element("#custom-subject-textbox textarea")
        self.type("#custom-subject-textbox textarea", "Quantum Mechanics")

        # Select Level and click Start test
        self.click('#level-radio label[data-testid="intermediate-radio-label"]')
        self.click("#start-session-button")

        # 3. Wait for Quiz to load (submit answers button is visible)
        self.wait_for_element("#submit-answers-button")

        # Verify the two questions are rendered
        self.assert_text("1. Stub question d1 on Physics?")
        self.assert_text("2. Stub question d2 on Chemistry?")

        # 4. Answer the questions
        # We will answer 'B' to the first question (incorrect) and 'A' to the second question (correct)
        cards = self.find_elements(".qm-quiz-card:not(.qm-quiz-card .qm-quiz-card)")
        self.assertEqual(len(cards), 2)
        cards[0].find_element("css selector", 'label:has(input[value="B"])').click()
        cards[1].find_element("css selector", 'label:has(input[value="A"])').click()

        # Submit answers
        self.click("#submit-answers-button")

        # 5. Wait for Diagnostic Review page to load (continue button is visible)
        self.wait_for_element("#continue-button")
        self.assert_text("Initial test — results")
        
        # Click Continue to practice
        self.click("#continue-button")

        # 6. Wait for Practice Round to load
        self.wait_for_element("#submit-answers-button")
        self.assert_text("Practice round 1")

        # Answer practice questions
        cards = self.find_elements(".qm-quiz-card:not(.qm-quiz-card .qm-quiz-card)")
        for card in cards:
            card.find_element("css selector", 'label:has(input[value="A"])').click()

        # Submit practice answers
        self.click("#submit-answers-button")

        # 7. Wait for Practice Review screen
        self.wait_for_element("#continue-button")
        self.assert_text("Practice round 1 — results")

        # Click "See final report" (continue button)
        self.click("#continue-button")

        # 8. Wait for DONE screen to load
        self.wait_for_element("#restart-session-button")
        self.assert_text("Final Learning Report")
        self.assert_element("#download-pdf-button")

        # 9. Click Restart to go back to config screen
        self.click("#restart-session-button")

        # Verify we are back on the Setup screen
        self.wait_for_element("#start-session-button")
        self.assert_text("Configure Learning Session")
