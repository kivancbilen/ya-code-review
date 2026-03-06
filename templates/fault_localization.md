You are investigating a bug. Apply the 5-phase semi-formal fault localization process below. Use tools extensively to gather evidence before reaching conclusions.

---

## BUG DESCRIPTION

{bug_description}

## RECENT CHANGES (DIFF)

{diff}

---

## PHASE 1: SYMPTOM ANALYSIS — Premises

Establish **premises** about the bug from the description, error messages, and observable behavior:

```
PREMISE S1: <factual statement about the reported symptom>
PREMISE S2: <factual statement about error messages or stack traces>
PREMISE S3: <factual statement about when/where the bug occurs>
...
```

**Required actions:**
- Parse the bug description for concrete symptoms, error messages, and reproduction steps
- `grep_search` for error messages or exception types mentioned
- `read_file` on any files mentioned in stack traces or the bug description
- Identify the entry point(s) where the bug manifests

## PHASE 2: HYPOTHESIS FORMATION

Generate 3-5 **hypotheses** about the root cause, each with a testable prediction:

```
HYPOTHESIS H1: <what might be causing the bug>
  Based on: S1, S2
  Prediction: If true, we should find <specific observable evidence> at <location>
  Test: <specific tool actions to verify/refute>

HYPOTHESIS H2: ...
```

**Required actions:**
- For each hypothesis, identify the specific file(s) and function(s) to examine
- Consider: recent changes, edge cases, race conditions, incorrect assumptions, missing validation
- Rank hypotheses by prior probability based on symptom analysis

## PHASE 3: EXECUTION TRACING — Evidence Gathering

For each hypothesis, systematically gather evidence:

```
HYPOTHESIS H1 — Investigation:
  Action: read_file(<file>, lines <start>-<end>)
  Observation: <what the code actually does>
  Action: grep_search(<pattern>)
  Observation: <callers/references found>
  Evidence: SUPPORTS | CONTRADICTS | NEUTRAL
```

**Required actions:**
- `read_file` on the suspected code for each hypothesis
- `grep_search` for callers and data flow into the suspected code
- `git_log` or `git_blame` to check recent changes to suspected areas
- Trace execution paths that lead to the symptom
- If the diff is provided, check whether recent changes introduced the bug

## PHASE 4: HYPOTHESIS EVALUATION

Score each hypothesis based on evidence gathered:

```
HYPOTHESIS H1:
  Evidence for: <list of supporting observations>
  Evidence against: <list of contradicting observations>
  Verdict: CONFIRMED | LIKELY | POSSIBLE | UNLIKELY | REFUTED
  Confidence: high | medium | low
```

**Required actions:**
- Weigh evidence for and against each hypothesis
- Check if multiple hypotheses could be interacting
- Identify any hypotheses that need more evidence (and gather it)

## PHASE 5: FAULT RANKING — Conclusions

Output a ranked list of suspect locations as JSON:

```json
{{
  "suspects": [
    {{
      "file": "<file path>",
      "line_start": <number>,
      "line_end": <number>,
      "suspicion_score": <0.0-1.0>,
      "hypothesis": "<which hypothesis this supports>",
      "evidence": ["S1", "H2", "<specific observation>"]
    }}
  ],
  "reasoning_log": "<brief narrative of the fault localization process>"
}}
```

Sort suspects by `suspicion_score` descending. Include all locations with score > 0.3.

**IMPORTANT:** Your response must end with the JSON block above (after ```json and before ```). All reasoning phases should appear before the JSON.
