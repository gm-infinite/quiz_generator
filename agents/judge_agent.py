"""LLM-in-the-loop session evaluator. Runs once, after the loop terminates."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core.session_state import SessionState
from llm import prompts
from llm.schemas import JudgeScores


class JudgeAgent(BaseAgent):
    name = "judge"

    def run(self, state: SessionState) -> SessionState:
        summary = {
            "subject": state.subject,
            "level": state.level,
            "diagnostic_score": state.diagnostic_score,
            "practice_score": state.practice_score,
            "iterations": state.iteration,
            "weak_topics": [w["topic"] for w in state.weak_topics],
            "diagnostic_questions": state.diagnostic_questions,
            "practice_questions": state.practice_questions,
            "practice_results": state.practice_results,
        }
        prompt = prompts.judge_prompt(summary)
        scores: JudgeScores = self.client.generate_structured(prompt, JudgeScores)
        state.judge_scores = scores.model_dump()
        return state
