"""Pure control flow over SessionState. No LLM calls happen in this file.

The Orchestrator does NOT collect student answers — that's a UI concern.
It exposes step boundaries the UI can drive: prepare diagnostic, submit
diagnostic answers, run practice round, etc.
"""
from __future__ import annotations

from agents.assessment_agent import AssessmentAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.feedback_agent import FeedbackAgent
from agents.judge_agent import JudgeAgent
from agents.question_generator import QuestionGenerator
from agents.weakness_analyzer import WeaknessAnalyzer
from core import config
from core.session_state import Phase, SessionState
from llm.llm_client import LLMClient


class Orchestrator:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()
        self.assessment = AssessmentAgent(self.client)
        self.analyzer = WeaknessAnalyzer(self.client)
        self.generator = QuestionGenerator(self.client)
        self.evaluator = EvaluatorAgent(self.client)
        self.feedback = FeedbackAgent(self.client)
        self.judge = JudgeAgent(self.client)

    def start(self, subject: str, level: str) -> SessionState:
        state = SessionState(subject=subject, level=level, phase=Phase.INIT)
        return self.prepare_diagnostic(state)

    def prepare_diagnostic(self, state: SessionState) -> SessionState:
        state.phase = Phase.ASSESSMENT
        return self.assessment.run(state)

    def submit_diagnostic_answers(
        self, state: SessionState, answers: list[str]
    ) -> SessionState:
        state.diagnostic_answers = answers
        state.phase = Phase.ANALYSIS
        state = self.analyzer.run(state)

        if not state.weak_topics:
            # Aced the diagnostic — skip practice, jump to feedback.
            state.passed = True
            return self._finalize(state)

        return self._run_practice_round(state)

    def submit_practice_answers(
        self, state: SessionState, answers: list[str]
    ) -> SessionState:
        state.practice_answers = answers
        state.phase = Phase.EVALUATION
        state = self.evaluator.run(state)

        if state.passed or state.iteration >= config.MAX_PRACTICE_ROUNDS:
            return self._finalize(state)

        # Loop back: regenerate weak-topic list from latest practice round
        # so the next round targets whatever is *still* weak.
        from tools import scoring

        per_topic = scoring.per_topic_accuracy(state.practice_results)
        still_weak = scoring.weak_topics(per_topic, config.WEAK_TOPIC_THRESHOLD)
        if still_weak:
            state.weak_topics = [
                {"topic": t, "accuracy": per_topic[t], "explanation": ""}
                for t in still_weak
            ]
        return self._run_practice_round(state)

    def _run_practice_round(self, state: SessionState) -> SessionState:
        state.iteration += 1
        state.phase = Phase.PRACTICE
        return self.generator.run(state)

    def _finalize(self, state: SessionState) -> SessionState:
        state.phase = Phase.FEEDBACK
        state = self.feedback.run(state)
        state = self.judge.run(state)
        state.phase = Phase.DONE
        return state
