# Council Rubric (Stage 3) — builder, reviewer, judge

The orchestrator (the session that runs `RUN.md`) is not on the council. It
dispatches, records, and stops. Everyone below is a subagent it dispatches.

## Roles (keep distinct)
`builder`  — does the work. Fresh context every iteration. At least one required.
`reviewer` — notes only. Improves quality but CANNOT declare a gate clean.
`judge`    — structured verdict. The only thing usable as a gate `verdict_source`.

Compiler-enforced: `verdict_policy: revise_until_clean` requires a
`verdict_source` that is a judge member or `human`; a builder may not appear on
a gate at all. A reviewer-only gate may use `fixed_passes` but cannot honestly
claim "clean".

## Choosing the builder subagent
Ask, and write the answer into the spec:
- **Which model?** `inherit` (same as the orchestrator) is the honest default.
  Name a cheaper model when the work is mechanical and fully specified; name a
  stronger one when the iteration involves design judgment or hard debugging.
- **How much effort / how long a leash?** A builder given a tight spec and one
  artifact needs less than one asked to explore.
- **What does its brief carry?** Goal, definition of done, the criteria it will
  be judged on, artifact paths, and the previous verdict's blocking issues —
  those only. The orchestrator's own commentary contaminates the next attempt.
- **Fresh context every iteration, always.** A builder that remembers its last
  three rejections starts defending them instead of fixing them.

## Judge selection
**Default: a fresh same-family subagent** (`kind: subagent`, `context: fresh`).
Fresh context is what a gate actually needs — the judge cannot see the builder's
reasoning, so it grades the artifact rather than the intention behind it. This
is free, fast, and stays inside the session.

**Optional: external / cross-family judge.** A different model family covers
same-family blind spots too, at the cost of money and a vendor boundary. Worth
it when a shared misreading would be expensive: public output, irreversible
actions, anything where a wrong "clean" is costly. Configure with
`judge: deepseek` (bundled adapter) or your own `invoke` argv.

Whichever you pick, remember the compensation principle from the verification
rubric: the weaker the judge's independence, the more criteria must be
programmatic.

## Writing a stable judge rubric
- Name the artifact and the exact criteria IDs being judged.
- Ask for blocking_issues, not general commentary.
- Require the JSON verdict shape (see verification rubric).
- Keep the wrapper short so the artifact dominates the judge's context.
- Include the 偏離情況 section of `implementation-notes.md` and instruct the
  judge to compare the delivery against `SPEC.yaml`: an unrecorded deviation is
  a blocking issue.

## Privacy — only when a judge is external
A same-family subagent sends nothing anywhere; there is no egress contract to
write. If and only if you add an external judge: name the destination, scope
what it receives (`sends`), apply the redaction globs, scrub secret patterns
from the artifact CONTENT (not just filenames), and require consent on the first
send. A local judge is flagged no-egress.
