English | [繁體中文](README.zh-TW.md)

# LoopForge

A loop design coach for Claude Code. It interviews you through six stages —
goal, verification, council, gates and caps, preview, emit — critiques each
answer against a rubric, and emits a spec plus an orchestrator playbook for an
agent loop that builds, checks, and revises its own work.

LoopForge is design-only. It never starts the loop: after emitting, a human
decides when iteration 1 opens.

## Install

Copy this folder into your Claude Code skills directory:

```bash
git clone https://github.com/kennethlaw325/loopforge.git ~/.claude/skills/loopforge
```

Then in Claude Code:

```
/loopforge ./my-loop
```

`--fast` accepts strong answers in one pass instead of critiquing every stage.

**Requirements:** Python 3.11+ (`py -3` on Windows, `python3` on macOS/Linux)
and PyYAML (`py -3 -m pip install PyYAML`) for reading `SPEC.yaml`. That is the
only dependency — the compiler, the cap checker and the dashboard renderer are
otherwise stdlib.

## The files it emits

| file | means | written by |
|---|---|---|
| `SPEC.yaml` | **what** to build and how it will be judged | you, through the interview |
| `PLAN.md` | **why** the loop is shaped this way | compiler |
| `RUN.md` | **how** to run it — the orchestrator playbook | compiler |
| `implementation-notes.md` | what actually happened while building | the builder, every iteration |
| `loop.resolved.json` | machine-readable spec | compiler |
| `loop-state.json` | iteration count, verdicts, spend | the orchestrator |
| `loop.html` | one-page dashboard | `render`, every iteration |

Agents edit markdown and JSON. Humans read the rendered HTML.

## Quickstart

1. **Design.** `/loopforge ./my-loop` walks the six stages and writes `SPEC.yaml`.
2. **Compile.** `py -3 scripts/loopforge.py compile ./my-loop/SPEC.yaml` produces
   `loop.resolved.json`, `PLAN.md` and `RUN.md`. It rejects a spec that lets the
   loop sign off on its own delivery, lets a reviewer issue a verdict, lets a
   builder grade itself, or leaves out a cap.
3. **Human go.** Read the preview. Nothing runs until you say so.
4. **Run.** The session follows `RUN.md` as the loop's orchestrator. Each
   iteration it runs `loopforge.py check` (a file read that says whether a cap
   allows another round), dispatches a fresh builder subagent, runs the
   programmatic criteria itself, dispatches a fresh judge subagent for what a
   script cannot measure, and appends the verdict to `loop-state.json`.
5. **Render.** `loopforge.py render ./my-loop` regenerates `loop.html`:
   progress, verdict history, criteria checklist, and the builder's open
   questions pinned to the top.

The last gate is always human. A builder can misread a spec and a same-family
judge can misread it the same way — that gate is where a person catches it.

## Security model

LoopForge is a single-operator tool: you write the spec, you run the loop, and
everything it touches runs as you.

- **`SPEC.yaml` is executable config.** Its `check` commands run with your
  permissions. Review a spec you did not write the way you would review a
  Makefile or a CI config before running it.
- **`loop-state.json` and `implementation-notes.md` are ordinary files.** They
  are the loop's memory, not a tamper-proof audit log — anything with write
  access to the directory can edit them.
- **Nothing leaves your machine by default.** The default judge is a subagent in
  your own session. The optional external judge sends artifacts to a third-party
  API; it is opt-in, and the privacy contract (redaction, content scrubbing,
  consent on first send) applies only once you enable it.

## Tests

```bash
py -3 scripts/test_loopforge.py
```
