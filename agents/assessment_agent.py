"""Generates the opening diagnostic quiz."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core.session_state import SessionState
from llm import prompts
from llm.schemas import QuestionSet


class AssessmentAgent(BaseAgent):
    name = "assessment"

    def run(self, state: SessionState) -> SessionState:
        prompt = prompts.assessment_prompt(
            subject=state.subject,
            level=state.level,
            n_questions=state.question_count,
            source_text=state.source_text,
        )
        result: QuestionSet = self.client.generate_structured(prompt, QuestionSet)
        state.diagnostic_questions = [q.model_dump() for q in result.questions]
        return state
