You are reviewing the following code changes. Apply the 5-phase semi-formal reasoning process below. Use tools extensively to gather evidence before reaching conclusions.

---

## DIFF UNDER REVIEW

{diff}

{known_patterns}

---

## PHASE 1: CHANGE COMPREHENSION — Premises

For each changed file/function, establish **premises** (facts verified by reading the code):

```
PREMISE P1: [file:line] <factual statement about what the code does, verified by read_file>
PREMISE P2: [file:line] <another fact>
...
```

**Required actions:**
- `read_file` each changed file to understand full context (not just the diff)
- For each changed function, read the surrounding class/module
- Identify the purpose of each change

## PHASE 2: EXECUTION PATH TRACING

Build a **function trace table** for each non-trivial change:

```
TRACE T1: caller_a() → changed_function() → callee_b() → callee_c()
  Data flow: param X is [type], transforms to [type] at [file:line]
TRACE T2: ...
```

**Required actions:**
- `grep_search` for all callers of each changed function
- `read_file` on key callers to understand how they use the changed code
- Trace data flow through at least 2 levels of call depth
- Note any type transformations, null checks, or error handling in the chain

## PHASE 3: DIVERGENCE ANALYSIS — Claims

Identify potential issues as **claims**, each referencing premises and traces:

```
CLAIM C1: [severity: critical|high|medium|low] [confidence: high|medium|low]
  Statement: <what the issue is>
  Based on: P1, P2, T1
  Evidence: <specific code references from tool outputs>
  Impact: <what could go wrong>
```

**Categories to check:**
- Correctness: logic errors, off-by-one, null/undefined handling, type mismatches
- Concurrency: race conditions, deadlocks, shared state
- Performance: N+1 queries, unbounded loops, missing pagination
- Security: injection, auth bypass, data exposure
- API contract: breaking changes, missing validation, inconsistent error handling
- Edge cases: empty inputs, boundary values, error paths

## PHASE 4: ALTERNATIVE HYPOTHESIS CHECK — Falsification

For each claim from Phase 3, actively try to **disprove** it:

```
CLAIM C1 — Falsification:
  Test coverage: <grep for tests covering this path>
  Defensive code: <any guards/checks already in place?>
  Pattern precedent: <is this pattern used successfully elsewhere?>
  Verdict: SUSTAINED | WEAKENED | REFUTED
  Updated confidence: high|medium|low
```

**Required actions:**
- `grep_search` for test files covering the changed code
- `read_file` on relevant tests to check coverage
- `grep_search` for similar patterns elsewhere in the codebase
- Check if the concern is already mitigated

## PHASE 5: FINDINGS — Conclusions

Only report claims that **survived** Phase 4 (SUSTAINED or WEAKENED, not REFUTED).

For each surviving finding, produce:

```json
{{
  "findings": [
    {{
      "id": "F1",
      "severity": "critical|high|medium|low",
      "confidence": "high|medium|low",
      "title": "<short description>",
      "file": "<file path>",
      "line_start": <number>,
      "line_end": <number>,
      "description": "<detailed explanation>",
      "evidence_chain": ["P1", "T2", "C1"],
      "references": [
        {{
          "file": "<file path>",
          "line_start": <number>,
          "line_end": <number>,
          "snippet": "<the actual code lines from the diff or file that demonstrate the issue — copy verbatim, 1-15 lines>",
          "label": "<brief label: e.g. 'Falsy check drops zero', 'Missing guard', 'Caller passes null'>"
        }}
      ],
      "suggestion": "<how to fix>",
      "category": "<correctness|performance|security|style|maintainability>"
    }}
  ],
  "summary": {{
    "total_files_reviewed": <number>,
    "total_findings": <number>,
    "critical": <count>,
    "high": <count>,
    "medium": <count>,
    "low": <count>,
    "premises_established": <count>,
    "traces_performed": <count>,
    "claims_investigated": <count>,
    "claims_refuted": <count>
  }},
  "reasoning_log": "<brief narrative of the semi-formal reasoning process>"
}}
```

If no issues survive the falsification phase, report an empty findings list and explain why the changes look correct.

**IMPORTANT:** Your response must end with the JSON block above (after ```json and before ```). All reasoning phases should appear before the JSON.
