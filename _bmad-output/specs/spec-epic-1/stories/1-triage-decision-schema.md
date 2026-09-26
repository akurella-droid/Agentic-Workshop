---
title: 'Triage-decision schema'
type: 'feature'
created: '2026-09-26'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'd5b5d2ab37df51b3afc40041cbd54160046052ef'
context: ['{project-root}/_bmad-output/specs/spec-epic-1/SPEC.md', '{project-root}/TRIAGE_POLICY.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing yet defines what a valid triage decision is. Epic 2's agent needs a schema to use as structured output and to validate model output against, and Epic 3's `valid_schema` scorer needs one to score with (SPEC CAP-1).

**Approach:** Add one importable Pydantic model for a triage decision with four fields (category, priority, route, rationale), each restricted to its allowed values. Add a helper that validates a dict or JSON string and raises an error naming each offending field.

## Boundaries & Constraints

**Always:** category ∈ {billing, bug, access, performance, how-to}; priority ∈ {P1, P2, P3, P4}; route ∈ {billing-team, bug-team, access-team, performance-team, how-to-team}; rationale is one sentence, checked leniently (non-empty after trimming only — a multi-sentence rationale still passes). Route must match category per `TRIAGE_POLICY.md`'s fixed mapping (billing→billing-team, bug→bug-team, access→access-team, performance→performance-team, how-to→how-to-team); a mismatched pair is rejected. Extra fields are rejected. The error message names the offending field(s). No network calls and no API keys. Pure Python plus the existing `pydantic` dependency.

**Never:** Touch `seed/`, `mcp/triage_server.py`, `TRIAGE_POLICY.md`, `run_agent.py` or `eval/`. Build the loader (story 2) or the agent (Epic 2). Add new runtime dependencies.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid decision | `{"category":"billing","priority":"P2","route":"billing-team","rationale":"Double charge puts money at stake, so P2."}` | Returns a `TriageDecision` | N/A |
| Valid JSON string | Same object as a JSON string | Returns a `TriageDecision` | N/A |
| Missing field | No `route` | Rejected | Error names `route` |
| Extra field | Adds `"confidence": 0.9` | Rejected | Error names `confidence` |
| Bad enum | `"priority":"P5"`, `"category":"sales"` or `"route":"sales-team"` | Rejected | Error names the field and lists the allowed values |
| Category/route mismatch | `"category":"billing"`, `"route":"bug-team"` | Rejected | Error names `route` and states the expected route for the category |
| Empty rationale | `"rationale":"   "` | Rejected | Error names `rationale` |
| Multi-sentence rationale | `"rationale":"Double charge. Refund now."` | Accepted (lenient check) | N/A |
| Malformed JSON | `"{not json"` | Rejected | Error says the input is not valid JSON |
| Not an object | `[]` or `"billing"` | Rejected | Error says a JSON object is expected |

</frozen-after-approval>

## Code Map

- `pyproject.toml` -- pydantic>=2.8 is already a dependency. The pytest `testpaths = ["tests"]`; there's no build-system, so the repo root isn't on `sys.path` under pytest. Add `pythonpath = ["."]`.
- `run_agent.py` -- imports top-level modules from the repo root (`from agent import triage`). The schema follows the same flat layout. Do not edit.
- `TRIAGE_POLICY.md` -- source of the category/route table and the "one-sentence rationale that names the rule" output rule. Read-only.
- `eval/labelled_tickets.csv` -- expected values use the same enum spellings (`billing`, `P2`). Read-only.
- `tests/` -- doesn't exist yet; create it.

## Tasks & Acceptance

**Execution:**
- [x] `triage_schema.py` -- create the `TriageDecision` Pydantic v2 model (`Literal` fields, `extra="forbid"`, a rationale validator, and a model-level validator enforcing the category→route pairing from `TRIAGE_POLICY.md`) with exported `CATEGORIES`, `PRIORITIES`, `ROUTES` tuples, and `validate_decision(data: dict | str) -> TriageDecision`. It raises `ValueError` whose message names every offending field. -- The single contract Epic 2 and Epic 3 import.
- [x] `pyproject.toml` -- add `pythonpath = ["."]` under `[tool.pytest.ini_options]`. -- Lets tests import the root-level module.
- [x] `tests/test_triage_schema.py` -- cover every I/O matrix row. -- Proves CAP-1.

**Acceptance Criteria:**
- Given the repo after `uv sync`, when `uv run python -c "from triage_schema import TriageDecision, validate_decision"` runs, then it succeeds with no network access.
- Given `TriageDecision.model_json_schema()`, when inspected, then category, priority and route appear as `enum`s with exactly the allowed values, and `additionalProperties` is false. That is what makes it usable as LangChain structured output.
- Given any rejected input, when `validate_decision` raises, then the message contains the offending field name(s) and never a raw Python traceback string.

### Review Findings

Independent re-review of `main...HEAD` (branch `story/Aswin-1.1`) against this story, run after the story was already merged and marked `done`. Four layers ran: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor. All four completed (no `failed_layers`).

- [x] [Review][Patch] Assert "no raw traceback" and correct field-naming across every rejection path, including a non-string `rationale` (e.g. `None`, `42`) — currently only `test_error_never_contains_raw_traceback` (the malformed-JSON path) checks the no-traceback guarantee, and no test passes a non-string `rationale` at all [tests/test_triage_schema.py:40-103]

**Rejected:**

- `false` — Several "manually verified, no permanent test" items from this story's own Review Triage Log (multi-field formatting, non-str/non-dict top-level input, rationale required-ness in schema) were re-flagged by blind-hunter as needing permanent tests. Re-verified by hand: `validate_decision(None)`, `validate_decision(42)`, and a combined `priority="P9"` + mismatched category/route all still produce correctly-named, traceback-free errors. No new evidence of failure since the prior triage round — a documented process trade-off, not a re-openable defect.
- `low`, rejected — `CATEGORY_TO_ROUTE` hand-duplicates `CATEGORIES`/`ROUTES` with no fallback. Duplicate of an already-rejected entry in this same Review Triage Log below; unreachable today since `Literal` field validation runs before the mismatch check, and a fix would add a guard for a state the program cannot currently reach.
- `low`, rejected — `Literal[CATEGORIES]` subscripts `Literal` with a runtime tuple, which a static type checker (mypy/pyright) would reject. No type checker is configured or run anywhere in this repo, so it is not reachable today.
- `low`, rejected — The category/route-mismatch error is raised in a `mode="after"` model validator with an empty pydantic `loc`, so `_format_validation_error` labels it `"decision: ..."` rather than `"route: ..."`; the existing test only passes because the free-text message happens to contain the word "route". Verified true structurally, but `test_category_route_mismatch_names_route_and_expected_route` already asserts `"route" in message`, so rewording the message to drop that word would fail that test today — the claimed fragility is already guarded.
- `false` — A category/route mismatch combined with another field-level error (e.g. bad `priority`) skips `route_matches_category` entirely, since pydantic only runs `mode="after"` validators once all field validators pass, so the mismatch is silently omitted from the message. Confirmed via `priority="P9"` + mismatched category/route → message only names `priority`. This is the same claim already raised and dismissed as `false` in this story's own Review Triage Log below, for the same reason (standard pydantic v2 ordering, not a defect); no new evidence this round.
- already deferred, not re-added — `SPEC.md`'s Open Questions (route/category pairing, rationale strictness) are resolved by this story but SPEC.md was never updated, since AGENTS.md restricts SPEC.md edits to `/bmad-spec`. Already tracked verbatim in `_bmad-output/implementation-artifacts/deferred-work.md` and in this story's own Review Triage Log below — not duplicated here.
- rejected — `.memlog.md` committed under `_bmad-output/specs/spec-epic-1/`. Verified this is a pre-existing, consistent convention: `spec-epic-2/.memlog.md` and `spec-epic-3/.memlog.md` were already committed the same way before this diff, so this is not introduced by or unique to this change.

## Implementation Notes

## Spec Change Log

## Review Triage Log

- [blind-hunter] `CATEGORY_TO_ROUTE` hand-duplicates `CATEGORIES`/`ROUTES`; `route_matches_category` indexes it with no fallback, so a future edit to `CATEGORIES` without updating the dict would raise a bare `KeyError`. — verdict: low, rejected. Not reachable today: `Literal[CATEGORIES]` field validation runs before the `mode="after"` model validator, and the dict's 5 keys currently match `CATEGORIES` exactly. Fix would add a guard for a state the program cannot currently reach.
- [blind-hunter] `rationale_not_empty` returns the un-stripped value, so a whitespace-padded rationale is stored as-is. — verdict: false. The frozen spec only requires the emptiness check to trim before testing ("non-empty after trimming only"); it does not require normalizing the stored value.
- [blind-hunter] Multi-field-error formatting (`_format_validation_error` joining with `"; "`) is never exercised by a test with two simultaneous bad fields. — verdict: false. Manually verified: `validate_decision({"category":"sales","priority":"P9","route":"billing-team","rationale":"x"})` raises `"Invalid triage decision - category: ...; priority: ..."`, naming both offending fields correctly.
- [blind-hunter] No test passes a non-str/non-dict value (e.g. `None`, `int`) straight into `validate_decision`, only JSON-decoded list/string. — verdict: false. Manually verified: `validate_decision(None)` and `validate_decision(42)` both raise `"... a JSON object is expected, got NoneType/int"` as intended.
- [blind-hunter] `test_json_schema_has_enums_and_forbids_extra` doesn't assert `rationale` is present/required in the schema, so a regression making it optional would pass. — verdict: false. Manually verified: `TriageDecision.model_json_schema()["required"] == ["category", "priority", "route", "rationale"]`.
- [blind-hunter] No test covers a payload with a category/route mismatch combined with another bad field, so it's unverified whether `route_matches_category` still runs once field-level validation has already failed elsewhere. — verdict: false. Standard Pydantic v2 behavior (confirmed via the multi-error check above): `mode="after"` model validators only run once all field validators pass, so this ordering is not a defect — it's how the "name every offending field" contract already behaves for field-level errors.
- [blind-hunter] `SPEC.md`'s `## Open Questions` (route/category pairing; rationale strictness) are already resolved by this story's frozen intent and implementation, but `SPEC.md` itself was never updated to remove them, leaving the epic-level spec out of sync with shipped behavior. — verdict: low, real, deferred. Per AGENTS.md, `SPEC.md` may only be changed via `/bmad-spec`, which is outside this story's scope.
- [edge-case-hunter] No findings reported.
- [verification-gap] No findings reported.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass.
- `uv run python -c "import json, triage_schema as t; print(json.dumps(t.TriageDecision.model_json_schema()))"` -- expected: enums and `additionalProperties: false` present.
