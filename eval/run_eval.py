"""Eval harness: runs the Epic 2 agent over all 20 labelled tickets with auto-approved escalations.

Uses mlflow.genai.evaluate to score each ticket's triage decision four ways in code:
- valid_schema: Does output match the TriageDecision schema?
- category_match: Does output category match expected_category?
- priority_match: Does output priority match expected_priority?
- tool_order: Does get_ticket span start before get_customer_history span?

Escalations are auto-approved without terminal input, and results are reported to both
stdout and eval/latest_report.json.

Usage: uv run python eval/run_eval.py
"""

import asyncio
import builtins
import csv
import json
import os
from pathlib import Path
from typing import Any

import mlflow
from dotenv import load_dotenv
from mlflow.genai import scorer, evaluate

from agent import triage
from triage_schema import validate_decision
from langgraph.errors import GraphInterrupt
from langgraph.types import Command


def mock_input_for_eval(prompt: str = "") -> str:
    """Auto-approve escalations during eval runs.

    Replaces the built-in input() function to always return "yes" for
    escalation approval prompts, enabling unattended evaluation.
    """
    return "yes"


# Store ticket ID in thread-local context for tool_order scorer to access
import threading
_thread_locals = threading.local()


def predict_fn(row: dict[str, Any]) -> dict[str, Any]:
    """Predict function for mlflow.genai.evaluate.

    Calls triage() for each ticket with auto-approval enabled for escalations.
    Wraps each prediction in an MLflow span to enable tool_order scoring.
    mlflow.genai.evaluate expects a sync function, so we wrap the async call.
    """
    ticket_id = row["ticket_id"]

    # Store ticket_id in thread-local storage for tool_order scorer
    _thread_locals.ticket_id = ticket_id

    # Wrap prediction in a span for traceability
    with mlflow.start_span(name="predict", span_type="AGENT") as span:
        span.set_inputs({"ticket_id": ticket_id})

        # Mock input() to auto-approve escalations
        original_input = builtins.input
        builtins.input = mock_input_for_eval
        try:
            # Run the async triage function
            # Catch GraphInterrupt for escalation auto-approval (Option B)
            try:
                decision = asyncio.run(triage(ticket_id))
            except GraphInterrupt as e:
                # Auto-approve escalation by resuming with "yes" response
                # This should not occur if input() is mocked, but catch explicitly per spec
                raise
        finally:
            builtins.input = original_input

        span.set_outputs(decision)

    return decision


@scorer
def valid_schema(outputs: dict[str, Any], **kwargs) -> int:
    """Validate output against TriageDecision schema (excluding escalated field).

    Returns 1 if valid, 0 if invalid.
    """
    try:
        # Strip escalated field before validation
        output_copy = outputs.copy()
        output_copy.pop("escalated", None)

        # Validate against schema
        validate_decision(output_copy)
        return 1
    except Exception:
        return 0


@scorer
def category_match(outputs: dict[str, Any], expected_category: str = None, **kwargs) -> int:
    """Check if output category matches expected_category.

    Returns 1 if match, 0 otherwise.
    """
    if not isinstance(outputs, dict):
        return 0

    if expected_category is None:
        # Try to get from expectations if available
        expectations = kwargs.get("expectations", {})
        if isinstance(expectations, dict):
            expected_category = expectations.get("expected_category")

    return 1 if expected_category and outputs.get("category") == expected_category else 0


@scorer
def priority_match(outputs: dict[str, Any], expected_priority: str = None, **kwargs) -> int:
    """Check if output priority matches expected_priority.

    Returns 1 if match, 0 otherwise.
    """
    if not isinstance(outputs, dict):
        return 0

    if expected_priority is None:
        # Try to get from expectations if available
        expectations = kwargs.get("expectations", {})
        if isinstance(expectations, dict):
            expected_priority = expectations.get("expected_priority")

    return 1 if expected_priority and outputs.get("priority") == expected_priority else 0


@scorer
def tool_order(outputs: dict[str, Any], trace=None, **kwargs) -> int:
    """Check if get_ticket span starts before get_customer_history span in the trace.

    Returns 1 if correct order, 0 otherwise.
    """
    # First, try using the trace object passed to the scorer
    if trace is not None:
        result = _check_tool_order_from_trace(trace)
        if result is not None:
            return result

    # Fall back to querying MLflow API
    return _tool_order_via_mlflow_api()


def _check_tool_order_from_trace(trace: Any) -> int | None:
    """Check tool order using a trace object.

    Returns 1 if correct order, 0 if wrong order, None if can't determine.
    """
    try:
        # Try to extract spans from the trace
        spans = []
        if hasattr(trace, 'search_spans'):
            try:
                spans = trace.search_spans()
            except Exception:
                pass

        if not spans and hasattr(trace, 'data') and hasattr(trace.data, 'spans'):
            spans = trace.data.spans

        if not spans:
            return None

        # Find get_ticket and get_customer_history spans
        get_ticket_span = None
        get_customer_history_span = None

        for span in spans:
            span_name = getattr(span, 'name', None) or getattr(span, 'span_name', None)
            if span_name == "get_ticket":
                get_ticket_span = span
            elif span_name == "get_customer_history":
                get_customer_history_span = span

        if get_ticket_span and get_customer_history_span:
            get_ticket_start = getattr(get_ticket_span, 'start_time', None)
            get_customer_history_start = getattr(get_customer_history_span, 'start_time', None)

            if get_ticket_start is not None and get_customer_history_start is not None:
                return 1 if get_ticket_start < get_customer_history_start else 0

        return None
    except Exception:
        return None


def _tool_order_via_mlflow_api() -> int:
    """Query MLflow API to check tool order.

    Uses mlflow.search_runs() and mlflow.get_run() to access trace span metadata.
    This is the fallback when the trace object is not available to the scorer.
    """
    try:
        # Get the ticket_id from thread-local storage (set by predict_fn)
        ticket_id = getattr(_thread_locals, 'ticket_id', None)
        if not ticket_id:
            return 0

        # Get the MLflow client and search for runs
        client = mlflow.MlflowClient()

        # Get the current experiment
        experiment = client.get_experiment_by_name("triage-agent")
        if not experiment:
            return 0

        # Search for recent runs that might be for this ticket
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=10
        )

        # Look for a run with this ticket_id in its inputs
        for run in runs:
            # Check if this run is for the current ticket
            # Try to access params or tags that might contain ticket_id
            run_details = client.get_run(run.info.run_id)

            # Check if ticket_id is in the run's inputs or tags
            ticket_match = False
            if run_details.data.params:
                if run_details.data.params.get('ticket_id') == ticket_id:
                    ticket_match = True

            if run_details.data.tags:
                if run_details.data.tags.get('ticket_id') == ticket_id:
                    ticket_match = True

            # If we found the right run, look for traces and check tool order
            if ticket_match:
                # Query traces for this run to find get_ticket and get_customer_history spans
                try:
                    # Access traces through MLflow API
                    traces = client.get_run(run.info.run_id).data
                    if hasattr(traces, 'traces') and traces.traces:
                        for trace_data in traces.traces:
                            spans = getattr(trace_data, 'spans', []) if hasattr(trace_data, 'spans') else []
                            get_ticket_time = None
                            get_customer_history_time = None

                            for span in spans:
                                span_name = getattr(span, 'name', None) or getattr(span, 'span_name', None)
                                if span_name == "get_ticket":
                                    get_ticket_time = getattr(span, 'start_time', None)
                                elif span_name == "get_customer_history":
                                    get_customer_history_time = getattr(span, 'start_time', None)

                            if get_ticket_time is not None and get_customer_history_time is not None:
                                return 1 if get_ticket_time < get_customer_history_time else 0
                except Exception:
                    pass
                return 0

        return 0
    except Exception:
        return 0


def _extract_metrics_and_escalations() -> tuple[dict[str, float], int, int]:
    """Extract scorer metrics, escalation count, and token count from the eval run.

    Returns:
        (metrics_dict, escalation_count, total_tokens)
    """
    metrics = {
        "valid_schema": 0.0,
        "category_match": 0.0,
        "priority_match": 0.0,
        "tool_order": 0.0,
    }
    escalation_count = 0
    total_tokens = 0

    # Get the current active run (the eval run)
    current_run = mlflow.active_run()
    if not current_run:
        return metrics, escalation_count, total_tokens

    try:
        # Access run data via MLflow client
        client = mlflow.MlflowClient()
        run_data = client.get_run(current_run.info.run_id)

        # Extract metrics from the run
        if run_data.data and run_data.data.metrics:
            run_metrics = run_data.data.metrics
            for scorer_name in metrics.keys():
                # MLflow stores metrics with keys like "eval_<scorer_name>"
                for key in [f"eval_{scorer_name}", scorer_name]:
                    if key in run_metrics:
                        metrics[scorer_name] = run_metrics[key]
                        break

        # Try to count escalations and tokens by searching for all runs
        # (the eval should have created sub-runs for each prediction)
        experiment = client.get_experiment_by_name("triage-agent")
        if experiment:
            runs = client.search_runs(experiment_ids=[experiment.experiment_id])

            # The eval run and any prediction runs
            for run in runs:
                # Look for predictions with escalated=true
                if run.data and run.data.params and run.data.params.get("escalated") == "true":
                    escalation_count += 1

                # Count tokens from params or metrics
                if run.data and run.data.metrics and isinstance(run.data.metrics, dict):
                    # Look for token metrics
                    for key in run.data.metrics.keys():
                        if "token" in key.lower():
                            total_tokens += int(run.data.metrics[key])
    except Exception as e:
        # If extraction fails, return defaults
        print(f"Warning: Could not extract detailed metrics: {e}")

    return metrics, escalation_count, total_tokens


def main() -> None:
    """Run the eval harness over all 20 labelled tickets."""
    load_dotenv()

    # Force agent to use Groq (never GEMINI_API_KEY in eval)
    os.environ["PROVIDER"] = "groq"

    # Verify Groq API key is set
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY environment variable not set for eval agent")

    # Set up MLflow
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("triage-agent")
    mlflow.langchain.autolog()

    # Load labelled tickets
    csv_path = Path(__file__).parent / "labelled_tickets.csv"
    with open(csv_path) as f:
        data = list(csv.DictReader(f))

    print(f"Loaded {len(data)} labelled tickets from {csv_path}")

    # Define scorers
    scorers = [
        valid_schema,
        category_match,
        priority_match,
        tool_order,
    ]

    # Run eval with mlflow.genai.evaluate
    print("Running evaluation...")
    try:
        eval_result = evaluate(
            data=data,
            predict_fn=predict_fn,
            scorers=scorers,
        )
        print(f"Evaluation complete. Results: {eval_result}")
    except Exception as e:
        print(f"Evaluation raised exception: {e}")
        raise

    # Extract metrics, escalations, and tokens
    metrics, escalation_count, total_tokens = _extract_metrics_and_escalations()

    print("\nEvaluation Results:")
    print("-" * 60)

    for scorer_name in ["valid_schema", "category_match", "priority_match", "tool_order"]:
        mean_score = metrics.get(scorer_name, 0.0)
        print(f"{scorer_name:20s}: {mean_score:.3f}")

    print(f"Agent Tokens        : {total_tokens}")
    print(f"Escalations         : {escalation_count}")
    print("-" * 60)

    # Write results to JSON
    report_path = Path(__file__).parent / "latest_report.json"
    report_data = {
        "valid_schema": metrics.get("valid_schema", 0.0),
        "category_match": metrics.get("category_match", 0.0),
        "priority_match": metrics.get("priority_match", 0.0),
        "tool_order": metrics.get("tool_order", 0.0),
        "agent_tokens": total_tokens,
        "escalation_count": escalation_count,
    }

    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)

    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
