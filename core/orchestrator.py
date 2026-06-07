"""Pure control flow over SessionState. No LLM calls happen in this file.

The Orchestrator does NOT collect student answers — that's a UI concern.
It exposes step boundaries the UI can drive: prepare diagnostic, submit
diagnostic answers, run practice round, etc.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

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
        # Background pool for pre-generating the next practice round while
        # the user is still on the review screen — hides LLM latency.
        self._bg = ThreadPoolExecutor(max_workers=2)

    def start(
        self, subject: str, level: str, source_text: str = "", question_count: int = 10
    ) -> SessionState:
        state = SessionState(
            subject=subject,
            level=level,
            source_text=source_text,
            phase=Phase.INIT,
            question_count=question_count,
        )
        state.started_at = time.time()
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
        state.phase = Phase.DIAGNOSTIC_REVIEW
        if state.weak_topics:
            self._start_practice_pregen(state, weak_topics=state.weak_topics)
        return state

    def continue_after_diagnostic(self, state: SessionState) -> SessionState:
        if not state.weak_topics:
            state.passed = True
            return self._finalize(state)
        if self._adopt_pregen(state):
            return state
        return self._run_practice_round(state)

    def submit_practice_answers(
        self, state: SessionState, answers: list[str]
    ) -> SessionState:
        state.practice_answers = answers
        state.phase = Phase.EVALUATION
        state = self.evaluator.run(state)

        # Archive this round before results get overwritten by the next round.
        state.practice_history.append({
            "iteration": state.iteration,
            "questions": list(state.practice_questions),
            "results": list(state.practice_results),
        })

        state.phase = Phase.PRACTICE_REVIEW

        # If there will be another round, pre-generate it now using the
        # weak topics we can already compute from this round's results.
        if not state.passed and state.iteration < config.MAX_PRACTICE_ROUNDS:
            from tools import scoring

            per_topic = scoring.per_topic_accuracy(state.practice_results)
            still_weak = scoring.weak_topics(per_topic, config.WEAK_TOPIC_THRESHOLD)
            if still_weak:
                next_weak = [
                    {"topic": t, "accuracy": per_topic[t], "explanation": ""}
                    for t in still_weak
                ]
                state.pending_weak_topics = next_weak
                self._start_practice_pregen(state, weak_topics=next_weak)
        return state

    def continue_after_practice(self, state: SessionState) -> SessionState:
        if state.passed or state.iteration >= config.MAX_PRACTICE_ROUNDS:
            return self._finalize(state)

        if state.pending_weak_topics:
            state.weak_topics = state.pending_weak_topics
            state.pending_weak_topics = None

        if self._adopt_pregen(state):
            return state

        # Fallback: nothing pre-generated — compute synchronously now.
        from tools import scoring

        per_topic = scoring.per_topic_accuracy(state.practice_results)
        still_weak = scoring.weak_topics(per_topic, config.WEAK_TOPIC_THRESHOLD)
        if not still_weak:
            # No individual topic is below the threshold even though the
            # round didn't pass — nothing concrete to drill on, so finalize.
            return self._finalize(state)
        state.weak_topics = [
            {"topic": t, "accuracy": per_topic[t], "explanation": ""}
            for t in still_weak
        ]
        return self._run_practice_round(state)

    def _start_practice_pregen(
        self, state: SessionState, weak_topics: list[dict]
    ) -> None:
        """Kick off the next practice round in a background thread."""
        snapshot = SessionState(
            subject=state.subject,
            level=state.level,
            source_text=state.source_text,
            iteration=state.iteration,
            weak_topics=list(weak_topics),
            diagnostic_questions=list(state.diagnostic_questions),
            practice_questions=list(state.practice_questions),
        )
        state.pending_future = self._bg.submit(self._run_practice_round, snapshot)

    def _adopt_pregen(self, state: SessionState) -> bool:
        """If a pre-generated practice round is ready, copy it onto `state`."""
        future = state.pending_future
        if future is None:
            return False
        try:
            ready = future.result(timeout=120)
        except Exception:
            state.pending_future = None
            return False
        state.pending_future = None
        state.iteration = ready.iteration
        state.phase = Phase.PRACTICE
        state.practice_questions = ready.practice_questions
        state.practice_answers = []
        state.practice_results = []
        return True

    def _run_practice_round(self, state: SessionState) -> SessionState:
        state.iteration += 1
        state.phase = Phase.PRACTICE
        return self.generator.run(state)

    def _finalize(self, state: SessionState) -> SessionState:
        if state.started_at:
            state.elapsed_seconds = time.time() - state.started_at
        state.phase = Phase.FEEDBACK
        state = self.feedback.run(state)
        state = self.judge.run(state)
        state.phase = Phase.DONE
        return state
