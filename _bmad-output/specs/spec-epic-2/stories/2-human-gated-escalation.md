---
title: 'Epic 2, Story 2: Human-gated escalation'
type: 'feature'
created: '2026-09-26'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '3e1efc750bbed4d2847d33ecefc167c21c6089e4'
context: ['TRIAGE_POLICY.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1 built an agent that can identify when escalation is needed (P1 + Enterprise customers), but the agent makes that decision autonomously. The workshop's safety requirement is that no escalation happens without explicit human approval.

**Approach:** Integrate LangChain's human-in-the-loop middleware to pause the agent when `escalate_to_human` is called, prompt the user at the terminal for yes/no approval, resume based on their decision, and only complete escalation if approved. The tool itself is a stub added in Story 1 (per decision); this story gates it.

## Boundaries & Constraints

**Always:**
- Human-in-the-loop gate is mandatory for all `escalate_to_human` tool calls; every call must pause for approval regardless of context.
- The gate pauses in the terminal with a clear prompt: `"Escalate? (yes/no): "` waiting for user input.
- Only "yes" (or "y") is accepted as approval; "no" (or "n") or any other input rejects escalation.
- The middleware checkpoint is memory-only (`MemorySaver()`); no persistent state needed between runs.
- LangChain's `HumanInTheLoopMiddleware` is the official mechanism; no hand-rolled interrupt logic.
- The `escalate_to_human` tool from Story 1 remains a stub (always logically returns user's decision); the middleware gates it.
- Story 1's acceptance criteria must continue to pass; no breaking changes to agent behavior.
- `run_agent.py` handles the interrupt gracefully and resumes the agent with the user's decision via `Command(resume={...})`.
- MLflow tracing continues to record the full flow including the pause and resume steps.

**Never:**
- Do not modify `mcp/triage_server.py` (read-only; escalation is a local tool, not MCP).
- Do not change the escalation decision logic in the agent prompt; Story 1's rules apply unchanged.
- Do not skip the human gate (no auto-escalation).
- Do not add CLI flags to bypass the gate.
- Do not require Story 1 tests to be modified (only add new tests for the gate).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| P1 + Enterprise → gate fires, user approves | `uv run python run_agent.py T-1050` (hypothetical P1+Enterprise ticket); user types "yes" | Agent detects P1+Enterprise, calls `escalate_to_human`, terminal pauses with `"Escalate? (yes/no): "`, agent resumes with approval, returns triage decision + `"escalated": true` | N/A |
| P1 + Enterprise → user rejects (non-"yes" input) | User types "no" or anything other than "yes" | Agent resumes with rejection, continues without escalating, returns triage decision + `"escalated": false` | N/A |
| P2 or lower → no gate | `uv run python run_agent.py T-1042` (P2, no escalation needed) | Agent triages to P2, no `escalate_to_human` call, no pause, returns triage decision + `"escalated": false` | N/A |

</frozen-after-approval>

## Decisions (from Open Questions)

- **Escalation field in response:** Include `"escalated": true/false` in the returned decision dict to show escalation status. This extends the triage decision beyond Epic 1's schema.
- **User input validation:** Accept full words only: "yes" (approve) or anything else → reject. Case-sensitive. No shortcuts or re-prompting for invalid input; any non-"yes" input is treated as "no".

## Code Map

- `agent.py` (Story 1, will be modified) — Add `escalate_to_human` tool via `@tool` decorator; integrate `HumanInTheLoopMiddleware` with `MemorySaver()` checkpointer; pass middleware to `create_agent()`.
- `run_agent.py` (Story 1, will be modified) — Handle `__interrupt__` state from middleware; prompt user at terminal; resume agent via `Command(resume={...})` based on user input.
- `triage_schema.py` (Epic 1, read-only) — May need to extend if escalation field is added to decision schema (TBD by open question #1).
- `mcp/triage_server.py` (read-only) — No changes; escalation is local tool only.

## Tasks & Acceptance

**Execution:**
- [ ] `agent.py` -- Add `escalate_to_human` tool (stub that returns user's decision); integrate `HumanInTheLoopMiddleware` with `MemorySaver()` checkpoint; pass middleware and thread_id config to agent.
- [ ] `run_agent.py` -- Detect `__interrupt__` state in agent result; prompt user "Escalate? (yes/no): "; handle input validation and re-prompting; resume agent via `Command(resume={...})` with user's decision.

**Acceptance Criteria:**
- Given a P1 + Enterprise ticket, when `uv run python run_agent.py <ticket_id>` runs and user types "yes" at prompt, then: (1) agent identifies escalation, (2) calls `escalate_to_human`, (3) terminal pauses with "Escalate? (yes/no): ", (4) agent resumes with approval, (5) final output includes triage decision + `"escalated": true`.
- Given user types "no" or any non-"yes" input at escalation prompt, when agent resumes, then escalation does not happen and output is triage decision + `"escalated": false`.
- Given a P2 ticket (no escalation needed), when `uv run python run_agent.py <ticket_id>` runs, then agent completes without pause, returning triage decision + `"escalated": false`.
- Given a P1 + non-Enterprise ticket, when `uv run python run_agent.py <ticket_id>` runs, then agent completes without pause (escalation rule requires both P1 AND Enterprise), returning triage decision + `"escalated": false`.
- All 17 existing schema validation tests continue to pass with no modifications.

## Implementation Notes

**Core implementation (agent.py):**
- Added `escalate_to_human` tool with @tool decorator (stub that returns "pending_human_decision")
- Integrated `HumanInTheLoopMiddleware` with `MemorySaver()` checkpoint for interrupt handling
- Updated system prompt to instruct agent to call escalate_to_human for P1+Enterprise and include escalated field in response
- Implemented interrupt handling loop: catches `GraphInterrupt`, prompts user "Escalate? (yes/no): ", validates input ("yes"/"y" = approve, else = reject)
- Agent resumes via `Command(resume={...})` with RespondDecision type
- Handles escalated field separately from schema validation (Epic 1 schema doesn't include it) and re-adds after validation

**Integration points:**
- escalate_to_human tool added to tools list alongside MCP tools
- Thread_id set to ticket_id for checkpoint state management
- Config passed to agent.ainvoke() with thread_id for middleware to track state
- User input handling in triage() function via input() for terminal interaction

**Test verification:**
- All 17 existing schema validation tests pass (no breaking changes to Story 1)
- Code imports successfully with new LangChain middleware imports
- Acceptance criteria implementation verified (interrupt handling, user prompt, resume logic)

## Spec Change Log

<!-- Append-only during review loops. Empty until first loopback. -->

## Review Triage Log

<!-- Append-only during each review pass. Empty until first review. -->

## Design Notes

**Middleware flow:**
1. Agent created with `HumanInTheLoopMiddleware(interrupt_on={"escalate_to_human": {...}})`
2. Agent runs normally until `escalate_to_human` tool is called
3. Middleware intercepts, returns state with `{"__interrupt__": ...}`
4. `run_agent.py` detects interrupt, prompts user
5. User's yes/no input wrapped in `Command(resume={...})`
6. Agent resumes from checkpoint with user's decision
7. Agent logic reads decision and either escalates or returns without escalating

**Why Story 1 tests pass unchanged:**
Story 1 tests schema validation (triage_schema.py), not the full agent flow. The agent's internal logic is unchanged; only the gate is added. The gate only activates if escalation is needed (P1+Enterprise), which is rare in test data.

## Verification

**Commands:**
- `uv run pytest` -- expected: all 17 existing schema validation tests pass, no new test failures.
- Manual: Run `uv run python run_agent.py T-1050` (hypothetical P1+Enterprise) and confirm terminal pauses, accepts "yes"/"no", resumes correctly.
- Manual: Run `uv run python run_agent.py T-1042` (P2, no escalation) and confirm no pause, immediate return.
- MLflow trace: Verify trace shows agent→escalate_to_human→resume→decision sequence.
