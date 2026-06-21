# QuizMind — Practitioner's Notes

Working notes for anyone extending, debugging, or operating QuizMind. Assumes you've read the README and `CLAUDE.md`. This document captures the *why* behind the design and the traps that aren't obvious from the code alone.

---

## 1. The three-layer contract

The codebase has exactly three layers, and each has one rule that must not be broken:

| Layer | File(s) | Hard rule |
|-------|---------|-----------|
| Orchestration | `core/orchestrator.py` | Owns the state machine. **Never calls the LLM.** It delegates to agents and inspects what they wrote to `SessionState`. |
| Agents | `agents/*` | Each does one thing and returns the mutated `SessionState`. **They never import each other.** |
| LLM client | `llm/llm_client.py` | The single chokepoint for every LLM call. **Agents must not import the openai SDK directly.** |

The UI (`ui/views.py`) only talks to the orchestrator — never to agents. Data flows one way: `UI → Orchestrator → Agents`. If you find yourself wanting to break one of these rules, you almost certainly have the responsibility in the wrong layer.

**Why it matters:** these boundaries are what make the system testable offline and the control flow inspectable. They're also the pedagogical point of the assignment — the orchestration logic is meant to be readable, not hidden inside a framework.

---

## 2. The determinism rule (load-bearing)

This is the single most important design decision and the easiest to accidentally undo.

**Scoring, weak-topic detection, and the pass decision are pure Python** (`tools/scoring.py`, `agents/evaluator_agent.py`). The LLM is asked for `EvaluationResult` and `WeaknessAnalysis` objects **only to obtain rationale prose**. The agent then *overwrites* any score, pass flag, or accuracy number the LLM tried to set.

Two tests lock this in — do not loosen them:
- `test_evaluator_ignores_llm_pass_claim`
- `test_weakness_analyzer_uses_math_for_accuracy_not_llm`

**If you add a new evaluation criterion:** compute it deterministically in Python and ask the LLM only for the explanation. Never let a model-returned number flow into a decision.

**Why:** reproducibility and auditability. A grade you can't reproduce isn't a grade. It also insulates the system from model drift — swap the model and the scores don't move.

---

## 3. The pass rule and loop termination

In `agents/evaluator_agent.py`:

> Pass **iff** `practice_score ≥ PASS_ABSOLUTE_THRESHOLD (0.70)` **OR** `(practice_score − diagnostic_score) ≥ PASS_IMPROVEMENT_DELTA (0.20)`.

Thresholds live in `core/config.py`. The round cap is per-session (`SessionState.max_rounds`, default `MAX_PRACTICE_ROUNDS = 3`), and the user can override it at `start()`, clamped to `1`–`MAX_PRACTICE_ROUNDS_LIMIT (5)`. **The orchestrator stops the loop once `iteration >= max_rounds` regardless of pass status** — so a session is always guaranteed to terminate. If you change the loop condition, preserve that guarantee.

---

## 4. Loop-back re-targets the gaps

When a practice round fails, `Orchestrator.submit_practice_answers` recomputes `weak_topics` from the **practice results**, not the original diagnostic. The next round chases what is *still* wrong, not the original gaps. This is intentional: a student who fixed two of three weak topics shouldn't keep being drilled on the two they've mastered.

---

## 5. Question generation: concurrency, IDs, and deduplication

`agents/question_generator.py` has three behaviors worth knowing:

- **Concurrency.** It uses `ThreadPoolExecutor(max_workers=min(4, len(weak_topics)))` to fan LLM calls out per weak topic. Wall time on a multi-topic round is roughly `max(per-topic)` rather than `sum(per-topic)`. Results are sorted by topic index after the join, so **question order stays deterministic** despite parallel execution.
- **ID/topic overwriting.** The agent overwrites the returned `id` and `topic` fields with `p{iter}-{topicIdx}-{qIdx}`. This prevents collisions across topics and rounds, and forces the topic tag to match the requested weak topic even if the model mislabels it. Don't trust model-supplied IDs.
- **Deduplication is enforced in code, not just the prompt.** The generator asks the LLM (via `avoid_prompts`) to skip prior stems, but models ignore this often enough that `tools/dedupe.py` applies a hard post-filter: normalized-stem exact match plus a token-overlap threshold. **Never rely on the prompt instruction alone** to prevent repeats across rounds.

---

## 6. Structured output and the strict-parse fallback

Every LLM call goes through `llm/llm_client.py` with a Pydantic schema from `llm/schemas.py`. The client tries OpenAI's strict structured-output path first (`beta.chat.completions.parse(response_format=PydanticClass)`), then falls back to JSON mode + manual `schema.model_validate_json(...)` if the model rejects strict json_schema.

`USE_STRICT_PARSE` is `False` by default because DashScope's OpenAI-compat endpoint doesn't reliably honor strict JSON mode. **If you switch to a provider that does** (e.g. OpenAI proper), flip it to `True` in `core/config.py` for better reliability. Agents never see any of this — they always receive a validated Pydantic instance.

---

## 7. Web-search grounding is never load-bearing

`generate_with_search(prompt, schema, search_query=...)` grounds generation with real web search via `tools/web_search.py` (Tavily or Serper, auto-detected from `TAVILY_API_KEY` / `SERPER_API_KEY`). Snippets are injected above the prompt.

Failure modes all degrade silently to plain `generate_structured`:
- no key present,
- empty `search_query`,
- any search failure or timeout.

Two consequences for practitioners:
- **Sessions with uploaded source material skip search entirely** — questions must stay within the source.
- **Tests must never hit the network.** `_post_json` is always monkeypatched (see `tests/test_web_search.py`). If you add a code path that calls out, add the corresponding monkeypatch.

Search constants (`SEARCH_ENABLED`, `SEARCH_MAX_RESULTS`, etc.) live in `core/config.py`.

---

## 8. The Judge agent runs once, after the loop

`agents/judge_agent.py` runs **once after the state machine terminates** (pass or round cap) to produce qualitative `JudgeScores` over the full transcript — diagnostic, every practice round, weak topics, and final scores. It does **not** influence the pass decision (that already fired deterministically) and writes only to `state.judge_scores`. Don't wire it into the loop; it's a post-hoc reviewer, not a gate.

---

## 9. Testing discipline

- **Tests never call the real API.** All tests use the `FakeLLMClient` fixture (`fake_client`) in `tests/conftest.py`, which returns canned Pydantic instances per schema.
- **Writing a new test that needs an LLM response?** Pass `fake_client` (or instantiate `FakeLLMClient()` directly) and use `fake_client.set(SchemaType, lambda prompt: SchemaType(...))` to override the default for a single schema. Do **not** import `LLMClient` in a test.
- Run the suite with `pytest -q`. It's deterministic and offline, so it's safe to run in CI without any secrets.

---

## 10. Provider / model swaps

The system is provider-agnostic via OpenAI-compatible APIs. To swap providers you edit `core/config.py` only:

- `LLM_API_BASE` — the endpoint (DashScope default; OpenRouter, Ollama, Hugging Face commented inline).
- `LLM_MODEL` — the model id.
- The matching API key (`DASHSCOPE_API_KEY`, `OPENROUTER_API_KEY`, or `LLM_API_KEY`) in `.env`.

Consider flipping `USE_STRICT_PARSE` if the new provider honors strict JSON mode (see §6). No agent or orchestrator code should need to change.

---

## 11. Gotchas and conventions

- **Vocabulary mismatch is intentional.** User-visible strings say "initial test" / "test"; internal field names still say `diagnostic_*` (`diagnostic_questions`, `diagnostic_score`). Don't rename the fields — the churn isn't worth it. Keep UI/CLI/prompt copy on "test."
- **No prompt strings in agent files.** All templates live in `llm/prompts.py`. If you're about to inline a prompt in an agent, stop and put it there.
- **No agent frameworks.** Don't introduce LangChain / LangGraph / any agent framework — the custom orchestrator is a deliberate choice for the assignment.
- **Gradio 6.x quirk.** `theme` and `css` belong on `launch()`, not `Blocks()`.
- **Diagnostic caching.** Diagnostics are cached (`tools/diagnostic_cache.py`, `data/diagnostics/*.json`) to avoid regenerating identical broad tests — useful for fast demos and to cut API spend.

---

## 12. Where to start when extending

- **New phase in the loop:** add a method to `core/orchestrator.py` and a value to `Phase` in `core/session_state.py`. The `@gr.render(inputs=state)` block in the UI re-renders automatically on state change — you don't manually toggle visibility.
- **New evaluation signal:** compute it in `tools/scoring.py` / `agents/evaluator_agent.py` deterministically; ask the LLM only for prose (§2).
- **New question source:** model it like uploaded-source material — grounding that the generator respects but that degrades gracefully if absent (§7).
