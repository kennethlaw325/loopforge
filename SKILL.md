---
name: loopforge
description: >
  Design a well-formed agent loop through a staged interview — sharp goal, typed verification, builder/judge subagents, gates and caps — then EMIT a spec (SPEC.yaml + PLAN.md + RUN.md) that this session executes as the loop's orchestrator. Design-only: LoopForge never starts the loop; a human does. Use when the user wants to design, scaffold, or tighten an agent loop, iterative workflow, self-review / LLM-as-judge loop, reviewer/judge gate, or build-check-revise loop.
disable-model-invocation: true
argument-hint: "[target-dir] [--fast]"
allowed-tools: Write Bash(py -3 *) Bash(python3 *)
---

# LoopForge

A loop DESIGN coach. It interviews you through six stages, critiques each answer
against a rubric, and emits a spec plus an orchestrator playbook. It does not
run the loop and it does not start it — after emitting, a human says go.

**Python:** `py -3` on Windows, `python3` on macOS/Linux. Every command below
takes either.

## Modes
- **Strict (default).** Every stage MUST be critiqued and tightened before the
  next. A weak goal blocks progress. This is the point of the skill.
- **Fast (`--fast`).** Accept a stage in one pass when the answer is already
  strong; push back only when a stage is weak. For experienced runs.

## The shape of the loop being designed

The session that later reads `RUN.md` is the **orchestrator**. Each iteration it:

1. runs `loopforge.py check` — a file read that says whether a cap allows another
   iteration;
2. dispatches a **fresh builder subagent** to do the work;
3. runs the programmatic criteria itself;
4. dispatches a **fresh judge subagent** for what a script cannot measure;
5. appends the verdict to `loop-state.json` and regenerates `loop.html`.

The orchestrator never builds and never judges. Holding the spec and the verdict
record is the entire job — the moment it starts building, the independence the
gates depend on is gone.

**"Subagent" here means whatever your runtime uses to get a clean context:** a
subagent, a spawned session, or a separate agent process. The requirement is
that the builder and the judge each start without the other's reasoning in
scope — not any particular runtime feature. Likewise `${CLAUDE_SKILL_DIR}` below
is just this skill's own directory; substitute your runtime's equivalent.

## Workflow

1. Resolve target from the argument (default `./loop`). Strip a leading
   `--fast` token first (detect it as the fast-mode flag, not part of the
   target). What remains, if anything: if it has no `/` or `\` and is not an
   existing path, treat it as a brief description, not a target dir — keep
   the default `./loop` target (or ask once if the intent is ambiguous) and
   write the brief verbatim into `SPEC.yaml`'s `meta.description`. Otherwise
   treat it as the target dir. If the resolved target already has a
   `SPEC.yaml`, treat as edit/resume: after each edit to a concept that has
   an id (a criterion id, a gate name, a council member id), grep the pack
   for that id before re-emitting — a rename or scope change can leave a
   stale reference in `PLAN.md` / `RUN.md` prose that the compiler does not
   catch (obs #306). ⚠️ this relies on memory, no enforcement point yet — a
   4th recurrence adds a compile-time cross-check instead of more reminder
   text.
2. Interview in SIX stages. Load the matching rubric ONLY when entering it:
   - Goal -> `${CLAUDE_SKILL_DIR}/references/goal-rubric.md`
   - Verification -> `${CLAUDE_SKILL_DIR}/references/verification-rubric.md`
   - Council -> `${CLAUDE_SKILL_DIR}/references/council-rubric.md`
   - Gates/Control -> `${CLAUDE_SKILL_DIR}/references/control-rubric.md`
   At Verification and Gates/Control, ALSO load
   `${CLAUDE_SKILL_DIR}/references/hard-invariants.md` (the consolidated
   錯題簿) and walk the applicable sections: every applicable invariant either
   becomes a check/rule in `SPEC.yaml` or gets a waiver line with a reason in
   the spec's `invariants:` block. Silence is not a waiver.
3. At each stage in strict mode: restate the user's input, critique it against
   the rubric with CONCRETE alternatives (use their domain's examples, not vague
   warnings), and then commit to ONE recommended answer, written in their
   vocabulary. A critique that stops at options hands the work back; a
   recommendation gives them something to confirm, adjust, or overrule. Get the
   tightened answer, THEN advance. Do not batch stages.
   - **Look facts up yourself.** Anything the environment can answer — which
     files exist, what a script already checks, what a context source actually
     contains — you read with your own tools and quote back. Only decisions go
     to the user; never ask them for something you could have looked up.
   - **Exit condition:** a stage counts as tightened when a fresh builder
     subagent could act on the answer without asking a single question. That,
     not "sounds good", is what lets you advance.
   - **Invariant codes (J1-J7, G1-G10 from `hard-invariants.md`) are write-side
     vocabulary** — they belong in `SPEC.yaml`'s `invariants:` block and other
     emit files, never in conversation. When a critique rests on one, say the
     consequence in the user's own domain terms ("the exam has to be taken
     once, not retried until it passes" — not "J7"). A critique that leaks a
     code name has zero information loss to fix: say it plainly instead.
   - When one stage holds several independent decisions (Gates & Control carries
     four separate caps), number them and put the whole round up at once, each
     with its own recommended answer. That is batching WITHIN a stage — stages
     themselves still never merge, and a weak answer still blocks on the spot.
4. Keep reviewer and judge roles distinct. `revise_until_clean` must name a judge
   member or `human` as `verdict_source` — never a reviewer.
5. Default judge = a **fresh same-family subagent** (`kind: subagent`,
   `context: fresh`). Fresh context is what the gate needs; a different vendor is
   an option, not the default. Offer the external judge only when the delivery is
   high-stakes enough to be worth the cost and the egress.
6. Require all caps: `max_iterations`, per-gate `max_revisions`,
   `no_progress.max_stalled_iterations`, and a budget cap. The compiler rejects a
   spec that is missing any of them.
7. The LAST gate's `verdict_source` must be `human`. Middle gates may be as
   automated as you like; the ship gate is not negotiable and the compiler
   enforces it.
8. Show the ASCII flow preview (Stage 5) and get confirmation before emitting.
9. Emit into the target: write `SPEC.yaml` (start from
   `${CLAUDE_SKILL_DIR}/templates/SPEC.yaml`) and
   `implementation-notes.md` (from `${CLAUDE_SKILL_DIR}/templates/`), then compile:
   `py -3 ${CLAUDE_SKILL_DIR}/scripts/loopforge.py compile <target>/SPEC.yaml`
   That writes `loop.resolved.json`, `PLAN.md` and `RUN.md`. Then render the
   empty dashboard so the user can see the loop before it runs:
   `py -3 ${CLAUDE_SKILL_DIR}/scripts/loopforge.py render <target>`
10. Show the preview and STOP. Tell the user the loop is designed, not started;
    iteration 1 begins only when they say go, and from then on the session
    follows `RUN.md` as orchestrator. LoopForge's job ends here.

## Six stages
1. **Goal** — outcome artifact, scope, context sources, definition_of_done.
2. **Verification** — typed criteria; push to `programmatic` first; warn on all-vibe.
3. **Council** — builder subagent (which model, what effort), reviewer (notes)
   vs judge (verdict); default judge = fresh same-family subagent; scope small.
4. **Gates & control** — plan / delivery / final gates, revision / iteration /
   no-progress / budget caps, human checkpoints, isolation and side effects.
5. **Preview** — ASCII flow; confirm.
6. **Emit** — write `SPEC.yaml`, compile, render, hand the go decision to the user.

## The files, and why they are named that way
| file | means | who writes it |
|---|---|---|
| `SPEC.yaml` | WHAT to build and how it is judged | human, via this interview |
| `PLAN.md` | WHY the loop is shaped this way | compiler |
| `RUN.md` | HOW to run it (orchestrator playbook) | compiler |
| `implementation-notes.md` | what actually happened while building | builder, every iteration |
| `loop.resolved.json` | machine-readable spec | compiler |
| `loop-state.json` | iteration count, verdicts, spend | orchestrator, every iteration |
| `loop.html` | the page a human opens | `render`, every iteration |

Agents edit markdown and JSON. Humans read rendered HTML. `loop.html` is
regenerated, never hand-edited.

## implementation-notes.md — the builder's four sections
**設計決策** (choices made where the spec was silent) · **偏離情況** (deliberate
deviations, with reasons) · **價值取捨** (alternatives considered and why this one
won) · **開放式問題** (only a question where both hold: (1) two competent
builders would choose differently; (2) the choice changes what the owner
sees or pays for — output shape, scope, cost, accepted risk. Everything else
is a design decision — use your default).

Three mechanisms hang off it:
- **Delivery gate.** No notes update = nothing was delivered. Send it back before
  running any gate. **Probe writability before emitting:** dispatch one throwaway
  builder subagent — the same builder invoke the SPEC council names, same model,
  same sandbox flag, not a stand-in — to write `<target>/.probe-write`, then
  read that path back yourself. Also have it run one command (e.g.
  `py -3 -c "print(1)"`) and return the stdout: a session opening is not the
  same as a process actually starting. File absent = this runtime blocks
  builder writes — move the notes write to the orchestrator (builder returns
  the four sections in its report) and say so in `SPEC.yaml`. Exec failing
  (e.g. Codex `CreateProcessWithLogonW failed: 5`) means the Council stage
  swaps the builder or writes a waiver — never emit on a probe that only
  wrote the file and never ran a command. Never leave the gate hanging on an
  action a guard stops: a blocked worker silently routes around it and puts
  the update in its message
  instead. Delete the probe file before emitting. (obs #209)
- **Judge input.** The judge reads 偏離情況 against `SPEC.yaml`. An unrecorded
  deviation is itself a blocking issue; a recorded one is judged on its reason.
- **Checkpoint agenda.** At each human checkpoint the orchestrator surfaces
  開放式問題 plus the load-bearing 設計決策. Whatever the human rules on is
  written back into `SPEC.yaml` — that is how the spec grows a decision trail.
  Before writing CHECKPOINT.md, triage each candidate 開放式問題 against the
  admission test above; anything that fails it moves to 設計決策 instead.

## File rules
- argv arrays, never shell strings, for every check and external invocation.
- Never write API keys / tokens / passwords into any emitted file.
- Keep `SPEC.yaml` human-readable and commented. Machines read
  `loop.resolved.json`.
- Reading lists split by role: the orchestrator reads `RUN.md` plus the
  criteria/stop/gates fields in `loop.resolved.json`, pulling `SPEC.yaml` /
  `PLAN.md` prose in only by section as a step needs it; a builder or judge
  subagent reads the full pack up front, referenced by path.

## Design-only boundary (hard rule)
LoopForge designs and emits. It does not start iteration 1, schedule anything,
or manage child agents. Emitting is where it stops; the human decides when the
loop opens.

## Compiler invariants (already enforced — rely on them, don't re-explain)
- Rejects a final gate whose `verdict_source` is not `human`.
- Rejects a reviewer as a `revise_until_clean` verdict_source.
- Rejects a builder sitting on a gate that grades its own work.
- Rejects any gate name outside `plan_gate` / `delivery_gate` / `final_gate` —
  gates are a closed set, and a fourth one would be enforced by nothing.
- Rejects a `verdict_source` that names no council member, under every policy;
  `revise_until_clean` additionally requires that member to be a judge.
- Rejects a `fixed_passes` gate whose `max_revisions` exceeds the no-progress
  window (the gate would stall out before it could proceed).
- Rejects a spec missing any required cap.
- Sets `no_progress.signature_match: normalized`.

## Appendix — external runner mode (unattended runs)
The orchestrator is a session, so the loop pauses when the session ends. When the
loop must survive that — overnight runs, scheduled wakeups, restart-safe
retries — set `execution.mode: external_runner` and name your scheduler or runner
of choice in `execution.runner`. `RUN.md` then carries a handoff section: the
runner reads `loop.resolved.json` and owes the same contract, **including the
human final gate**. Durability changes who drives the loop, never who signs it off.

## Appendix — external (cross-family) judge
Optional. A fresh same-family subagent already removes context contamination; a
different model family additionally covers same-family blind spots, at the cost
of money and a vendor boundary. To use it, add a council member with
`judge: deepseek` (bundled `adapters/judge_deepseek.py`, needs `DEEPSEEK_API_KEY`)
or your own `invoke` argv. Then, and only then, the privacy contract applies:
declare what leaves the machine in `privacy.egress`, set redaction globs, scrub
secret patterns from artifact CONTENT (not just filenames), and get explicit
consent before the first send.
