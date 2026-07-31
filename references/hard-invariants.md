# Hard Invariants — the consolidated 錯題簿 registry

Compiled from four production agent harnesses: a staged design loop, an
unattended overnight agent, a long-running task scheduler, and a multi-stage
content pipeline. Every entry below is a bug that actually shipped somewhere and
cost real time. The bracketed 〔...〕 note is what it looked like when it bit.

**How to use (Stages 2 and 4):** walk the applicable sections. Every invariant
either becomes a concrete check / spec rule in `SPEC.yaml`, or gets an entry in
its `invariants:` block with `status: waived` and a reason. Silence is not a
waiver. Entries marked ✅ are already enforced by the bundled adapter/compiler —
rely on them, don't re-emit.

## J — Judge & verdict I/O

- **J1 · Byte-transparent judge transport.** ✅ The bundled adapter reads stdin
  as bytes + UTF-8 and refuses mojibake (`????` runs → warning=mojibake_input).
  Spec side: pin an external judge's invoke as a byte-transparent pipe; never a
  shell that re-encodes. 〔a judge graded all-`??` text and returned a confident
  verdict on garbage〕
- **J2 · Verdict is a typed record.** ✅ adapter: `revise` with zero actionable
  blocking issues → one auto re-ask, then warning=verdict_inconsistent.
  〔verdict field said revise, body said everything was acceptable, confidence 1.0〕
- **J3 · Issues cite the rubric.** ✅ adapter system prompt: each blocking issue
  starts with `[the criterion it violates]`; can't cite = advisory in notes.
  〔a plan judge complained about an ordering the rubric itself mandated and
  burned the whole revision quota〕
- **J4 · Fault-source revision accounting.** `max_revisions` counts EXECUTOR
  faults only. Judge/transport faults (any `warning` verdict) = free re-query,
  bounded by a separate judge_fault_cap (~3) that escalates to human.
  Human-checkpoint rework opens a NEW iteration — it never burns gate quota.
  State records rounds as `{round, fault_source: executor|judge|transport|human,
  consumed}`. 〔the human's own feedback exhausted the delivery quota 3/3〕
- **J5 · Single-line JSON result contract, enforced on BOTH sides.** Every
  executor exit (success AND each typed failure) emits exactly one non-empty
  JSON line; the consumer parses scan-from-end, ok-anchored; free-text argv
  values passed as `--flag=value` (a leading dash is not an argparse
  SystemExit). 〔indent=2 output vs a single-line parser: successful runs were
  reported as failures〕
- **J6 · Parse failure is a typed terminal status.** Executor output that fails
  schema validation = `parse_error` (never success); quarantine raw stdout;
  counts toward the consecutive-failure alarm. 〔a fallback let unparsed runs
  flow downstream as success〕
- **J7 · The verify harness is itself untrusted until smoke-tested.** "Verify
  green" only after executing it and parsing `N pass / 0 fail` from real
  stdout. A VCS command's exit code is forbidden as a pass/fail signal (hooks
  pollute it). 〔3 false FAILs in one iteration, all from a post-checkout hook〕

## G — Gate & plan design

- **G1 · A documented risk is not mitigation.** Every plan Risks row carries
  `mitigating_check_id` (resolving to a real criterion) or
  `accepted_by_human: <name+date>`; a bare risk row is a mechanical blocking
  issue. 〔week-stale input data was written in Risks, passed the plan gate, and
  detonated at the human checkpoint〕
- **G2 · Spec-to-plan traceability.** Every spec MUST / integration-surface
  line maps to a plan task id; a plan task marked "optional" that maps to a
  MUST-line fails. Criteria coverage ≠ spec coverage.
  〔a loop judged itself COMPLETE; the human caught that the spec said unified
  entry point and the plan had quietly shipped a standalone one〕
- **G3 · Per-phase criteria applicability.** Criteria carry an
  `applies_when`/`phase` field; the gate computes the applicable subset;
  "N/A" is a computed status, never operator improvisation.
  〔a flat 8-criteria list led the operator to improvise "these are N/A here"〕
- **G4 · Human checkpoints carry a timeout policy.** `{timeout_min,
  on_timeout: wait | proxy_if_reversible | stop}`; proxy allowed only when
  isolation == branch AND zero forbidden side effects executed; proxy approval
  written as a typed record. 〔a 60-second-AFK proxy approval was improvised —
  safe only by luck of branch isolation〕
- **G5 · A gate may not write its own threshold.** Config/threshold hash
  asserted unchanged between iterations; changes require a human commit.
  〔a budget check auto-raised its own cap every time spend hit 90%〕
- **G6 · Declared gates must be grep-provably wired.** Every cap/threshold
  config key must have an enforcement call site; README-only gates fail
  compile. 〔`max_cost_per_run` lived in the config and the README and was read
  by no code〕
- **G7 · Truth-recompute sibling criterion.** Any criterion validating a
  generated data artifact gets a `<id>-truth` sibling that re-derives the
  numbers from raw sources, not from the artifact's producer — fake-green data
  becomes mechanically impossible.
- **G8 · The verifier layer is itself verified.** Race/lock fixes require a
  barrier-synced real-writer test plus a mutation run (revert fix → test red →
  restore → green), logged in the PR; concurrency tests may not monkeypatch
  claim primitives; cross-repo reviewers assert local HEAD == origin before
  filing blockers. 〔a reverted fix left 306 tests green = the pin was fake; a
  stale checkout produced a false blocker〕
- **G9 · Irreversible actions gated by a static policy table.**
  `{action_class → execute | report_only}` decided at design time;
  publish / merge / push / file-move / prod-config default to report_only with a
  ranked report as the typed output. Never per-iteration model judgment.
- **G10 · Builder invocation pinned and asserted.** State records
  `builder_invoke_actual` per dispatch; a mismatch against the spec's council
  entry is a typed deviation `{spec, actual, justification, approved_by}` that
  blocks iteration 1. 〔the spec pinned a specific model, the runner substituted
  a different dispatch path and self-certified it as "the same tier"〕

## S — State integrity

- **S1 · Three atomicity primitives, never conflated.** Atomic overwrite =
  unique mkstemp + fsync + rename (a FIXED .tmp name is itself a race);
  create-if-absent = claim-WITH-content in one kernel op (mkstemp full write +
  os.link — an O_EXCL empty claim exposes a publishable 0-byte item);
  rename/os.replace is NEVER a claim (two renames of one src both succeed).
  Cleanup OSError on the success path is suppressed so it can't mask success
  as failure. 〔file-lock race / 0-byte publishes 34⁄40 / dual-land 14⁄80 /
  an antivirus unlink window → permanently duplicate-stuck items〕
- **S2 · Cross-process lock with steal-and-rearbitrate.** Shared JSON state =
  read-merge-write under a lockfile carrying {pid,ts}; a stale holder gets a
  dead-PID liveness probe → unlink + O_EXCL re-create; NEVER
  "timeout-then-proceed-lockless". On Windows `os.kill(pid, 0)` KILLS — probe
  via OpenProcess. 〔a leaked lockfile silently disabled the mutex; 32⁄40
  dual-landed〕
- **S3 · Corrupt state quarantines, never resets.** Decode failure → copy to
  `.corrupt-<ts>` + alert; a silent `state = {}` wipes every agent's last_run.
- **S4 · Every at-most-once marker has a paired CLEAR.** One clearing call
  site per terminal edge of the item state machine, proven by a lifecycle
  test (post → gate → legitimately re-enter → FRESH must fire); terminal
  probes check the full cluster key set, not a representative.
  〔zombie drafts; killed items resurrecting〕
- **S5 · Ledger keys are creation-frozen.** Key outcome/ledger records by
  path.stem (fixed at draft time), never recomputed from mutable content
  (slug(title), hash(source_url)) — human edits during review make recomputed
  keys drift. 〔an edit silently downgraded a record's identity and double-logged
  the outcome〕
- **S6 · Re-entrancy guard before the first await.** Interactive handlers set
  their busy flag in the first synchronous section, reset in `finally`;
  long-run mutual exclusion via a non-blocking `lock.locked()` check.
  〔a double-click dual-moved files during a subprocess run〕
- **S7 · Append-only tracker read at step 0 of every iteration.** The loop
  never trusts its own context memory across wakeups; an iteration may not
  end without appending. (`loop-state.json` is this tracker — it is why a new
  orchestrator session can take over mid-loop.)
- **S8 · User WIP is sacred.** Autonomous repo work = stash-with-untracked +
  branch off a clean base + byte-verified restore (porcelain snapshot identical
  afterwards).

## P — Process, timeout, quota

- **P1 · Tree-kill wrapper for every executor spawn.** `subprocess.run(timeout=)`
  is fake for launcher CLIs (grandchildren hold the pipe → hang); use Popen +
  a tree kill (`taskkill /T /F /PID`). Orphan cleanup only via a persisted
  own-PID registry with an image-name PID-reuse guard — NEVER `/IM`-wide kills.
  〔a startup `/IM` kill took out the human's own live session〕
- **P2 · Timeout ordering is computed, not guessed.** Outer timeout >
  inner worst case (retries × per-call timeout + backoff sum) + startup
  margin, pinned by a guard test that computes from the actual constants;
  timeouts ≥ 1.5× rolling-mean runtime. 〔a 360s outer timeout killed a 545s
  worst-case inner on attempt 3〕
- **P3 · Per-item exception boundary; the pointer always advances.** One item
  crashing (or 429ing) may not kill the loop; typed error record + next
  iteration fires. 〔a quota 429 killed a scheduler for 40 hours〕
- **P4 · Claim-then-ack work items.** Rename the trigger to `.processing/<id>`
  before executing; delete on success; dead-letter + alert on failure;
  watchdog asserts no `.processing` older than the timeout. Delete-before-execute
  = silent stall on crash.
- **P5 · Surface produced work on EVERY exit path.** Success, timeout,
  exception, rc≠0 all route through one shared surfacing function (test per
  path); user-facing error text truncated to the transport cap; summaries
  report only counters measured this run. 〔a 20-minute run timed out at the
  last step and 8 real deliverables sat invisible — the human saw "nothing came
  out"〕
- **P6 · Cost accounting may not default to 0.** A missing cost field =
  `cost_unknown` event, alert after 3 consecutive; a $0 default makes the
  budget gate permanently blind. 〔callers hardcoded `cost_usd: 0.0` and a
  four-figure overrun ran invisible〕
- **P7 · Pin the context surface; alarm on identical repeats.** Spawns carry
  isolation flags; a pre-spawn assert checks prompt size < context limit −
  margin (typed prompt_too_long); 3 consecutive identical failures of one agent
  = alert. 〔an inherited context surface grew to 212K and every cycle failed
  silently for days〕

## F — Freshness & no-op traps

- **F1 · Step-0 freshness assert per external input pool.**
  `max(published_date) >= now − freshness_budget` else block the phase; any
  dual-mode (fixture/live) tool must echo its effective mode to stdout and
  the gate asserts it equals the required mode.
  〔a fixture-mode env var made a source a silent no-op: week-old data passed
  two green gates until the human asked why nothing was recent〕
- **F2 · Process-alive ≠ healthy.** Watchdog asserts output freshness
  (heartbeat mtime < max age) AND process identity (PID alive AND command
  line matches); stale pidfiles deleted on detection; exactly one recovery
  authority per component ({restart | alert_only}) — auto-restarting a
  component that has native retry races it.
- **F3 · Watchdog coverage is asserted, not assumed.** A machine-readable
  live-component list is diffed against the set actually checked each run;
  architecture cutover PRs must update the list in the same diff.
  〔after a cutover the new pipeline had zero freshness checks — the exact
  silent-outage class the watchdog was built for〕
- **F4 · Deferred gates carry liveness.** Every watch-gate has
  `{precondition_check_cmd, hard_stop_date}`; a sweep flags UNREACHABLE when
  the referenced external object can no longer transition. 〔a gate keyed on a
  PR that auto-closed was silently dead〕

## E — Encoding & environment

- **E1 · UTF-8 pinned at every process boundary.** `PYTHONUTF8=1` in every
  spawned env; `encoding="utf-8", errors="replace"` on every subprocess text
  read (including process-listing tools); harness stdio reconfigured; REST
  bodies pre-encoded to UTF-8 bytes; one CJK+emoji canary round-trip test per
  channel (it doubles as the standing refutation of the whole bug class).
  〔a judge pipe, a cleanup-path decode crash, and a chat notifier, all the same
  bug on a non-UTF-8 default codepage〕
- **E2 · Dual-path declarations on Windows.** Any path consumed by both
  Python and a POSIX shell declares PATH_WIN (`C:/...`) and PATH_UNIX
  (`/c/...`) variants. 〔a verify script false-failed on the path form alone〕

## A — Autonomy & escalation

- **A1 · Closeout is licensed, budgeted, and terminal.** Reserve an explicit
  closeout window; past the value plateau only closeout iterations are
  permitted; stopping (omitting the next wakeup) is a positive act the spec
  licenses. 〔post-plateau iterations dilute a clean final state〕
- **A2 · Negative space is mandatory.** The final briefing carries a
  `not_done` table — one row per never-auto category with instance counts and
  artifact paths — so unattended-agent accountability is auditable rather
  than inferred from absence.
- **A3 · Activation gates key on state, not phrases.** Trigger = (eligible
  pending tasks AND signal class), emitting a typed offer before ending the
  turn; exact-phrase matching fails closed. 〔a start signal without the magic
  words left a proven harness idle: 11 tasks, 0 progress〕
