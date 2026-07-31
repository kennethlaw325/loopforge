---
description: Design an agent loop (strict-mode coach, typed verification, builder/judge subagents, human ship gate) and emit SPEC.yaml + PLAN.md + RUN.md. Design-only — a human decides when it starts.
argument-hint: "[target-dir] [--fast]"
---

Invoke the `loopforge` skill to design an agent loop. Strict mode by default
(every stage critiqued before advancing); pass `--fast` to accept strong stages
in one pass.

LoopForge runs a six-stage interview and emits `SPEC.yaml` (what to build),
`PLAN.md` (why the loop is shaped this way), `RUN.md` (how to run it),
`loop.resolved.json` and an empty `loop.html` dashboard. The session that later
follows `RUN.md` is the loop's orchestrator: it dispatches a fresh builder
subagent and a fresh judge subagent each iteration, and never builds or judges
itself.

LoopForge does not start the loop. Iteration 1 begins only when you say go.

Target dir: $ARGUMENTS
