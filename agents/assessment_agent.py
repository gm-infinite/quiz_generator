"""Generates the opening diagnostic quiz."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core.session_state import SessionState
from llm import prompts
from llm.schemas import QuestionSet
from tools import diagnostic_cache


class AssessmentAgent(BaseAgent):
    name = "assessment"

    def run(self, state: SessionState) -> SessionState:
        # Predefined subjects ship a preloaded question bank — serve it and
        # skip the LLM. Uploaded-source sessions must stay within the source,
        # so they always generate; custom subjects have no bank and fall through.
        if not state.source_text:
            cached = diagnostic_cache.load_cached(
                state.subject, state.level, state.question_count
            )
            if cached is not None:
                state.diagnostic_questions = cached
                return state

        prompt = prompts.assessment_prompt(
            subject=state.subject,
            level=state.level,
            n_questions=state.question_count,
            source_text=state.source_text,
        )
        result: QuestionSet = self.client.generate_structured(prompt, QuestionSet)
        state.diagnostic_questions = [q.model_dump() for q in result.questions]
        return state
