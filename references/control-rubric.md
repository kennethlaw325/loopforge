# Control Rubric (Stage 4) — gates, caps, stop conditions, boundary

## Required caps (compiler rejects a spec missing any)
- `loop_control.max_iterations`
- `gates.*.max_revisions` — and `gates.*` is exactly three gates: `plan_gate`,
  `delivery_gate`, `final_gate`. It is a closed set. Do not design a fourth gate
  or rename one during the interview: the compiler rejects it at Emit, and a
  gate under any other name would be run and validated by nothing anyway. More
  stages of scrutiny go INSIDE these three, as extra criteria or extra members.
- `loop_control.no_progress.max_stalled_iterations`
- At least one budget cap: `wall_clock_min` / `usd` / `tokens`
- A stop condition describing SUCCESS.
- A stop condition describing no-progress / repeated failure.

Caps are enforced by reading files, not by remembering. The orchestrator opens
every iteration with `loopforge.py check <dir>`: exit 0 = go, non-zero = stop and
escalate. A cap the loop has to remember is a cap the loop will forget on
iteration 6.

## Gate design
- Plan gate runs before any delivery work is spent on a wrong plan.
- Delivery gate runs after each delivery artifact.
- Programmatic checks run BEFORE judge calls (cheap and deterministic first — a
  judge call spent on something a script already answered is wasted twice: once
  in money, once in the revision it triggers).
- **The final gate is human. Always.** Middle gates may be fully automated; the
  ship gate is not negotiable and the compiler rejects any other
  `verdict_source`. The failure it prevents is specific: the builder misreads
  the spec, a same-family judge misreads it the same way, the loop certifies
  itself clean, and nobody looks until the work is out the door.
- Other human checkpoints sit at high-leverage points: after plan approval, or
  before the first irreversible action.
- Resume at gate boundaries.

## The delivery contract (why a gate can refuse to even run)
A builder's delivery is only a delivery if `implementation-notes.md` was updated
with it. No update = nothing delivered: send it back, do not spend a gate on it.
The notes are the only record of what the builder decided that the spec never
said, and the judge needs 偏離情況 to grade deviations at all.

## Judge-call hygiene
- A judge CLI/adapter error is a bad call, never a loop-killing crash.
- A verdict carrying a `warning` (adapter error / mangled input / self-contradicting
  verdict / unparseable output) is a BAD JUDGE CALL, not a real verdict: it does
  NOT count against `max_revisions`, is logged separately, and NEVER dispatches a
  builder revision. Response = retry the judge once, then escalate to a human.
- 2+ bad judge calls at one gate -> human checkpoint, not more retries.
- Revision quota accounts by FAULT SOURCE. `max_revisions` counts EXECUTOR faults
  only. Human-checkpoint rework opens a NEW iteration and never burns gate quota.
  (In one recorded run, the human's own taste feedback consumed revisions 2/3 and
  3/3 — the quota meant for builder faults ran dry on rounds the builder never
  caused.)
- Judge and transport faults are free re-queries, bounded by a separate
  judge-fault cap (~3) that escalates to a human.

## No-progress detection
- Signature is NORMALIZED (lowercase + collapsed whitespace) so a judge
  rephrasing the same complaint still counts toward the stall window.
- `fixed_passes` max_revisions must be <= the no-progress window, else the gate
  appends a constant failure each round and stalls out before it can proceed.
  The compiler REJECTS that config.

## Orchestrator handover
An orchestrator that has read six revisions of the same artifact starts agreeing
with the builder it has been reading. Set `orchestrator_handover_every` (default
3) and hand the loop to a fresh session at that interval, or the moment verdicts
begin to repeat. All the state is in files precisely so the orchestrator is
replaceable: `SPEC.yaml`, `PLAN.md`, `RUN.md`, `loop-state.json`,
`implementation-notes.md` are a complete handover.

## Human checkpoint agenda
At every checkpoint, put in front of the person: every 開放式問題 entry, the
設計決策 that changed the shape of the deliverable, and any 偏離情況 the judge
let through. Whatever they rule on is written back into `SPEC.yaml` and
recompiled — a question answered once never gets re-litigated, and the next
builder inherits the answer as a requirement.

## Execution boundary
- Name where the loop may modify files: current_workspace / branch / worktree /
  sandbox.
- Identify side-effecting actions: pushes, PR comments, posts, deploys, deletes,
  DB writes, external sends. Decide at DESIGN time which are `execute` and which
  are `report_only` — never per-iteration model judgment.
- The orchestrator is a session: the loop pauses when the session ends. If the
  loop needs to survive that (scheduled wakeups, restart-safe retries), set
  `execution.mode: external_runner` and name your runner of choice. Durability
  changes who drives the loop, never who signs it off.

## Anti-patterns (block)
- No max iteration count. A judge gate with no judge. Budget in prose only.
- No no-progress detector. Human signoff required but no checkpoint.
- Stop conditions that require subjective self-satisfaction.
- A final gate that anything other than a human can pass.
