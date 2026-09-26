# Epic 3 Context: Measure the Agent

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build an MLflow evaluation harness that runs the Epic 2 agent over 20 hand-labelled tickets, scores each result four ways in code (schema validity, category match, priority match, tool order) plus once by an independent LLM judge, and reports aggregate metrics — mean scores, token spend, and escalation count — so workshop attendees leave with a measured baseline of the agent's quality and cost.

## Stories

- Story 3.1: The eval run and the four code scorers
- Story 3.2: The rationale judge and the report

## Requirements & Constraints

**Functional Requirements:**
- The eval harness must use `mlflow.genai.evaluate` (not hand-rolled scoring).
- Run entry point: `uv run python eval/run_eval.py` drives the agent over all 20 tickets in `eval/labelled_tickets.csv` in one pass.
- Produces exactly one MLflow run to the `triage-agent` experiment in `sqlite:///mlflow.db`.
- Escalation approvals within eval runs must be automatic (unattended); unattended approval does not apply to normal `run_agent.py` invocations.

**Scorer Scope:**
- `valid_schema`: Validates each ticket's output against the Epic 1 triage-decision schema (1 = valid, 0 = invalid).
- `category_match`: Checks if output category equals the labelled `expected_category` (1/0).
- `priority_match`: Checks if output priority equals the labelled `expected_priority` (1/0).
- `tool_order`: Verifies MLflow trace shows `get_ticket` span starting before `get_customer_history` span (1/0).
- `rationale_judge`: Groq model judges rationality against each ticket's `judge_notes`; returns pass/fail per ticket (pass = 1, fail = 0 in reporting).

**Judge Configuration:**
- `rationale_judge` always calls `ChatGroq` with model from `JUDGE_MODEL` (default `openai/gpt-oss-120b`) and key from `GROQ_API_KEY`.
- Must never read `GEMINI_API_KEY` — does not compete with the agent's Gemini quota.

**Output & Reporting:**
- Prints mean of all five scorers, agent's total tokens, and escalation count.
- Writes the same metrics to `eval/latest_report.json` for reuse.
- Escalation auto-approval count appears in both printed output and JSON report.

**Read-Only / Unchanged:**
- `eval/labelled_tickets.csv` — not modified.
- `TRIAGE_POLICY.md` — not modified.
- Epic 2 agent behavior — `run_eval.py` calls the existing agent as-is; no changes to its decision logic, prompts, or policy handling.

**Trace & Escalation Handling:**
- Each ticket's prediction runs inside a single MLflow trace. Approved escalations resume the agent in a second call within the same trace, ensuring CAP-5's `tool_order` scorer can see both spans.

**Network & Isolation:**
- Code scorers (`valid_schema`, `category_match`, `priority_match`, `tool_order`) run locally against schema, labels, and traces.
- Only the agent's model call and `rationale_judge`'s Groq call cross the network.
- `eval/latest_report.json` is the only new file outside MLflow's store.

## Technical Decisions

- **MLflow Integration:** Use `mlflow.genai.evaluate` as the eval harness framework; log one run per full evaluation pass.
- **Trace Ownership:** Each ticket prediction is a single MLflow trace; approved escalations resume within that trace to maintain visibility for cross-span metrics.
- **Scorer Separation:** Code scorers are deterministic and local; `rationale_judge` is a Groq-based LLM scorer separate from the agent's Gemini instance.
- **Auto-Approval Scope:** Escalation auto-approval applies only during eval runs, not in normal interactive `run_agent.py` invocations.

## Cross-Story Dependencies

Story 3.1 (eval harness + four code scorers) must be completed before Story 3.2 (rationale judge + report) because the judge scorer and reporting depend on the eval framework and labelled run data from Story 3.1.
