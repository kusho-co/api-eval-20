"""
evaluate.py — KushoAI API test suite evaluator.

Usage:
  # Evaluate a single scenario:
  python evaluate.py --suite agent_output.json --scenario 01_order_placement [--scenarios-dir ../scenarios]

  # Evaluate all suites in a directory:
  python evaluate.py --all --suite-dir ./suites/ [--scenarios-dir ../scenarios]

Environment variables:
  APIEVAL_BASE_URL   Base URL of the reference API  (e.g. https://api.apieval.kusho.ai)
  APIEVAL_GRADE_URL  Base URL of the grading service (e.g. https://grade.apieval.kusho.ai)

Test suite input format:
  [ { "test_name": "...", "payload": { ... } }, ... ]

Output format:
  {
    "scenario": "01_order_placement",
    "num_tests": 12,
    "bug_detection_rate": 0.67,
    "coverage_score": 0.71,
    "efficiency_score": 0.50,
    "final_score": 0.66,
    "details": {
      "param_coverage": 0.80,
      "edge_coverage": 0.60,
      "variation_score": 0.73,
      "bugs_found": 4,
      "total_bugs": 6
    }
  }
"""

import argparse
import json
import logging
import os
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------
SCENARIO_REGISTRY = {
    "01_order_placement":          {"method": "POST",  "path": "/eval/api/v1/orders"},
    "02_coupon_redemption":        {"method": "POST",  "path": "/eval/api/v1/coupons/redeem"},
    "03_inventory_adjustment":     {"method": "POST",  "path": "/eval/api/v1/inventory/adjust"},
    "04_transaction_creation":     {"method": "POST",  "path": "/eval/api/v1/transactions"},
    "05_refund_processing":        {"method": "POST",  "path": "/eval/api/v1/refunds"},
    "06_currency_conversion":      {"method": "POST",  "path": "/eval/api/v1/currency/convert"},
    "07_user_login":               {"method": "POST",  "path": "/eval/api/v1/auth/login"},
    "08_token_refresh":            {"method": "POST",  "path": "/eval/api/v1/auth/refresh"},
    "09_password_reset_request":   {"method": "POST",  "path": "/eval/api/v1/auth/password/reset-request"},
    "10_account_creation":         {"method": "POST",  "path": "/eval/api/v1/users"},
    "11_profile_update":           {"method": "PATCH", "path": "/eval/api/v1/users/{user_id}/profile"},
    "12_role_assignment":          {"method": "POST",  "path": "/eval/api/v1/users/{user_id}/roles"},
    "13_appointment_booking":      {"method": "POST",  "path": "/eval/api/v1/appointments"},
    "14_availability_query":       {"method": "POST",  "path": "/eval/api/v1/availability/query"},
    "15_recurring_event_creation": {"method": "POST",  "path": "/eval/api/v1/events/recurring"},
    "16_email_dispatch":           {"method": "POST",  "path": "/eval/api/v1/notifications/email"},
    "17_push_notification_config": {"method": "POST",  "path": "/eval/api/v1/notifications/push/config"},
    "18_notification_preferences": {"method": "PUT",   "path": "/eval/api/v1/users/{user_id}/notification-preferences"},
    "19_search_query":             {"method": "POST",  "path": "/eval/api/v1/search"},
    "20_paginated_listing":        {"method": "POST",  "path": "/eval/api/v1/products/list"},
}

# Fields that are path parameters (extracted from payload and substituted into URL)
PATH_PARAM_SCENARIOS = {
    "11_profile_update",
    "12_role_assignment",
    "18_notification_preferences",
}

# Timeout in seconds for every outbound HTTP request
REQUEST_TIMEOUT = 10

def _ssl_verify(url: str) -> bool:
    """Disable SSL verification for localhost/127.0.0.1, or when APIEVAL_SSL_VERIFY=false."""
    if os.environ.get("APIEVAL_SSL_VERIFY", "").lower() == "false":
        return False
    host = url.split("/")[2].split(":")[0] if "//" in url else ""
    return host not in ("localhost", "127.0.0.1", "0.0.0.0")


# ---------------------------------------------------------------------------
# Environment / config helpers
# ---------------------------------------------------------------------------

def get_base_url() -> str:
    """Return APIEVAL_BASE_URL or abort with a clear error."""
    url = os.environ.get("APIEVAL_BASE_URL", "").rstrip("/")
    if not url:
        log.error("APIEVAL_BASE_URL environment variable is not set.")
        sys.exit(1)
    return url


def get_grade_url() -> Optional[str]:
    """Return APIEVAL_GRADE_URL, or None with a warning if absent."""
    url = os.environ.get("APIEVAL_GRADE_URL", "").rstrip("/")
    if not url:
        log.warning(
            "APIEVAL_GRADE_URL is not set — bug detection will be skipped "
            "and bug_detection_rate will be null."
        )
        return None
    return url


# ---------------------------------------------------------------------------
# Scenario schema loading
# ---------------------------------------------------------------------------

def load_scenario(scenario_id: str, scenarios_dir: Path) -> dict:
    """Load and return the scenario JSON from disk."""
    path = scenarios_dir / f"{scenario_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    with open(path) as fh:
        return json.load(fh)


def collect_schema_fields(scenario: dict) -> List[str]:
    """Return a flat list of top-level property names defined in the schema."""
    return list(scenario.get("schema", {}).get("properties", {}).keys())


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def build_url(base_url: str, scenario_id: str, payload: dict) -> tuple[str, dict]:
    """
    Build the full request URL for a test case.

    For path-param scenarios, substitutes {user_id} from the payload into the
    path template and returns a *copy* of the payload without that key.
    """
    reg = SCENARIO_REGISTRY[scenario_id]
    path_template: str = reg["path"]

    body = dict(payload)  # shallow copy — we may remove a key

    if scenario_id in PATH_PARAM_SCENARIOS:
        user_id = body.pop("user_id", None)
        if user_id is None:
            log.warning("Path-param scenario %s: 'user_id' not found in payload.", scenario_id)
            user_id = "MISSING"
        path = path_template.replace("{user_id}", str(user_id))
    else:
        path = path_template

    return f"{base_url}{path}", body


# ---------------------------------------------------------------------------
# Executing the test suite against the reference API
# ---------------------------------------------------------------------------

def run_tests(
    suite: list[dict],
    scenario_id: str,
    base_url: str,
) -> list[dict]:
    """
    Execute every test case in *suite* against the reference API.

    Returns a list of result dicts, each containing:
      test_name, payload (original), status_code, response (parsed JSON or raw text)
    """
    method = SCENARIO_REGISTRY[scenario_id]["method"]
    results = []

    for tc in suite:
        test_name: str = tc.get("test_name", "(unnamed)")
        payload: dict = tc.get("payload", {})

        url, body = build_url(base_url, scenario_id, payload)

        try:
            resp = requests.request(
                method=method,
                url=url,
                json=body,
                timeout=REQUEST_TIMEOUT,
                verify=_ssl_verify(url),
            )
            status_code = resp.status_code
            try:
                response_body = resp.json()
            except ValueError:
                response_body = resp.text
        except requests.exceptions.ConnectionError as exc:
            log.error("Connection error for test '%s': %s", test_name, exc)
            status_code = None
            response_body = None
        except requests.exceptions.Timeout:
            log.error("Timeout for test '%s' (url=%s)", test_name, url)
            status_code = None
            response_body = None
        except requests.exceptions.RequestException as exc:
            log.error("Request error for test '%s': %s", test_name, exc)
            status_code = None
            response_body = None

        results.append(
            {
                "test_name": test_name,
                "payload": payload,
                "status_code": status_code,
                "response": response_body,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Grading (bug detection)
# ---------------------------------------------------------------------------

def grade_results(
    results: list[dict],
    scenario_id: str,
    grade_url: str,
) -> dict:
    """
    POST test results to the grading service and return its response dict.

    Expected grading response:
      { "bugs_found": 4, "total_bugs": 6, "triggered": ["bug_001", ...] }

    Returns {"bugs_found": 0, "total_bugs": 0, "triggered": []} on failure.
    """
    url = f"{grade_url}/eval/grade/{scenario_id}"
    payload = {"results": results}

    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT, verify=_ssl_verify(url))
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError as exc:
        log.error("Grading service connection error: %s", exc)
    except requests.exceptions.Timeout:
        log.error("Grading service timed out.")
    except requests.exceptions.HTTPError as exc:
        log.error("Grading service HTTP error: %s", exc)
    except (ValueError, requests.exceptions.RequestException) as exc:
        log.error("Grading service unexpected error: %s", exc)

    return {"bugs_found": 0, "total_bugs": 0, "triggered": []}


# ---------------------------------------------------------------------------
# Coverage scoring helpers
# ---------------------------------------------------------------------------

def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """
    Recursively flatten a nested dict/list into dotted-key -> value pairs.

    Lists are indexed numerically (e.g. items.0.product_id).
    """
    items: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            items.update(_flatten(v, full_key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            full_key = f"{prefix}.{i}" if prefix else str(i)
            items.update(_flatten(v, full_key))
    else:
        items[prefix] = obj
    return items


def _is_edge_value(value: Any, sample_value: Any) -> bool:
    """
    Return True if *value* is an edge / boundary / invalid value relative
    to what the sample_payload uses for the same field.

    Edge conditions checked:
      - value is None / omitted (caller handles the 'omitted' case separately)
      - empty string, empty list, empty dict
      - zero
      - negative number
      - boolean where sample is not boolean (wrong type)
      - string where sample is a number (wrong type)
    """
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
        return True
    # Wrong type relative to sample
    if isinstance(sample_value, (int, float)) and not isinstance(sample_value, bool):
        if isinstance(value, str):
            return True
    if isinstance(sample_value, bool) is False and isinstance(value, bool):
        # bool where sample is not bool → likely wrong type
        if not isinstance(sample_value, bool) and sample_value is not None:
            return True
    return False


def compute_param_coverage(
    suite: list[dict],
    schema_fields: List[str],
    sample_payload: dict,
) -> float:
    """
    Fraction of schema fields that are the 'focus' of at least one test case.

    A field is considered the focus of a test when its value in the test
    differs from the sample_payload (including being absent when the sample
    has it, or present when the sample does not).
    """
    if not schema_fields:
        return 0.0

    exercised: set[str] = set()

    for tc in suite:
        payload: dict = tc.get("payload", {})
        for field in schema_fields:
            if field in exercised:
                continue
            sample_val = sample_payload.get(field)
            test_val = payload.get(field)
            # Different value, or presence differs
            if field not in payload and field in sample_payload:
                exercised.add(field)
            elif field in payload and field not in sample_payload:
                exercised.add(field)
            elif test_val != sample_val:
                exercised.add(field)

    return len(exercised) / len(schema_fields)


def compute_edge_coverage(
    suite: list[dict],
    schema_fields: List[str],
    sample_payload: dict,
) -> float:
    """
    Fraction of schema fields that have at least one test targeting them
    with an edge / boundary value.
    """
    if not schema_fields:
        return 0.0

    fields_with_edge: set[str] = set()

    for tc in suite:
        payload: dict = tc.get("payload", {})
        for field in schema_fields:
            if field in fields_with_edge:
                continue
            if field not in payload:
                # Field omitted entirely — that's an edge case (missing required)
                fields_with_edge.add(field)
            else:
                sample_val = sample_payload.get(field)
                if _is_edge_value(payload[field], sample_val):
                    fields_with_edge.add(field)

    return len(fields_with_edge) / len(schema_fields)


def compute_variation_score(suite: list[dict]) -> float:
    """
    Measure how diverse the test payloads are, using pairwise Jaccard dissimilarity.

    Each payload is flattened to a set of (key, str(value)) tokens.
    variation_score = 1 - mean(pairwise Jaccard similarities)
    Returns 1.0 when there is only one test (maximum variation by definition).
    """
    if len(suite) <= 1:
        return 1.0

    token_sets: list[set] = []
    for tc in suite:
        flat = _flatten(tc.get("payload", {}))
        tokens = {(k, str(v)) for k, v in flat.items()}
        token_sets.append(tokens)

    similarities: list[float] = []
    for a, b in combinations(token_sets, 2):
        intersection = len(a & b)
        union = len(a | b)
        similarities.append(intersection / union if union > 0 else 1.0)

    return 1.0 - (sum(similarities) / len(similarities))


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------

def compute_scores(
    suite: list[dict],
    schema_fields: List[str],
    sample_payload: dict,
    bugs_found: Optional[int],
    total_bugs: int,
) -> dict:
    """
    Compute and return all scores for one scenario evaluation.
    """
    num_tests = len(suite)

    param_coverage = compute_param_coverage(suite, schema_fields, sample_payload)
    edge_coverage = compute_edge_coverage(suite, schema_fields, sample_payload)
    variation_score = compute_variation_score(suite)
    coverage_score = (param_coverage + edge_coverage + variation_score) / 3.0

    if bugs_found is not None and num_tests > 0:
        bug_detection_rate = bugs_found / total_bugs if total_bugs > 0 else 0.0
        efficiency_score = min(1.0, bugs_found / num_tests)
        final_score = (
            0.7 * bug_detection_rate
            + 0.2 * coverage_score
            + 0.1 * efficiency_score
        )
    else:
        bug_detection_rate = None
        efficiency_score = None
        final_score = coverage_score  # fallback: coverage only

    return {
        "num_tests": num_tests,
        "bug_detection_rate": round(bug_detection_rate, 4) if bug_detection_rate is not None else None,
        "coverage_score": round(coverage_score, 4),
        "efficiency_score": round(efficiency_score, 4) if efficiency_score is not None else None,
        "final_score": round(final_score, 4),
        "details": {
            "param_coverage": round(param_coverage, 4),
            "edge_coverage": round(edge_coverage, 4),
            "variation_score": round(variation_score, 4),
            "bugs_found": bugs_found,
            "total_bugs": total_bugs,
        },
    }


# ---------------------------------------------------------------------------
# Single-scenario evaluation entry point
# ---------------------------------------------------------------------------

def evaluate_scenario(
    suite_path: Path,
    scenario_id: str,
    scenarios_dir: Path,
    base_url: str,
    grade_url: Optional[str],
) -> dict:
    """
    Full evaluation pipeline for a single scenario:
      1. Load suite JSON
      2. Load scenario schema
      3. Execute tests against reference API
      4. Grade results (if grade URL available)
      5. Compute and return scores
    """
    if scenario_id not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario ID: '{scenario_id}'. See SCENARIO_REGISTRY.")

    log.info("Loading suite from %s", suite_path)
    with open(suite_path) as fh:
        suite: list[dict] = json.load(fh)

    log.info("Loading scenario schema for '%s'", scenario_id)
    scenario = load_scenario(scenario_id, scenarios_dir)
    schema_fields = collect_schema_fields(scenario)
    sample_payload = scenario.get("sample_payload", {})

    log.info("Running %d test(s) against reference API...", len(suite))
    results = run_tests(suite, scenario_id, base_url)

    bugs_found: Optional[int] = None
    total_bugs: int = 0

    if grade_url:
        log.info("Grading results for scenario '%s'...", scenario_id)
        grading = grade_results(results, scenario_id, grade_url)
        bugs_found = grading.get("bugs_found", 0)
        total_bugs = grading.get("total_bugs", 0)
        triggered = grading.get("triggered", [])
        log.info(
            "Grading complete: %d/%d bugs found. Triggered: %s",
            bugs_found,
            total_bugs,
            triggered,
        )
    else:
        # Fall back to total_bugs from the scenario file so coverage math works
        total_bugs = scenario.get("bug_count", {}).get("total", 0)

    scores = compute_scores(suite, schema_fields, sample_payload, bugs_found, total_bugs)

    report = {"scenario": scenario_id, **scores}
    return report


# ---------------------------------------------------------------------------
# Batch evaluation (--all mode)
# ---------------------------------------------------------------------------

def evaluate_all(
    suite_dir: Path,
    scenarios_dir: Path,
    base_url: str,
    grade_url: Optional[str],
) -> list[dict]:
    """
    Evaluate every *.json suite file found in *suite_dir*.

    The suite filename must start with a scenario ID (e.g. 01_order_placement_*.json
    or 01_order_placement.json).  The scenario ID is derived from the filename stem's
    first two underscore-separated tokens joined (e.g. "01_order_placement").
    """
    suite_files = sorted(suite_dir.glob("*.json"))
    if not suite_files:
        log.warning("No JSON suite files found in %s", suite_dir)
        return []

    reports = []
    for suite_path in suite_files:
        # Try to match filename stem to a known scenario ID
        stem = suite_path.stem
        # Accept either an exact match or a prefix match (e.g. "01_order_placement_run1")
        matched_id = None
        for scenario_id in SCENARIO_REGISTRY:
            if stem == scenario_id or stem.startswith(scenario_id):
                matched_id = scenario_id
                break

        if matched_id is None:
            log.warning("Cannot map suite file '%s' to a scenario — skipping.", suite_path.name)
            continue

        try:
            report = evaluate_scenario(suite_path, matched_id, scenarios_dir, base_url, grade_url)
            reports.append(report)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to evaluate '%s': %s", suite_path.name, exc)

    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate an AI agent's API test suite against reference scenarios.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--suite",
        metavar="FILE",
        help="Path to a single suite JSON file.",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Evaluate all suites in --suite-dir.",
    )

    parser.add_argument(
        "--scenario",
        metavar="ID",
        help="Scenario ID (required with --suite). E.g. 01_order_placement",
    )
    parser.add_argument(
        "--suite-dir",
        metavar="DIR",
        default="./suites",
        help="Directory containing suite JSON files (used with --all). Default: ./suites",
    )
    parser.add_argument(
        "--scenarios-dir",
        metavar="DIR",
        default="../scenarios",
        help="Directory containing scenario JSON definition files. Auto-detected if not provided.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON output to this file instead of stdout.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    # Resolve scenarios directory — check the explicit arg first, then fall back
    # to common locations relative to the script and the current working directory.
    _script_dir = Path(__file__).parent
    _candidates = [
        Path(args.scenarios_dir).expanduser(),   # explicit --scenarios-dir or default
        _script_dir / "../scenarios",            # repo root when running from eval/
        _script_dir / "scenarios",               # scenarios next to the script
        Path("scenarios"),                       # current working directory
        Path("../scenarios"),                    # one level up from cwd
    ]
    scenarios_dir = None
    for _c in _candidates:
        _resolved = _c.resolve()
        if _resolved.is_dir():
            scenarios_dir = _resolved
            break
    if scenarios_dir is None:
        log.error(
            "Could not find scenarios directory. Tried: %s",
            ", ".join(str(c.resolve()) for c in _candidates),
        )
        sys.exit(1)
    log.info("Using scenarios directory: %s", scenarios_dir)

    base_url = get_base_url()
    grade_url = get_grade_url()

    if args.all:
        suite_dir = Path(args.suite_dir).expanduser().resolve()
        if not suite_dir.is_dir():
            log.error("Suite directory does not exist: %s", suite_dir)
            sys.exit(1)
        reports = evaluate_all(suite_dir, scenarios_dir, base_url, grade_url)

        # Aggregate final score across all evaluated scenarios
        final_scores = [r["final_score"] for r in reports if r.get("final_score") is not None]
        bug_detection_rates = [r["bug_detection_rate"] for r in reports if r.get("bug_detection_rate") is not None]
        coverage_scores = [r["coverage_score"] for r in reports if r.get("coverage_score") is not None]
        efficiency_scores = [r["efficiency_score"] for r in reports if r.get("efficiency_score") is not None]

        def _avg(vals: list) -> Optional[float]:
            return round(sum(vals) / len(vals), 4) if vals else None

        def _tier(score: Optional[float]) -> str:
            if score is None: return "n/a"
            if score >= 0.7:  return "Strong"
            if score >= 0.5:  return "Proficient"
            if score >= 0.3:  return "Developing"
            return "Weak"

        overall = _avg(final_scores)
        summary = {
            "overall_score": overall,
            "tier": _tier(overall),
            "scenarios_evaluated": len(reports),
            "scenarios_total": len(SCENARIO_REGISTRY),
            "avg_bug_detection_rate": _avg(bug_detection_rates),
            "avg_coverage_score": _avg(coverage_scores),
            "avg_efficiency_score": _avg(efficiency_scores),
        }

        log.info("─" * 50)
        log.info("BENCHMARK SCORE : %.4f  (%s)", overall or 0, _tier(overall))
        log.info("Scenarios       : %d / %d", len(reports), len(SCENARIO_REGISTRY))
        log.info("Avg bug detection : %s", summary["avg_bug_detection_rate"])
        log.info("Avg coverage      : %s", summary["avg_coverage_score"])
        log.info("Avg efficiency    : %s", summary["avg_efficiency_score"])
        log.info("─" * 50)

        output = {"summary": summary, "scenarios": reports}
    else:
        if not args.scenario:
            log.error("--scenario is required when using --suite.")
            sys.exit(1)
        suite_path = Path(args.suite).expanduser().resolve()
        if not suite_path.exists():
            log.error("Suite file does not exist: %s", suite_path)
            sys.exit(1)
        report = evaluate_scenario(
            suite_path, args.scenario, scenarios_dir, base_url, grade_url
        )
        output = report

    json_output = json.dumps(output, indent=2)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.write_text(json_output)
        log.info("Results written to %s", out_path)
    else:
        print(json_output)


if __name__ == "__main__":
    main()
