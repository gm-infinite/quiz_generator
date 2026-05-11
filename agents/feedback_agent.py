"""Writes the human-readable final report."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core.session_state import SessionState
from llm import prompts
from llm.schemas import FinalReport


class FeedbackAgent(BaseAgent):
    name = "feedback"

    def run(self, state: SessionState) -> SessionState:
        prompt = prompts.feedback_prompt(
            subject=state.subject,
            weak_topics=[w["topic"] for w in state.weak_topics],
            practice_results=state.practice_results,
        )
        report: FinalReport = self.client.generate_structured(prompt, FinalReport)
        state.final_report = {**(state.final_report or {}), **report.model_dump()}
        return state
