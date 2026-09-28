# Verification Rubric (Stage 2) — the most important stage

Turn definition_of_done into TYPED, checkable criteria. Order of preference:
programmatic > judge > human.

## Taxonomy
`programmatic` — an argv command returns pass/fail. Deterministic, free, repeatable.
  Needs `check` (argv array) + `expect` (exit_zero | exit_nonzero | stdout_contains).
  Use for: counts, schema, required headings, build, lint, snapshot, URL liveness.
`judge` — a model scores a `rubric` and returns a structured verdict.
  Use ONLY for semantic quality code cannot cheaply check. Rubric must be
  specific enough that a DIFFERENT context applies it consistently.
`human` — a person signs off via a `prompt`.
  Use for taste, business judgment, private knowledge, legal risk.

## The compensation principle (read this before writing any judge criterion)

**The less independent the judge, the more of the verification must be
programmatic.** A judge is only as good as its distance from the builder, and
that distance comes in tiers:

| judge | independence | what it buys you |
|---|---|---|
| same session / same context | none | it agrees with what it already wrote |
| fresh same-family subagent (default) | no context contamination | catches drift, not shared blind spots |
| different model family (optional) | no context AND no family blind spot | costs money, crosses a vendor boundary |

The default judge is a fresh same-family subagent. It cannot see the builder's
reasoning, but it can share the builder's blind spots — the two may misread the
same ambiguous spec line the same way. **Compensate deterministically: anything
that can be an assert, a test, a schema check or a grep MUST be one. The judge
only rules on what genuinely cannot be measured.**

Practical test for every judge criterion you are about to write: "could a
20-line script decide this?" If yes, it is not a judge criterion. Counts,
presence, format, ordering, freshness, liveness, referential integrity, "no
placeholder text" — all of these are scripts, not judgments.

The residue that legitimately stays with the judge: is the argument coherent,
is the tone right, is the step actually followable by someone who does not
already know the answer, is this the thing that was asked for.

## Strict-mode rules
- Convert as much as possible to `programmatic`. Push back on every judge/human
  criterion a script could check instead.
- Every `context_source` that has a fixture / demo / sample mode MUST get a
  step-0 programmatic freshness assert: real-mode flag checked + max data age.
  A silent fixture no-op looks exactly like success — in one recorded run a
  fixture flag served week-old data through two passing gates, and only the
  human checkpoint caught it.
- LOUD WARNING if every criterion is judge/human ("all-vibe loop"): demand at
  least one deterministic check unless the user explicitly accepts the risk.
- Each criterion checks ONE thing and says what failure means.
- Judge rubrics must be observable against the artifact the judge receives — no
  hidden context.
- Never let the builder grade its own work; the judge is a separate, fresh
  context, and the compiler rejects a builder sitting on a gate.

## Anti-patterns (block)
- Judge/human criteria where a test or schema check exists.
- "No errors thrown" as the only success criterion.
- "High quality" / "comprehensive" with no named dimensions.
- Programmatic `check` written as a shell string instead of an argv array.

## Structured judge verdict (the contract every judge returns)
```json
{ "verdict": "pass" | "revise", "blocking_issues": ["[criterion] ..."],
  "confidence": 0.0, "notes": "...",
  "warning": "optional — adapter_error | mojibake_input | verdict_inconsistent | unparseable_judge_output",
  "usage": { "prompt_tokens": 0, "completion_tokens": 0 } }
```
- Each blocking issue starts with `[the criterion it violates]`; an issue that
  cannot cite a criterion is advisory. (A judge that complained about something
  no criterion required once burned an entire gate's revision quota.)
- **The judge also checks the spec against the delivery.** It reads the
  偏離情況 section of `implementation-notes.md`: a deviation from `SPEC.yaml`
  that is NOT recorded there is a blocking issue in itself; a recorded deviation
  is judged on whether its stated reason holds.
- Unparseable / errored / self-inconsistent output carries a `warning` and is a
  BAD JUDGE CALL, not a real verdict — it never aborts the loop and MUST NOT
  trigger a builder revision (see control rubric).
- **Multi-clause criteria report coverage, not only a verdict.** Add optional
  `"clauses_checked": [{"clause": "<id>", "status": "pass" or "fail"}]`; the
  next fresh judge receives the previous list as a coverage map (not a
  verdict to trust) plus which files changed since, and examines unchecked
  clauses first. 〔three fresh judges each found a different pre-existing gap
  the earlier ones had marked pass; the revision quota ran out on
  one-sentence-at-a-time discovery〕
