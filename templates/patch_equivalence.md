You are comparing two patches for behavioral equivalence. Apply the 5-phase semi-formal equivalence analysis below. Use tools extensively to gather evidence before reaching conclusions.

---

## PATCH A

{patch_a}

---

## PATCH B

{patch_b}

---

## PHASE 1: PATCH COMPREHENSION — Premises

For each patch, establish **premises** about what it does:

```
PATCH A:
  PREMISE A1: [file:line] <factual statement about what patch A changes, verified by reading>
  PREMISE A2: [file:line] <another fact about patch A>

PATCH B:
  PREMISE B1: [file:line] <factual statement about what patch B changes, verified by reading>
  PREMISE B2: [file:line] <another fact about patch B>
```

**Required actions:**
- `read_file` each changed file to understand the full context of both patches
- Identify what each patch adds, removes, and modifies
- Note the intent/purpose of each patch

## PHASE 2: SEMANTIC MAPPING

Map corresponding changes between the two patches:

```
MAPPING M1: Patch A [file:line] ↔ Patch B [file:line]
  A does: <description>
  B does: <description>
  Semantic match: YES | PARTIAL | NO

MAPPING M2: ...

UNMATCHED in A: <changes in A with no counterpart in B>
UNMATCHED in B: <changes in B with no counterpart in A>
```

**Required actions:**
- Identify which changes in A correspond to changes in B
- Note any changes that appear in one patch but not the other
- `grep_search` for affected functions to understand their full signatures and contracts

## PHASE 3: BEHAVIORAL ANALYSIS

For each mapping pair, trace execution to check if observable behavior matches:

```
MAPPING M1 — Behavioral Analysis:
  Input space: <what inputs reach this code>
  Patch A behavior: <output/side-effect for representative inputs>
  Patch B behavior: <output/side-effect for same inputs>
  Equivalent: YES | NO | CONDITIONAL
  If conditional: <under what conditions they differ>
```

**Required actions:**
- `read_file` to trace how the changed code is called
- `grep_search` for all callers of modified functions
- Consider type coercion, null handling, error paths, and ordering differences
- For each mapping, reason about whether the same inputs produce the same outputs

## PHASE 4: BOUNDARY TESTING

Construct edge-case inputs and reason about behavior:

```
EDGE CASE E1: <description of edge case>
  Input: <specific input>
  Patch A result: <expected behavior>
  Patch B result: <expected behavior>
  Difference: YES | NO

EDGE CASE E2: ...
```

**Edge cases to consider:**
- Null/undefined/None inputs
- Empty strings, empty arrays, empty objects
- Boundary values (0, -1, MAX_INT)
- Unicode / special characters
- Concurrent access (if applicable)
- Error/exception paths

**Required actions:**
- For each edge case, trace through both patches mentally
- `read_file` on relevant code if edge case behavior is unclear
- Focus on cases where the patches take different code paths

## PHASE 5: VERDICT — Conclusions

Output the equivalence verdict as JSON:

```json
{{
  "verdict": "equivalent | not_equivalent | uncertain",
  "confidence": "high | medium | low",
  "differences": [
    {{
      "description": "<what differs>",
      "input_that_differs": "<example input where behavior diverges>",
      "patch_a_behavior": "<what patch A does>",
      "patch_b_behavior": "<what patch B does>",
      "severity": "breaking | minor | cosmetic"
    }}
  ],
  "reasoning_log": "<brief narrative of the equivalence analysis>"
}}
```

If the patches are equivalent, `differences` should be empty.
If uncertain, explain what additional information would resolve the uncertainty.

**IMPORTANT:** Your response must end with the JSON block above (after ```json and before ```). All reasoning phases should appear before the JSON.
