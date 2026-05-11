"""Scoring is deterministic; LLM only writes the human-readable explanations."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core import config
from core.session_state import SessionState
from llm import prompts
from llm.schemas import WeaknessAnalysis
from tools import scoring


class WeaknessAnalyzer(BaseAgent):
    name = "weakness_analyzer"

    def run(self, state: SessionState) -> SessionState:
        graded = scoring.grade_answers(state.diagnostic_questions, state.diagnostic_answers)
        state.diagnostic_results = graded
        state.diagnostic_score = scoring.overall_accuracy(graded)

        per_topic = scoring.per_topic_accuracy(graded)
        weak_names = scoring.weak_topics(per_topic, config.WEAK_TOPIC_THRESHOLD)

        if not weak_names:
            state.weak_topics = []
            return state

        prompt = prompts.weakness_analysis_prompt(
            subject=state.subject,
            per_topic_accuracy={t: per_topic[t] for t in weak_names},
            threshold=config.WEAK_TOPIC_THRESHOLD,
        )
        analysis: WeaknessAnalysis = self.client.generate_structured(prompt, WeaknessAnalysis)
        # Trust LLM only for the explanation text; trust math for accuracy values.
        explanations = {w.topic: w.explanation for w in analysis.weak_topics}
        state.weak_topics = [
            {
                "topic": t,
                "accuracy": per_topic[t],
                "explanation": explanations.get(t, ""),
            }
            for t in weak_names
        ]
        return state
