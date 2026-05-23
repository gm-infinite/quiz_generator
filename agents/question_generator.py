"""Generates fresh practice questions for each weak topic, with search grounding.

Topics are fanned out across a thread pool — when there are multiple weak
topics, latency becomes max(per-topic) instead of sum(per-topic).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from agents.base_agent import BaseAgent
from core import config
from core.session_state import SessionState
from llm import prompts
from llm.schemas import QuestionSet
from tools.dedupe import is_duplicate


class QuestionGenerator(BaseAgent):
    name = "question_generator"

    def run(self, state: SessionState) -> SessionState:
        prior_stems = [q["prompt"] for q in state.diagnostic_questions] + [
            q["prompt"] for q in state.practice_questions
        ]

        def gen_for_topic(args: tuple[int, dict]) -> tuple[int, dict, QuestionSet]:
            i, weak = args
            prompt = prompts.question_generator_prompt(
                subject=state.subject,
                level=state.level,
                weak_topic=weak["topic"],
                n_questions=config.PRACTICE_QUESTIONS_PER_TOPIC,
                avoid_prompts=prior_stems,
                source_text=state.source_text,
            )
            return i, weak, self.client.generate_with_search(prompt, QuestionSet)

        if not state.weak_topics:
            state.practice_questions = []
            state.practice_answers = []
            state.practice_results = []
            return state

        n_workers = min(4, len(state.weak_topics))
        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            results = list(ex.map(gen_for_topic, enumerate(state.weak_topics)))

        # Sort by topic index so question order is deterministic regardless
        # of which thread finished first.
        results.sort(key=lambda r: r[0])

        all_questions: list[dict] = []
        accepted_stems: list[str] = list(prior_stems)
        dropped = 0
        for i, weak, result in results:
            j = 0
            for q in result.questions:
                if is_duplicate(q.prompt, accepted_stems):
                    dropped += 1
                    continue
                d = q.model_dump()
                d["id"] = f"p{state.iteration + 1}-{i + 1}-{j + 1}"
                d["topic"] = weak["topic"]
                all_questions.append(d)
                accepted_stems.append(q.prompt)
                j += 1

        if dropped:
            print(f"[question_generator] dropped {dropped} duplicate question(s)")

        state.practice_questions = all_questions
        state.practice_answers = []
        state.practice_results = []
        return state
