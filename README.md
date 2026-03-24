---
annotations_creators:
  - expert-generated
language:
  - en
language_creators:
  - expert-generated
license: mit
multilinguality:
  - monolingual
pretty_name: APIEval-20
size_categories:
  - n<100
source_datasets:
  - original
tags:
  - api-testing
  - black-box-testing
  - agent-benchmark
  - software-testing
  - qa
  - code
task_categories:
  - text-generation
task_ids:
  - language-modeling
dataset_info:
  config_name: default
  features:
    - name: scenario_id
      dtype: string
    - name: domain
      dtype: string
    - name: endpoint
      dtype: string
    - name: method
      dtype: string
    - name: schema
      dtype: string
    - name: sample_payload
      dtype: string
    - name: bug_count
      dtype: int32
    - name: bug_complexity_simple
      dtype: int32
    - name: bug_complexity_moderate
      dtype: int32
    - name: bug_complexity_complex
      dtype: int32
  splits:
    - name: test
      num_examples: 20
  homepage: https://huggingface.co/datasets/kusho-ai/api-eval-20
  license: mit
---

# APIEval-20: A Benchmark for Black-Box API Test Suite Generation

---

## Motivation

Testing APIs thoroughly is one of the most critical, yet consistently underserved, activities in software engineering. Despite a rich ecosystem of API testing tools — Postman, RestAssured, Schemathesis, Dredd, and others — we found ourselves asking a deceptively simple question:

**Given only the schema and an example payload of an API request — no source code, no documentation, no prior knowledge — how well can an AI agent generate a test suite that actually finds bugs?**

We searched for an existing benchmark that captured this black-box scenario and came up empty. Every evaluation we found either required access to the implementation, relied on rich API documentation, or measured properties like schema compliance rather than actual bug-finding capability. The practitioner reality is different: teams frequently receive API payloads with little context and need to construct meaningful tests quickly.

That gap is the reason **APIEval-20** exists.

APIEval-20 is not a model benchmark. It is a **task benchmark for AI agents**. It evaluates end-to-end agent behavior — the ability to reason about an API surface, design targeted tests, and uncover real bugs — not just the quality of generated text.

---

## 1. Benchmark Overview

APIEval-20 consists of 20 carefully designed API scenarios drawn from real-world application domains. Each scenario presents the agent with an API request schema and a sample payload, then challenges it to produce a test suite that exposes bugs hidden within a live reference implementation.

### Domains Covered

The 20 scenarios span the following application domains, chosen to reflect a broad range of validation patterns, business logic complexity, and security sensitivity:

| Domain | Scenarios |
|---|---|
| **E-commerce** | Order placement, coupon redemption, inventory adjustment |
| **Payments** | Transaction creation, refund processing, currency conversion |
| **Authentication** | Login, token refresh, password reset, session management |
| **User Management** | Account creation, profile update, role assignment |
| **Scheduling** | Appointment booking, availability queries, recurring events |
| **Notifications** | Email dispatch, push configuration, preference management |
| **Search & Filtering** | Query construction, pagination, sort and rank |

---

## 2. Bug Spectrum

Each scenario contains between 3 and 8 planted bugs. Rather than categorising bugs by severity, APIEval-20 classifies them by **complexity** — reflecting how much reasoning is required to discover them. Bugs range along a continuum from simple to complex.

### Simple Bugs

Require no semantic understanding of the domain. They test whether the API handles basic structural issues correctly: missing required fields, empty values (`""`, `null`, `[]`), and wrong data types.

### Moderate Bugs

Require understanding the meaning of individual fields and their constraints: numeric values outside valid range, strings violating format constraints (malformed email, invalid currency code, wrong date format), and enum fields receiving boundary or undocumented values.

### Complex Bugs

Require understanding the *relationship* between multiple fields, or the broader semantics of the operation: mutually exclusive fields both provided, discounts applied to ineligible orders, fields whose validity depends on the value of another field.

**A strong test suite should span the full complexity spectrum — simple structural checks alone will not surface the bugs that matter most in production.**

---

## 3. Agent I/O

### What the Agent Receives

For each scenario, the agent is given exactly two inputs. Nothing else — no response schema, no implementation details, no error messages, no changelog. This deliberate constraint reflects the black-box testing reality and prevents agents from trivially exploiting documentation.

1. **JSON Schema** — The full request schema: field names, types, required/optional status, and any documented constraints.
2. **Sample Payload** — A concrete example of a valid request, showing realistic field values.

**Example Input — `POST /api/v1/orders`**

Schema:
```json
{
  "user_id":    { "type": "string",  "required": true },
  "items":      { "type": "array",   "required": true,
    "items": { "product_id": "string", "quantity": "integer", "unit_price": "number" } },
  "coupon_code": { "type": "string",  "required": false },
  "currency":   { "type": "string",  "required": true, "description": "ISO 4217 currency code" },
  "shipping":   { "type": "object",  "required": true,
    "properties": { "address": "string", "method": "string" } }
}
```

Sample Payload:
```json
{
  "user_id": "usr_4821",
  "items": [
    { "product_id": "prod_991", "quantity": 2, "unit_price": 29.99 }
  ],
  "coupon_code": "SAVE10",
  "currency": "USD",
  "shipping": {
    "address": "123 Main St, Springfield",
    "method": "standard"
  }
}
```

### What the Agent Produces

The agent must output a **test suite** — a list of test cases, where each test case contains a short human-readable test name and the complete request payload as a valid JSON object. No expected outcome is required. Evaluation is performed by running each test case against the live reference implementation and observing what actually happens.

**Example Test Case Output:**
```json
{
  "test_name": "Order with zero quantity item",
  "payload": {
    "user_id": "usr_4821",
    "items": [{ "product_id": "prod_991", "quantity": 0, "unit_price": 29.99 }],
    "currency": "USD",
    "shipping": { "address": "123 Main St, Springfield", "method": "standard" }
  }
}
```

---

## 4. Evaluation Methodology

All 20 reference API implementations are deployed and running. Evaluation is fully automated: each test case in the agent's output is executed against the live API, and the responses are analysed to determine which planted bugs were triggered.

A bug is considered **detected** if at least one test case in the suite produces a response that deviates from the correct behaviour in a way that corresponds to the planted bug — for example, a `200 OK` where a `400` should have been returned, or a silently incorrect computed value in the response body.

---

## 5. Scoring

The final score combines three factors, weighted to emphasise real-world value: finding bugs matters most, systematic coverage rewards thoroughness, and efficiency discourages noise.

| Component | Weight | Description |
|---|---|---|
| Bug Detection Score | 70% | Primary metric |
| Coverage Score | 20% | API surface exploration |
| Efficiency Score | 10% | Signal-to-noise ratio |

### Bug Detection Score — Primary (70%)

Measures how many of the planted bugs were successfully triggered. This is the core metric of the benchmark — an agent that finds more bugs scores higher, regardless of how it gets there.

```
Bug Detection Rate = bugs_found / total_bugs
```

**Range: 0 – 1.** A score of 1 means every planted bug was triggered; 0 means none were. Scores below 0.3 indicate the agent is missing most bugs; above 0.7 is considered strong performance on a scenario.

### Coverage Score — 20%

Measures how well the test suite explores the API surface across three independently computed dimensions. Each dimension produces a value between 0 and 1; the three are averaged to produce the final Coverage Score.

```
Coverage Score = (param_coverage + edge_coverage + variation_score) / 3
```

**Range: 0 – 1.** All three sub-dimensions are individually bounded [0, 1], so the average is too. A score of 1 requires full field coverage, edge tests on every field, and completely non-overlapping payloads — a high bar that rewards comprehensive, systematic suites.

#### Parameter Coverage

What fraction of schema fields are the *focus* of at least one test — i.e., differ from the valid sample payload in that test case (modified, omitted, or set to an alternate value).

```
param_coverage = fields_exercised / total_schema_fields
```

#### Edge Case Coverage

What fraction of schema fields have at least one test that targets them with a recognised edge value. Edge values are: field omitted entirely, `null`, `""`, `[]`, wrong type, zero or negative number, and out-of-range value.

```
edge_coverage = fields_with_edge_test / total_schema_fields
```

#### Input Variation

Penalises suites that repeat near-identical payloads. Computed as one minus the average pairwise Jaccard similarity across all test payload pairs, where each payload is treated as a set of `(field, value)` pairs.

```
variation_score = 1 − mean(Jaccard(tᵢ, tⱼ))  ∀ i ≠ j
```

A score of 1 means every test is completely distinct; a score approaching 0 means the suite is largely repetitive.

### Efficiency Score — 10%

Penalises unnecessarily large test suites. A suite that finds 6 bugs with 10 tests is more valuable than one that finds the same 6 bugs with 80 tests.

```
Efficiency = min(1, bugs_found / number_of_tests)
```

**Range: 0 – 1.** The raw ratio is capped at 1 to keep the metric bounded. A score of 1 means the suite finds at least one bug per test — the theoretical ideal. The score degrades linearly as redundant tests accumulate: a suite with 5× more tests than bugs found scores 0.2. An agent that finds no bugs scores 0 regardless of suite size.

### Final Score Formula

```
Final Score =
  0.7 × Bug Detection Rate
+ 0.2 × Coverage Score
+ 0.1 × Efficiency Score
```

The final benchmark score for an agent is the **average Final Score across all 20 scenarios**. Since all three components are bounded [0, 1], the Final Score is also bounded [0, 1].

| Score Range | Interpretation |
|---|---|
| **0.0 – 0.3** · Weak | The agent finds few bugs, covers limited fields, and may produce repetitive or low-signal tests. Likely relies on trivial structural mutations only. |
| **0.3 – 0.5** · Developing | The agent demonstrates awareness of edge cases but misses moderate and complex bugs. Coverage is partial and efficiency is inconsistent. |
| **0.5 – 0.7** · Proficient | The agent finds most simple and moderate bugs with reasonable coverage. Complex cross-field bugs remain elusive. Efficiency is generally good. |
| **0.7 – 1.0** · Strong | The agent surfaces bugs across all complexity tiers, achieves broad field and edge case coverage, and keeps the test suite lean. Comparable to a thorough human QA engineer. |

---

## 6. Why This Benchmark Matters

APIEval-20 evaluates a capability that is largely unmeasured today. It goes beyond simple code generation or factual reasoning — it measures something more practically valuable.

- **Limited-information reasoning** — Understanding API behaviour from schema and payload alone, without implementation access.
- **Unsupervised edge case discovery** — Identifying edge cases without being told where to look or what to test.
- **Targeted test strategy design** — Designing effective, minimal test suites that maximise bug-finding per test.
- **Multi-tier bug uncovering** — Finding bugs across simple, moderate, and complex complexity levels.

**How well can an AI agent think like a QA engineer?** Most existing benchmarks evaluate whether a model can produce syntactically correct output. APIEval-20 evaluates whether an agent can *do useful work* — work that directly maps to a real engineering task with measurable outcomes.

---

## 7. Running the APIEval-20 Evaluator

### Prerequisites
- Python 3.8 or later

### Setup
```bash
# Clone the dataset repo
git clone https://huggingface.co/datasets/kusho-ai/api-eval-20
cd api-eval-20

# Install the single dependency
pip install -r eval/requirements.txt
```

### Configuration
Set the following environment variables before running:
```bash
export APIEVAL_BASE_URL="https://<tbd>"
export APIEVAL_GRADE_URL="https://<tbd>"
```
`APIEVAL_GRADE_URL` is optional. If omitted, bug detection scoring is skipped and the evaluator returns coverage and efficiency scores only.

### Test Suite Format
Your agent must produce a JSON file containing a list of test cases. Each test case has a `test_name` and a `payload`:
```json
[
  {
    "test_name": "Order with missing user_id",
    "payload": {
      "items": [{ "product_id": "prod_991", "quantity": 2, "unit_price": 29.99 }],
      "currency": "USD",
      "shipping": { "address": "123 Main St", "method": "standard", "country": "US" }
    }
  },
  {
    "test_name": "Order with zero quantity",
    "payload": {
      "user_id": "usr_4821",
      "items": [{ "product_id": "prod_991", "quantity": 0, "unit_price": 29.99 }],
      "currency": "USD",
      "shipping": { "address": "123 Main St", "method": "standard", "country": "US" }
    }
  }
]
```
One file per scenario. The scenario schemas and sample payloads are in the `scenarios/` folder.

### Evaluating a Single Scenario
```bash
python eval/evaluate.py \
  --suite path/to/your_suite.json \
  --scenario 01_order_placement
```
Output:
```json
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
```

### Evaluating All 20 Scenarios
Place all your suite files in a single directory, named `<scenario_id>_suite.json`:
```
suites/
  01_order_placement_suite.json
  02_coupon_redemption_suite.json
  ...
  20_paginated_listing_suite.json
```
Then run:
```bash
python eval/evaluate.py \
  --all \
  --suite-dir ./suites/ \
  --output results.json
```
`results.json` will contain per-scenario scores and an overall benchmark score averaged across all 20 scenarios.

### Scoring Reference
| Component | Weight | Formula |
|---|---|---|
| Bug Detection Rate | 70% | `bugs_found / total_bugs` |
| Coverage Score | 20% | `(param_coverage + edge_coverage + variation_score) / 3` |
| Efficiency Score | 10% | `min(1, bugs_found / num_tests)` |
| **Final Score** | | `0.7 × bug_detection + 0.2 × coverage + 0.1 × efficiency` |
The overall benchmark score is the average Final Score across all 20 scenarios.
| Score | Interpretation |
|---|---|
| 0.0 – 0.3 | Weak |
| 0.3 – 0.5 | Developing |
| 0.5 – 0.7 | Proficient |
| 0.7 – 1.0 | Strong |

### All Scenario IDs
| ID | Scenario | Domain |
|---|---|---|
| `01_order_placement` | Place a new order | E-commerce |
| `02_coupon_redemption` | Redeem a coupon code | E-commerce |
| `03_inventory_adjustment` | Adjust stock quantity | E-commerce |
| `04_transaction_creation` | Create a financial transaction | Payments |
| `05_refund_processing` | Process a refund | Payments |
| `06_currency_conversion` | Convert currency | Payments |
| `07_user_login` | Authenticate a user | Authentication |
| `08_token_refresh` | Refresh an access token | Authentication |
| `09_password_reset_request` | Request a password reset | Authentication |
| `10_account_creation` | Create a user account | User Management |
| `11_profile_update` | Update a user profile | User Management |
| `12_role_assignment` | Assign a role to a user | User Management |
| `13_appointment_booking` | Book an appointment | Scheduling |
| `14_availability_query` | Query available slots | Scheduling |
| `15_recurring_event_creation` | Create a recurring event | Scheduling |
| `16_email_dispatch` | Send a transactional email | Notifications |
| `17_push_notification_config` | Configure push notifications | Notifications |
| `18_notification_preferences` | Set notification preferences | Notifications |
| `19_search_query` | Execute a product search | Search & Filtering |
| `20_paginated_listing` | List products with filters | Search & Filtering |

---

## 8. What Comes Next

APIEval-20 is a **functional testing benchmark**. Every scenario, every planted bug, and every scoring dimension is scoped to functional correctness — how well an agent validates that an API behaves as intended given valid and invalid inputs. Security vulnerabilities, authentication bypasses, injection attacks, and authorization failures are explicitly out of scope here.

This is the first entry in what we plan to be a growing family of API testing benchmarks, each targeting a distinct testing discipline. Coming soon:

### APIEval-Security

A dedicated benchmark for API security testing. Built on the same black-box setup, it evaluates whether an agent can identify authentication weaknesses, authorization flaws, injection vulnerabilities, and other OWASP API Security Top 10 categories from schema and payload alone.

### Agent Benchmark: Coding & Testing Agents

A comprehensive head-to-head comparison of all major coding and testing agents — including Cursor, GitHub Copilot, Devin, and KushoAI — evaluated on the APIEval-20 scenario set. The goal is to give teams a clear, data-driven picture of where each agent stands in the API testing space specifically, not just general coding tasks.

### APIEval-50

A larger scenario set covering 50 APIs with an expanded bug taxonomy, including concurrency bugs, state-dependent failures, and multi-step workflow errors.

---

*APIEval-20 is an open benchmark created by KushoAI to evaluate AI agent capability on black-box API test suite generation. All reference implementations are hosted and maintained by KushoAI. Evaluation is run through the hosted harness to prevent contamination.*

*The benchmark is versioned. Scores reported against APIEval-20 v1.0 are not directly comparable to future versions without explicit cross-version normalisation.*

*For questions, contributions, or issue reports, reach out at [contact@kusho.ai](mailto:contact@kusho.ai) or open an issue on Hugging Face.*

*APIEval-20 — Version 1.0 — 2026*
