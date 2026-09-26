---
id: SPEC-epic-1
companions: [../../../mcp/triage_server.py]
sources: [../../../INTENT.md]
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Epic 1: triage data and schema

## Why

The triage agent needs two foundations before it can exist: a strict shape for what a triage decision is, and the ticket and customer data loaded where the MCP server already expects it. `mcp/triage_server.py` reads `app.db`, but nothing creates that file yet, and nothing defines a valid decision. Epic 2's agent returns this schema as structured output and reads this data through MCP tools, and Epic 3's eval scores against both. So this epic comes first.

## Capabilities

- **CAP-1**
  - **intent:** Any code can check whether a triage decision is valid: a JSON object with a category, a priority, a route and a one-sentence rationale.
  - **success:** A decision with category in {billing, bug, access, performance, how-to}, priority in {P1, P2, P3, P4}, route in {billing-team, bug-team, access-team, performance-team, how-to-team} and a one-sentence rationale is accepted. Anything else is rejected with an error that names the offending field. That includes a missing field, an extra field, a value outside those sets, or an empty rationale or one longer than a sentence.

- **CAP-2**
  - **intent:** One command loads the seed CSVs into a local SQLite database that the MCP server can read.
  - **success:** `uv run python load_seed.py` produces `app.db` with tables `tickets` and `customers`, holding every row of `seed/tickets.csv` and `seed/customers.csv` under the same column names. Running it a second time gives an identical database, with the same rows and no duplicates.

## Constraints

- Python 3.12 or newer, managed with uv; packages are added with `uv add`.
- Files under `seed/` are read-only.
- No network calls and no API keys in this epic.
- `mcp/triage_server.py` is not changed, and its queries must keep working. That means `tickets(ticket_id, customer_id, created_at, text)` and `customers(customer_id, name, plan, open_tickets)`.
- `app.db` is never committed.
- Epic 2 imports this schema as the agent's structured output and uses it to validate model output, so it must be importable from Python and able to validate a decision.

## Non-goals

- The agent, the MCP tools, evals and any user interface.

## Success signal

After a fresh clone, `uv run python load_seed.py` run twice leaves an `app.db` that the `get_ticket("T-1042")` and `get_customer_history("C-77")` queries in `mcp/triage_server.py` answer correctly. A test suite (`uv run pytest`) shows the schema accepting a valid decision and rejecting each invalid shape with a clear error.

## Assumptions

- A rerun of `load_seed.py` rebuilds both tables from the CSVs (replace, not append). That is how "same database" is met.
- Values are stored as the CSVs give them. `open_tickets` may be stored as an integer, because the Enterprise rule compares it numerically.

## Open Questions

- Should the schema reject a route that doesn't match its category in `TRIAGE_POLICY.md` (for example billing + bug-team), or only check each field on its own?
- How strictly is "one sentence" enforced for rationale: only non-empty, or no internal sentence breaks?
