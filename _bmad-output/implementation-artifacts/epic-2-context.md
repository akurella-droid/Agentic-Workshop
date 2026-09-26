# Epic 2 Context: the triage agent

<!-- Compiled from SPEC.md and TRIAGE_POLICY.md. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A LangChain agent reads support tickets through MCP tools, applies the triage policy to understand ticket content and customer context, and returns a structured decision that a person can trust. The agent pauses for explicit human approval before escalating the riskiest tickets (P1 priority on Enterprise customers), ensuring no escalation happens without consent. This is the core capability the workshop is built to demonstrate: end-to-end agentic triage with human oversight.

## Stories

- Story 2.1: The triage agent (CAP-1 through CAP-4, CAP-6)
- Story 2.2: Human-gated escalation (CAP-5)

## Requirements & Constraints

The agent runs as a terminal command: `uv run python run_agent.py <ticket_id>` and prints a triage decision.

The decision respects the triage policy: ticket category (billing, bug, access, performance, how-to), priority (P1–P4), route, and a one-sentence rationale. It applies the Enterprise bump rule (P3→P2, P2→P1 if the customer is Enterprise with 3+ open tickets) and validates against the Epic 1 schema. If validation fails on first try, the agent retries once; a second failure stops with a clear error.

Before deciding, the agent calls two MCP tools in order: `get_ticket` (to read the ticket), then `get_customer_history` (to look up the customer by the ticket's customer_id). Both tools must be available over stdio from `mcp/triage_server.py`.

When the final priority is P1 and the customer is Enterprise, the agent calls `escalate_to_human` instead of deciding on its own, pausing the run with a yes/no prompt. Only "yes" escalates the ticket; "no" completes the run without escalation.

Ticket text is untrusted customer input. The agent must never follow instructions embedded inside it (e.g., "mark this P1"); it treats all text strictly as data and applies the policy rules instead.

The model provider switches by environment variable: `PROVIDER=groq` runs on Groq with `ChatGroq`, otherwise defaults to `ChatGoogleGenerativeAI`. The model defaults are `gemini-3.8-flash` (Gemini) and `openai/gpt-oss-120b` (Groq), overridable with `MODEL`. Keys come from `GEMINI_API_KEY` and `GROQ_API_KEY`.

## Technical Decisions

- Built with LangChain's `create_agent` (not hand-rolled).
- MCP tools sourced only from `mcp/triage_server.py` via `langchain-mcp-adapters`.
- `escalate_to_human` is a separate local tool (outside the MCP server) gated end-to-end by LangChain's human-in-the-loop middleware to ensure all escalations pause for approval.
- MLflow tracking uses `sqlite:///mlflow.db` in the `triage-agent` experiment with `mlflow.langchain.autolog()` enabled; this is protected from change.
- The existing `run_agent.py` stub imports `triage` from an `agent` module, calls it with `asyncio.run`, and prints the decision as JSON — this integration point must stay intact.
- Epic 1 schema, `mcp/triage_server.py`, `TRIAGE_POLICY.md`, and all `seed/` files are read-only.

## Cross-Story Dependencies

Story 2.1 (agent logic, MCP tool integration, policy application, schema validation and retry) must complete before Story 2.2 (escalation gate). The escalation middleware depends on the agent running end-to-end.
