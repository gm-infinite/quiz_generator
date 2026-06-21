"""Grades the practice round and applies the pass rule.

The pass decision is deterministic — we do NOT ask the LLM to decide.
LLM only contributes the rationale text.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core import config
from core.session_state import SessionState
from llm import prompts
from llm.schemas import EvaluationResult
from tools import scoring


class EvaluatorAgent(BaseAgent):
    name = "evaluator"

    def run(self, state: SessionState) -> SessionState:
        graded = scoring.grade_answers(state.practice_questions, state.practice_answers)
        state.practice_results = graded
        practice_score = scoring.overall_accuracy(graded)
        state.practice_score = practice_score

        diagnostic_score = state.diagnostic_score or 0.0
        delta = practice_score - diagnostic_score
        passed = (
            practice_score >= config.PASS_ABSOLUTE_THRESHOLD
            or delta >= config.PASS_IMPROVEMENT_DELTA
        )
        state.passed = passed

        prompt = prompts.evaluator_prompt(
            diagnostic_score=diagnostic_score,
            practice_score=practice_score,
            improvement_delta=delta,
            pass_absolute=config.PASS_ABSOLUTE_THRESHOLD,
            pass_delta=config.PASS_IMPROVEMENT_DELTA,
        )
        # We still ask the LLM for an EvaluationResult so we get a rationale,
        # but we OVERWRITE its passed/score with deterministic values.
        llm_eval: EvaluationResult = self.client.generate_structured(prompt, EvaluationResult)
        state.final_report = state.final_report or {}
        state.final_report["evaluator_rationale"] = llm_eval.rationale
        return state
