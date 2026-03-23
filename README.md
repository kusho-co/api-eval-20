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

**A task benchmark for evaluating AI agents on real-world API testing.**

---

## Motivation

Testing APIs thoroughly is one of the most critical, yet consistently underserved, activities in software engineering. Despite a rich ecosystem of API testing tools — Postman, RestAssured, Schemathesis, Dredd, and others — we found ourselves asking a deceptively simple question:

*Given only the schema and an example payload of an API request — no source code, no documentation, no prior knowledge — how well can an AI agent generate a test suite that actually finds bugs?*

We searched for an existing benchmark that captured this black-box scenario and came up empty. Every evaluation we found either required access to the implementation, relied on rich API documentation, or measured properties like schema compliance rather than actual bug-finding capability. The practitioner reality is different: teams frequently receive API payloads with little context and need to construct meaningful tests quickly.

That gap is the reason **APIEval-20** exists.

**Note:** APIEval-20 is not a model benchmark. It is a **task benchmark for AI agents**. It evaluates end-to-end agent behavior — the ability to reason about an API surface, design targeted tests, and uncover real bugs — not just the quality of generated text.

---

## Benchmark Overview

APIEval-20 consists of 20 carefully designed API scenarios drawn from real-world application domains. Each scenario presents the agent with an API request schema and a sample payload, then challenges it to produce a test suite that exposes bugs hidden within a live reference implementation.

### Domains Covered

The 20 scenarios span the following application domains, chosen to reflect a broad range of validation patterns, business logic complexity, and security sensitivity:

- **E-commerce:** order placement, coupon redemption, inventory adjustment
- **Payments:** transaction creation, refund processing, currency conversion
- **Authentication:** login, token refresh, password reset, session management
- **User management:** account creation, profile update, role assignment
- **Scheduling:** appointment booking, availability queries, recurring events
- **Notifications:** email dispatch, push configuration, preference management
- **Search and filtering:** query construction, pagination, sort and rank

---

### Bug Spectrum

Each scenario contains between 3 and 8 planted bugs. Rather than categorising bugs by severity, APIEval-20 classifies them by **complexity** — reflecting how much reasoning is required to discover them.

Bugs range along a continuum from simple to complex:

**Simple bugs** require no semantic understanding of the domain. They test whether the API handles basic structural issues correctly:
- What happens when a required field is missing entirely?
- What happens when a field is present but empty (`""`, `null`, `[]`)?
- What happens when a field receives the wrong data type?

**Moderate bugs** require understanding the meaning of individual fields and their constraints:
- What happens when a numeric field receives a value outside its valid range (e.g. a negative quantity, a year far in the future)?
- What happens when a string field violates a format constraint (e.g. a malformed email, an invalid currency code, a date in the wrong format)?
- What happens when an enum field receives an undocumented or boundary value?

**Complex bugs** require understanding the *relationship* between multiple fields, or the broader semantics of the operation:
- What happens when two fields are mutually exclusive but both are provided?
- What happens when a discount is applied to an order that doesn't meet the eligibility criteria defined across several fields?
- What happens when a field's validity depends on the value of another field (e.g. a shipping method that is only valid for certain destination countries)?

A strong test suite should span the full complexity spectrum — simple structural checks alone will not surface the bugs that matter most in production.

---

### What the Agent Receives

For each scenario, the agent is given exactly two inputs:

1. **The JSON schema** of the API request — field names, types, required/optional status, and any documented constraints.
2. **A sample payload** — a concrete example of a valid request.

Nothing else. No response schema, no implementation details, no error messages, no changelog. This deliberate constraint reflects the black-box testing reality and prevents agents from trivially exploiting documentation.

**Example input:**

```
POST /api/v1/orders
```

**Schema:**
```json
{
  "user_id":    { "type": "string",  "required": true },
  "items":      { "type": "array",   "required": true, "items": { "product_id": "string", "quantity": "integer", "unit_price": "number" } },
  "coupon_code":{ "type": "string",  "required": false },
  "currency":   { "type": "string",  "required": true, "description": "ISO 4217 currency code" },
  "shipping":   { "type": "object",  "required": true, "properties": { "address": "string", "method": "string" } }
}
```

**Sample payload:**
```json
{
  "user_id": "usr_4821",
  "items": [
    { "product_id": "prod_991", "quantity": 2, "unit_price": 29.99 }
  ],
  "coupon_code": "SAVE10",
  "currency": "USD",
  "shipping": {
    "address": "123 Main St, Springfield, IL 62701",
    "method": "standard"
  }
}
```

---

### What the Agent Produces

The agent must output a **test suite** — a list of test cases, where each test case contains:

- A short, human-readable **test name** describing the intent.
- The complete **request payload** to be submitted, as a valid JSON object.

No expected outcome is required. The evaluation is performed by running each test case against the live reference implementation and observing what actually happens.

**Example test case:**
```json
{
  "test_name": "Order with zero quantity item",
  "payload": {
    "user_id": "usr_4821",
    "items": [{ "product_id": "prod_991", "quantity": 0, "unit_price": 29.99 }],
    "currency": "USD",
    "shipping": { "address": "123 Main St, Springfield, IL 62701", "method": "standard" }
  }
}
```

---

## Evaluation Methodology

All 20 reference API implementations are deployed and running. Evaluation is fully automated: each test case in the agent's output is executed against the live API, and the responses are analysed to determine which planted bugs were triggered.

A bug is considered **detected** if at least one test case in the suite produces a response that deviates from the correct behaviour in a way that corresponds to the planted bug — for example, a 200 OK where a 400 should have been returned, or a silently incorrect computed value in the response body.

---

## Scoring

The final score combines three factors:

### 1. Bug Detection Score *(Primary — 70%)*

Measures how many of the planted bugs were successfully triggered.

```
Bug Detection Rate = bugs_found / total_bugs
```

This is the core metric of the benchmark. An agent that finds more bugs scores higher, regardless of how it gets there.

### 2. Coverage Score *(20%)*

Measures how well the test suite explores the API surface. This rewards agents that think systematically rather than getting lucky with a few tests. Coverage is assessed across three dimensions:

- **Parameter coverage** — what fraction of the request fields are exercised as the primary variable in at least one test.
- **Edge case coverage** — whether the suite probes boundaries (empty values, nulls, type mismatches, out-of-range values) rather than only valid inputs.
- **Input variation** — whether the suite explores diverse combinations rather than repeating near-identical payloads with minor changes.

### 3. Efficiency Score *(10%)*

Penalises unnecessarily large test suites.

```
Efficiency = bugs_found / number_of_tests
```

This encourages agents to produce minimal, high-signal, non-redundant tests. A suite that finds 6 bugs with 10 tests is more valuable than one that finds the same 6 bugs with 80 tests.

### Final Score

```
Final Score =
  0.7 × Bug Detection Rate
+ 0.2 × Coverage Score
+ 0.1 × Efficiency Score
```

The final benchmark score for an agent is the average Final Score across all 20 scenarios.

---

## Why This Benchmark Matters

APIEval-20 evaluates a capability that is largely unmeasured today:

- Understanding API behaviour from limited information
- Identifying edge cases without being told where to look
- Designing effective, targeted test strategies
- Uncovering hidden bugs across a range of complexity levels

This goes beyond simple code generation or factual reasoning. It measures something more practically valuable:

> **How well can an AI agent think like a QA engineer?**

Most existing benchmarks evaluate whether a model can produce syntactically correct output or answer a question accurately. APIEval-20 evaluates whether an agent can *do useful work* — work that directly maps to a real engineering task with measurable outcomes.

---

## Dataset Structure

The APIEval-20 dataset is hosted on Hugging Face and is structured as follows:

- `scenarios/` — 20 JSON files, one per scenario, each containing the request schema, sample payload, and metadata (domain, bug count by complexity tier).
- `reference_impls/` — 20 live reference server implementations. These are not publicly released to prevent contamination; evaluation is run through the hosted harness.
- `eval/` — the evaluation harness that accepts a model-generated test suite, runs it against the reference implementation, and returns the three score components.
- `leaderboard.json` — the current leaderboard snapshot, updated weekly.

All scenarios are versioned. Subsequent releases will carry a version suffix (e.g. `APIEval-20-v2`) to enable longitudinal comparison.

---

## Leaderboard

Head over to Hugging Face to check how various existing AI agents stack up against each other across the 20 scenarios. The leaderboard displays individual scenario scores alongside the composite benchmark score, making it easy to see which agents are best at comprehensive coverage versus which are most efficient at finding bugs with minimal tests.

**[View the leaderboard → huggingface.co/datasets/apieval-20](https://huggingface.co/datasets/apieval-20)**

---

## What Comes Next

APIEval-20 is the first entry in what we plan to be a growing family of API testing benchmarks. Coming soon:

- **APIEval-20-Response:** extends the benchmark to include response schema information alongside request payloads, measuring whether additional context improves bug-finding.
- **APIEval-Tool:** a companion benchmark evaluating existing automated API testing tools (Schemathesis, Dredd, RESTler, and others) on the same scenario set, enabling direct comparison between AI agent-generated and tool-generated test suites.
- **APIEval-50:** a larger scenario set covering 50 APIs with an expanded bug taxonomy, including concurrency bugs, state-dependent failures, and multi-step workflow errors.

Stay tuned — we will be releasing these additional benchmarks in the coming months. If you would like to contribute scenarios, suggest improvements, or report issues with the evaluation harness, please open an issue on the Hugging Face repository.

---

*APIEval-20 — Version 1.0 — 2026*
