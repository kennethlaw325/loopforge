#!/usr/bin/env python3
"""LoopForge compiler + runtime checks (loop DESIGN tool).

LoopForge designs loops. It never runs one. The session that reads RUN.md is
the orchestrator; this script only turns a hand-written SPEC.yaml into machine
artifacts and answers deterministic questions about a running loop.

Subcommands:
  compile <SPEC.yaml> -> loop.resolved.json (machine) + PLAN.md + RUN.md
  check   <dir>       -> exit 0 = another iteration is allowed
                         exit 1 = a cap stops the loop (prints which one)
  render  <dir>       -> loop.html, a self-contained one-page dashboard

Compile-time invariants (the reason this file exists):
  - the LAST gate's verdict_source must be `human` -- a loop may not sign off
    on its own delivery;
  - a reviewer may never be a `revise_until_clean` verdict_source (reviewers
    write notes, judges write verdicts);
  - a builder may never sit on a gate that grades its own work;
  - a `fixed_passes` gate whose max_revisions exceeds the no-progress window
    stalls out before it can proceed -- rejected;
  - every cap is required: max_iterations, per-gate max_revisions,
    no_progress.max_stalled_iterations, and at least one budget cap.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any

DEFAULT_REDACTIONS = [".env", ".env.*", "secrets/**", "**/*.key"]
ADAPTER_DIR = Path(__file__).resolve().parent.parent / "adapters"
SCRIPT_PATH = Path(__file__).resolve()

GATE_ORDER = ("plan_gate", "delivery_gate", "final_gate")
FINAL_GATE = GATE_ORDER[-1]
ROLES = {"builder", "reviewer", "judge"}
BUDGET_KEYS = ("wall_clock_min", "usd", "tokens")

STATE_FILE = "loop-state.json"
RESOLVED_FILE = "loop.resolved.json"
NOTES_FILE = "implementation-notes.md"
DASHBOARD_FILE = "loop.html"

# implementation-notes.md contract. Headings are matched by substring, so
# `## 設計決策 (Design decisions)` still binds to the first slot.
NOTE_SECTIONS = (
    ("設計決策", "Design decisions made where the spec was silent"),
    ("偏離情況", "Deliberate deviations from the spec, with reasons"),
    ("價值取捨", "Alternatives considered and why this one won"),
    ("開放式問題", "Questions for the human to rule on"),
)
OPEN_QUESTIONS = NOTE_SECTIONS[3][0]

# `judge: <name>` shorthand -> argv, for the OPTIONAL external-judge mode.
# Adapters read the prompt from stdin and print one fenced JSON verdict.
JUDGE_SHORTHANDS: dict[str, list[str]] = {
    "deepseek": ["<python>", str(ADAPTER_DIR / "judge_deepseek.py")],
}


class LoopForgeError(RuntimeError):
    pass


def python_argv() -> list[str]:
    """Cross-platform python launcher for emitted argv arrays."""
    return ["py", "-3"] if os.name == "nt" else ["python3"]


# ---------- io ----------

def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise LoopForgeError(
            "PyYAML required. Install: py -3 -m pip install PyYAML  (POSIX: python3 -m pip install PyYAML)"
        ) from exc
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise LoopForgeError(f"Could not parse YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LoopForgeError(f"{path} must be a YAML mapping at top level")
    return data


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise LoopForgeError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LoopForgeError(f"{path} must contain a JSON object")
    return data


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_argv(value: Any, field: str) -> list[str]:
    if isinstance(value, list) and all(isinstance(i, str) for i in value):
        return value
    if isinstance(value, str):
        return shlex.split(value, posix=os.name != "nt")
    raise LoopForgeError(f"{field} must be an argv array or string")


# ---------- validation ----------

def criteria_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    criteria = spec.get("goal", {}).get("verification", [])
    if not isinstance(criteria, list) or not criteria:
        raise LoopForgeError("goal.verification must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for item in criteria:
        if not isinstance(item, dict):
            raise LoopForgeError("Each verification criterion must be an object")
        cid, ctype = item.get("id"), item.get("type")
        if not isinstance(cid, str) or not cid:
            raise LoopForgeError("Each criterion needs a non-empty id")
        if cid in result:
            raise LoopForgeError(f"Duplicate criterion id: {cid}")
        if ctype not in {"programmatic", "judge", "human"}:
            raise LoopForgeError(f"Criterion {cid} has invalid type: {ctype}")
        if ctype == "programmatic":
            item["check"] = normalize_argv(item.get("check"), f"criterion {cid}.check")
            if item.get("expect") not in {"exit_zero", "exit_nonzero", "stdout_contains"}:
                raise LoopForgeError(f"Criterion {cid}.expect must be exit_zero/exit_nonzero/stdout_contains")
            if item.get("expect") == "stdout_contains" and not isinstance(item.get("contains"), str):
                raise LoopForgeError(f"Criterion {cid} stdout_contains needs `contains`")
        elif ctype == "judge" and not isinstance(item.get("rubric"), str):
            raise LoopForgeError(f"Criterion {cid} needs a judge rubric")
        elif ctype == "human" and not isinstance(item.get("prompt"), str):
            raise LoopForgeError(f"Criterion {cid} needs a human prompt")
        result[cid] = item
    return result


def validate_member(member: dict[str, Any]) -> None:
    mid, role = member.get("id"), member.get("role")
    if not isinstance(mid, str) or not mid:
        raise LoopForgeError("Each council member needs a non-empty id")
    if role not in ROLES:
        raise LoopForgeError(f"Council member {mid} role must be one of {sorted(ROLES)}")
    kind = member.setdefault("kind", "subagent")
    if kind not in {"subagent", "external"}:
        raise LoopForgeError(f"Council member {mid}.kind must be subagent or external")

    shorthand = member.get("judge")
    if shorthand:
        if shorthand not in JUDGE_SHORTHANDS:
            raise LoopForgeError(f"Unknown judge shorthand: {shorthand}")
        member["kind"] = kind = "external"
        member.setdefault("cli", shorthand)
        argv = [*python_argv(), *JUDGE_SHORTHANDS[shorthand][1:]]
        member.setdefault("invoke", argv)

    if kind == "external":
        if not member.get("invoke"):
            raise LoopForgeError(
                f"Council member {mid} is external: it needs an `invoke` argv array or a `judge:` shorthand"
            )
        member["invoke"] = normalize_argv(member["invoke"], f"council.{mid}.invoke")
        timeout = member.setdefault("timeout_sec", 600)
        if not isinstance(timeout, int) or timeout <= 0:
            raise LoopForgeError(f"Council member {mid}.timeout_sec must be a positive integer")
        member.setdefault("local", member.get("cli") == "ollama")
    else:
        # A fresh same-family subagent. `inherit` = same model as the orchestrator.
        member.setdefault("model", "inherit")
        member.setdefault("context", "fresh")
        if member.get("context") != "fresh":
            raise LoopForgeError(
                f"Council member {mid}.context must be `fresh`: a reused context carries the bias the gate exists to catch"
            )
    member.setdefault("scope", ["plan", "delivery"])


def validate_gate(name, gate, criteria, members, no_progress_window) -> None:
    if not isinstance(gate, dict):
        raise LoopForgeError(f"gates.{name} is required and must be an object")
    policy = gate.get("verdict_policy")
    if policy not in {"revise_until_clean", "fixed_passes"}:
        raise LoopForgeError(f"{name}.verdict_policy must be revise_until_clean or fixed_passes")
    max_revisions = gate.get("max_revisions")
    if not isinstance(max_revisions, int) or max_revisions < 0:
        raise LoopForgeError(
            f"{name}.max_revisions is a required cap and must be a non-negative integer"
        )
    for cid in gate.get("criteria", []):
        if cid not in criteria:
            raise LoopForgeError(f"{name} references unknown criterion: {cid}")
    for mid in gate.get("members", []):
        if mid not in members:
            raise LoopForgeError(f"{name} references unknown council member: {mid}")
        if members[mid].get("role") == "builder":
            raise LoopForgeError(
                f"{name} lists builder `{mid}` as a gate member: a builder may not grade its own work"
            )

    source = gate.get("verdict_source")
    if name == FINAL_GATE and source != "human":
        raise LoopForgeError(
            f"{name}.verdict_source must be `human` (got {source!r}). The final delivery gate is "
            "the one place a person must look: a builder can misread the spec and a same-family "
            "judge can misread it the same way, and the loop would then certify itself clean."
        )
    # Existence is checked for every policy; only revise_until_clean also
    # constrains the role (a fixed_passes gate may legitimately name a reviewer).
    if source is not None and source != "human" and source not in members:
        raise LoopForgeError(
            f"{name}.verdict_source names `{source}`, which is not a council member id or `human`"
        )
    if source in members and members[source].get("role") == "builder":
        raise LoopForgeError(
            f"{name}.verdict_source names builder `{source}`: a builder may not grade its own work"
        )
    if policy == "revise_until_clean":
        if source == "human":
            return
        if source is None:
            raise LoopForgeError(f"{name}.verdict_source must name a judge member or human")
        if members[source].get("role") != "judge":
            raise LoopForgeError(
                f"{name}.verdict_source names `{source}`, a {members[source].get('role')}: "
                "reviewers write notes, only a judge writes a verdict"
            )
    if policy == "fixed_passes" and max_revisions > no_progress_window:
        raise LoopForgeError(
            f"{name}: fixed_passes max_revisions ({max_revisions}) exceeds the no-progress window "
            f"({no_progress_window}); the gate appends a constant failure each round and the "
            f"no-progress detector stops the loop before the gate can proceed. Lower max_revisions "
            f"or raise loop_control.no_progress.max_stalled_iterations."
        )


def validate_invariants(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise LoopForgeError("invariants must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise LoopForgeError("invariants entries must be objects")
        iid, status = entry.get("id"), entry.get("status")
        if not isinstance(iid, str) or not iid:
            raise LoopForgeError("Each invariants entry needs an id (e.g. J1, G7)")
        if status not in {"checked", "waived"}:
            raise LoopForgeError(f"invariants[{iid}].status must be checked or waived")
        if status == "checked" and not entry.get("where"):
            raise LoopForgeError(f"invariants[{iid}] is checked: name `where` (a criterion id or gate)")
        if status == "waived" and not entry.get("reason"):
            raise LoopForgeError(f"invariants[{iid}] is waived: `reason` is required. Silence is not a waiver.")
    return entries


def normalize_spec(spec: dict[str, Any], source_path: Path) -> dict[str, Any]:
    if spec.get("version") != 2:
        raise LoopForgeError(
            "Only SPEC.yaml version: 2 is supported. (v1 `loop.yaml` predates orchestrator mode: "
            "drop `host`, add a builder council member, add gates.final_gate with verdict_source: human.)"
        )

    goal = spec.get("goal")
    if not isinstance(goal, dict):
        raise LoopForgeError("goal must be an object")
    for field in ("statement", "definition_of_done"):
        if not isinstance(goal.get(field), str) or not goal[field].strip():
            raise LoopForgeError(f"goal.{field} is required")
    for index, source in enumerate(goal.get("context_sources", [])):
        if not isinstance(source, dict):
            raise LoopForgeError("goal.context_sources entries must be objects")
        if "cmd" in source:
            source["cmd"] = normalize_argv(source["cmd"], f"context_sources[{index}].cmd")

    criteria = criteria_by_id(spec)

    council_list = spec.get("council")
    if not isinstance(council_list, list) or not council_list:
        raise LoopForgeError("council must be a non-empty list")
    for member in council_list:
        if not isinstance(member, dict):
            raise LoopForgeError("council entries must be objects")
        validate_member(member)
    members = {m["id"]: m for m in council_list}
    if len(members) != len(council_list):
        raise LoopForgeError("Duplicate council member id")
    if not any(m["role"] == "builder" for m in members.values()):
        raise LoopForgeError(
            "council needs at least one `builder` member: the subagent the orchestrator dispatches "
            "to do the work each iteration"
        )

    control = spec.get("loop_control")
    if not isinstance(control, dict):
        raise LoopForgeError("loop_control must be an object")
    if not isinstance(control.get("max_iterations"), int) or control["max_iterations"] <= 0:
        raise LoopForgeError("loop_control.max_iterations is a required cap and must be a positive integer")

    budget = control.get("budget")
    if not isinstance(budget, dict) or not any(
        isinstance(budget.get(k), (int, float)) and budget[k] > 0 for k in BUDGET_KEYS
    ):
        raise LoopForgeError(
            "loop_control.budget is a required cap: set at least one of "
            f"{', '.join(BUDGET_KEYS)} to a positive number"
        )

    no_progress = control.get("no_progress")
    if not isinstance(no_progress, dict):
        raise LoopForgeError("loop_control.no_progress is a required cap and must be an object")
    window = no_progress.get("max_stalled_iterations")
    if not isinstance(window, int) or window <= 0:
        raise LoopForgeError(
            "loop_control.no_progress.max_stalled_iterations is a required cap and must be a positive integer"
        )
    no_progress.setdefault("action", "stop")
    no_progress.setdefault(
        "signals", ["same blocking issue repeats", "artifact unchanged", "check output unchanged"]
    )
    # Normalized: lowercase + collapsed whitespace, so a judge rephrasing the
    # same complaint still counts toward the stall window.
    no_progress.setdefault("signature_match", "normalized")

    gates = spec.get("gates")
    if not isinstance(gates, dict):
        raise LoopForgeError("gates must be an object")
    unknown = sorted(set(gates) - set(GATE_ORDER))
    if unknown:
        raise LoopForgeError(
            f"Unknown gate(s): {', '.join(unknown)}. The loop runs exactly these gates: "
            f"{', '.join(GATE_ORDER)}. A gate under any other name is validated by nothing and "
            "run by nothing — PLAN.md, RUN.md, the dashboard and the cap checker all ignore it — "
            "so it is rejected here rather than silently dropped."
        )
    for gate_name in GATE_ORDER:
        validate_gate(gate_name, gates.get(gate_name), criteria, members, window)

    execution = spec.setdefault("execution", {})
    execution.setdefault("mode", "orchestrator")
    if execution["mode"] not in {"orchestrator", "external_runner"}:
        raise LoopForgeError("execution.mode must be orchestrator or external_runner")
    if execution["mode"] == "external_runner" and not execution.get("runner"):
        raise LoopForgeError("execution.mode is external_runner: name the runner in execution.runner")
    execution.setdefault("isolation", "current_workspace")
    if execution["isolation"] not in {"current_workspace", "branch", "worktree", "sandbox"}:
        raise LoopForgeError("execution.isolation must be current_workspace/branch/worktree/sandbox")
    execution.setdefault("side_effects", {}).setdefault("requires_approval", True)
    execution["side_effects"].setdefault("duplicate_action_check", True)

    observability = spec.setdefault("observability", {})
    for key, default in (
        ("state_file", STATE_FILE),
        ("notes_file", NOTES_FILE),
        ("dashboard", DASHBOARD_FILE),
        ("checkpoint_granularity", "gate"),
    ):
        observability.setdefault(key, default)

    workspace = spec.setdefault("workspace", {})
    workspace.setdefault("dir", "./loop-workspace")
    workspace.setdefault("layout", ["plan.md", "delivery-{n}.md", "review-{n}.md"])

    # Only relevant to the optional external-judge mode; harmless otherwise.
    privacy = spec.setdefault("privacy", {})
    for entry in privacy.setdefault("egress", []):
        if not isinstance(entry, dict):
            raise LoopForgeError("privacy.egress entries must be objects")
        entry.setdefault("redact", DEFAULT_REDACTIONS)
        entry.setdefault("consent", "required")
        entry.setdefault("scrub_content", True)

    spec["invariants"] = validate_invariants(spec.get("invariants", []))

    return to_jsonable({
        "$schema": "loopforge/loop.resolved.v2",
        "compiled_at": _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
        "source": str(source_path),
        **spec,
        "criteria_by_id": criteria,
        "council_by_id": members,
    })


# ---------- state + caps ----------

def normalize_signature(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def iteration_signature(record: dict[str, Any]) -> str:
    if record.get("signature"):
        return normalize_signature(record["signature"])
    issues = record.get("blocking_issues") or []
    return normalize_signature(" ".join(str(i) for i in issues))


def resolve_in(directory: Path, name: Any, field: str) -> Path:
    """A path the SPEC names must stay inside the loop directory."""
    if not isinstance(name, str) or not name:
        raise LoopForgeError(f"observability.{field} must be a non-empty filename")
    path = (directory / name).resolve()
    if not path.is_relative_to(directory):
        raise LoopForgeError(
            f"observability.{field} is {name!r}, which resolves outside {directory}. "
            "Loop files stay in the loop directory."
        )
    return path


def require_number(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoopForgeError(f"{field} must be a number, got {type(value).__name__}")


def load_resolved(directory: Path) -> dict[str, Any]:
    """Load loop.resolved.json and check the fields cap_report does math on."""
    path = directory / RESOLVED_FILE
    if not path.exists():
        raise LoopForgeError(f"{path} not found — compile SPEC.yaml first")
    resolved = load_json(path)
    require_number(resolved.get("loop_control", {}).get("max_iterations"),
                   f"{path}: loop_control.max_iterations")
    for name in GATE_ORDER:
        require_number(resolved.get("gates", {}).get(name, {}).get("max_revisions"),
                       f"{path}: gates.{name}.max_revisions")
    return resolved


def load_state(directory: Path, resolved: dict[str, Any]) -> dict[str, Any]:
    path = resolve_in(directory, resolved.get("observability", {}).get("state_file", STATE_FILE), "state_file")
    if not path.exists():
        return {"iterations": [], "spend": {}, "gate_revisions": {}}
    state = load_json(path)
    state.setdefault("iterations", [])
    state.setdefault("spend", {})
    state.setdefault("gate_revisions", {})
    if not isinstance(state["iterations"], list):
        raise LoopForgeError(f"{path}: iterations must be a list")
    for index, record in enumerate(state["iterations"]):
        if not isinstance(record, dict):
            raise LoopForgeError(
                f"{path}: iterations[{index}] must be an object, got {type(record).__name__}"
            )
    for key in ("spend", "gate_revisions"):
        if not isinstance(state[key], dict):
            raise LoopForgeError(f"{path}: {key} must be an object")
        for name, value in state[key].items():
            require_number(value, f"{path}: {key}.{name}")
    return state


def cap_report(resolved: dict[str, Any], state: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (blockers, remaining). Empty blockers = another iteration is allowed."""
    control = resolved.get("loop_control", {})
    gates = resolved.get("gates", {})
    iterations = state.get("iterations", [])
    done = len(iterations)
    blockers: list[str] = []
    remaining: list[str] = []

    max_iterations = control.get("max_iterations", 0)
    remaining.append(f"iterations: {done}/{max_iterations} used, {max(max_iterations - done, 0)} left")
    if done >= max_iterations:
        blockers.append(f"max_iterations reached ({done}/{max_iterations})")

    for name in GATE_ORDER:
        cap = gates.get(name, {}).get("max_revisions")
        used = state.get("gate_revisions", {}).get(name, 0)
        if cap is None:
            continue
        remaining.append(f"{name}.max_revisions: {used}/{cap} used")
        if used >= cap:
            blockers.append(
                f"{name} revision quota exhausted ({used}/{cap}) -- escalate to a human, do not open another iteration"
            )

    spend = state.get("spend", {})
    for key, cap in (control.get("budget") or {}).items():
        if not isinstance(cap, (int, float)):
            continue
        used = spend.get(key, 0) or 0
        remaining.append(f"budget.{key}: {used}/{cap} used")
        if used >= cap:
            blockers.append(f"budget cap {key} exceeded ({used}/{cap})")

    window = control.get("no_progress", {}).get("max_stalled_iterations", 0)
    if window and done >= window:
        recent = [iteration_signature(r) for r in iterations[-window:]]
        if recent[0] and all(sig == recent[0] for sig in recent):
            blockers.append(
                f"no progress: the same blocking signature repeated {window}x -- \"{recent[0][:120]}\""
            )
    remaining.append(f"no_progress window: {window}")

    last = iterations[-1] if iterations else {}
    if last.get("gate") == FINAL_GATE and last.get("verdict") == "pass":
        blockers.append("loop already complete: the final gate passed. Nothing left to iterate.")
    return blockers, remaining


# ---------- rendering ----------

def clip(text: Any, width: int) -> str:
    value = str(text or "")
    return value if len(value) <= width else value[: width - 1] + "~"


def ascii_box(*rows: str, width: int = 30) -> list[str]:
    border = "+" + "-" * (width + 2) + "+"
    return [border, *[f"| {clip(r, width):<{width}} |" for r in rows], border]


def budget_bits(control: dict[str, Any]) -> str:
    budget = control.get("budget", {})
    bits = []
    for key, suffix in (("wall_clock_min", "m"), ("usd", "usd"), ("tokens", "tok")):
        if budget.get(key) is not None:
            bits.append(f"{budget[key]}{suffix}")
    return ", ".join(bits) or "caps"


def render_ascii(resolved: dict[str, Any]) -> str:
    gates, control = resolved.get("gates", {}), resolved.get("loop_control", {})
    plan_g = gates.get("plan_gate", {})
    deliv_g = gates.get("delivery_gate", {})
    final_g = gates.get(FINAL_GATE, {})
    no_prog = control.get("no_progress", {})
    builder = next((m["id"] for m in resolved.get("council", []) if m.get("role") == "builder"), "builder")
    lines: list[str] = []
    lines += ascii_box("0. loopforge.py check", "caps read from state file")
    lines += ["              |", "              v"]
    lines += ascii_box(f"1. builder subagent ({clip(builder, 12)})", "plan.md + notes update")
    lines += ["              |", "              v"]
    lines += ascii_box("2. PLAN GATE", f"verdict: {plan_g.get('verdict_source', 'human')}")
    lines += [f"      | revise <= {plan_g.get('max_revisions', 0)} -> step 1", "      | pass", "      v"]
    lines += ascii_box("3. builder subagent", "delivery-N + notes update")
    lines += ["              |", "              v"]
    lines += ascii_box("4. programmatic checks", "cheap + deterministic first")
    lines += ["              |", "              v"]
    lines += ascii_box("5. DELIVERY GATE", f"verdict: {deliv_g.get('verdict_source', 'human')}")
    lines += [f"      | revise <= {deliv_g.get('max_revisions', 0)} -> step 3", "      | pass", "      v"]
    lines += ascii_box("6. write loop-state.json", "then render loop.html")
    lines += ["              |", "              v"]
    lines += ascii_box("7. FINAL GATE (human)", f"verdict: {final_g.get('verdict_source', 'human')}")
    lines += [
        "",
        f"STOP: final gate passes | max {control.get('max_iterations')} iter | "
        f"no-progress x{no_prog.get('max_stalled_iterations')} | budget {budget_bits(control)}",
    ]
    return "\n".join(lines)


def render_plan(resolved: dict[str, Any]) -> str:
    meta, goal = resolved.get("meta", {}), resolved.get("goal", {})
    control, gates = resolved.get("loop_control", {}), resolved.get("gates", {})
    execution = resolved.get("execution", {})
    out = [
        f"# PLAN — {meta.get('name', 'LoopForge loop')}",
        "",
        "Why this loop is shaped the way it is. `SPEC.yaml` says WHAT to build,",
        "this file says WHY the design looks like this, and `RUN.md` says HOW to run it.",
        "",
        meta.get("description", "").strip(),
        "",
        "## Goal", "", goal.get("statement", "").strip(),
        "", "## Definition of done", "", goal.get("definition_of_done", "").strip(),
        "", "## Verification criteria", "",
    ]
    for item in goal.get("verification", []):
        detail = item.get("rubric") or item.get("prompt") or json.dumps(item.get("check", []))
        out.append(f"- `{item['id']}` ({item['type']}) — {str(detail).strip()[:200]}")
    out += ["", "## Council", ""]
    for m in resolved.get("council", []):
        if m.get("kind") == "external":
            out.append(f"- `{m['id']}` — {m['role']}, external via `{json.dumps(m.get('invoke', []))}`")
        else:
            out.append(f"- `{m['id']}` — {m['role']}, fresh subagent, model `{m.get('model')}`")
    out += ["", "## Gates — what each one is for", ""]
    purpose = {
        "plan_gate": "Catches a wrong plan before any delivery work is spent on it.",
        "delivery_gate": "Grades each delivery against the criteria. Programmatic checks run first; the judge only rules on what a script cannot measure.",
        FINAL_GATE: "The ship gate. Always human: a builder can misread the spec and a same-family judge can misread it the same way.",
    }
    for name in GATE_ORDER:
        gate = gates.get(name, {})
        out += [
            f"### {name}",
            f"- {purpose[name]}",
            f"- policy `{gate.get('verdict_policy')}` · verdict_source `{gate.get('verdict_source')}` "
            f"· max_revisions `{gate.get('max_revisions')}`",
            f"- criteria: `{', '.join(gate.get('criteria', [])) or 'none'}`",
            "",
        ]
    out += [
        "## Caps", "",
        f"- max_iterations: `{control.get('max_iterations')}`",
        f"- budget: `{json.dumps(control.get('budget', {}), sort_keys=True)}`",
        f"- no_progress: `{json.dumps(control.get('no_progress', {}), sort_keys=True)}`",
        "",
        "Caps are enforced by reading files, not by remembering: run",
        "`loopforge.py check <dir>` at the top of every iteration.",
        "",
        "## Execution", "",
        f"- mode: `{execution.get('mode')}`"
        + (f" (runner: `{execution.get('runner')}`)" if execution.get("runner") else ""),
        f"- isolation: `{execution.get('isolation')}`",
        f"- side effects require approval: `{execution.get('side_effects', {}).get('requires_approval')}`",
        "", "## Hard-invariant ledger", "",
        "Every applicable invariant from `references/hard-invariants.md` is either wired",
        "to a check or waived here with a reason. Anything absent from this table is",
        "unwaived — silence is not a waiver.", "",
    ]
    entries = resolved.get("invariants", [])
    if entries:
        out += ["| id | status | where / why |", "|---|---|---|"]
        for entry in entries:
            detail = entry.get("where") if entry["status"] == "checked" else entry.get("reason")
            out.append(f"| {entry['id']} | {entry['status']} | {detail} |")
    else:
        out.append("_(none recorded — walk the registry before the first iteration)_")
    out += ["", "## Flow", "", "```text", render_ascii(resolved), "```", ""]
    return "\n".join(out)


def render_run(resolved: dict[str, Any]) -> str:
    meta = resolved.get("meta", {})
    goal, gates = resolved.get("goal", {}), resolved.get("gates", {})
    control = resolved.get("loop_control", {})
    execution, observ = resolved.get("execution", {}), resolved.get("observability", {})
    workspace = resolved.get("workspace", {})
    council = resolved.get("council", [])
    builders = [m for m in council if m.get("role") == "builder"]
    builder = builders[0] if builders else {"id": "builder", "model": "inherit"}
    handover = control.get("orchestrator_handover_every", 3)
    py = " ".join(python_argv())
    # Forward slashes: one form that works in PowerShell, cmd and Git Bash alike.
    script = SCRIPT_PATH.as_posix()
    notes = observ.get("notes_file", NOTES_FILE)

    out = [
        f"# RUN — orchestrator playbook for `{meta.get('name', 'loop')}`",
        "",
        "**You (the session reading this) are the orchestrator.** You do not write the",
        "deliverable yourself. Each iteration you dispatch a fresh builder subagent, run",
        "the programmatic checks, dispatch a fresh judge subagent, record the verdict, and",
        "regenerate the dashboard. Holding the spec and the verdict record is the whole job:",
        "the moment you start building, you lose the independence the gates depend on.",
        "",
        "Nothing starts until the human says go.",
        "",
        "\"Subagent\" below means whatever your runtime uses to get a clean context: a",
        "subagent, a spawned session, or a separate agent process. What matters is that",
        "the builder and the judge each start without the other's reasoning in scope.",
        "",
        "## Files",
        "",
        "| file | written by | what it is |",
        "|---|---|---|",
        "| `SPEC.yaml` | human (via LoopForge) | what to build, and how it will be judged |",
        "| `PLAN.md` | compiler | why the loop is shaped this way |",
        "| `RUN.md` | compiler | this playbook |",
        f"| `{RESOLVED_FILE}` | compiler | machine-readable spec; `check` reads it |",
        f"| `{observ.get('state_file', STATE_FILE)}` | orchestrator | iteration count, verdicts, spend |",
        f"| `{notes}` | builder | what actually happened while building |",
        f"| `{observ.get('dashboard', DASHBOARD_FILE)}` | `render` | the page a human opens |",
        "",
        "Agents edit markdown and JSON. Humans read the rendered HTML. Never hand-edit",
        f"`{observ.get('dashboard', DASHBOARD_FILE)}` — it is regenerated every iteration.",
        "",
        "## Per-iteration sequence",
        "",
        "**0 · Ask permission to iterate.**",
        "",
        "```text",
        f"{py} {script} check <dir>",
        "```",
        "",
        "Exit 0 = go, and the remaining quota is printed. Non-zero = STOP: print the",
        "blocker to the human and wait. Do not re-derive the caps yourself; this command",
        "exists so cap enforcement is a file read, not a memory of one.",
        "",
        f"**1 · Dispatch the builder subagent** (`{builder.get('id')}`, model `{builder.get('model', 'inherit')}`, fresh context).",
        "The brief must carry: the goal, the definition of done, the criteria it will be",
        "judged on, the artifact paths, and the previous verdict's blocking issues (only",
        "those — not your own commentary, which contaminates the next attempt).",
        "",
        f"The builder MUST update `{notes}` as part of delivering. Four sections:",
        "",
    ]
    for name, gloss in NOTE_SECTIONS:
        out.append(f"- **{name}** — {gloss}")
    out += [
        "",
        f"**No `{notes}` update = nothing was delivered.** Send it back; do not run any gate",
        "on an undocumented delivery. This is a hard gate, not a nicety: it is the only",
        "record of what the builder decided that the spec never said.",
        "",
        "**2 · Run the programmatic criteria yourself.** They are cheap, deterministic, and",
        "free of judgment. Any failure goes straight back to the builder as an executor",
        "fault; do not spend a judge call on something a script already answered.",
        "",
    ]
    for item in goal.get("verification", []):
        if item["type"] == "programmatic":
            out.append(f"- `{item['id']}`: run `{json.dumps(item['check'])}`, expect `{item['expect']}`")
    out += [
        "",
        "**3 · Dispatch the judge subagent** (fresh context, never the builder's, never yours).",
        "The judge receives: the artifact, the criteria it must apply verbatim, `SPEC.yaml`,",
        f"and the **偏離情況** section of `{notes}`.",
        "",
        "Judge rules:",
        "",
        "- A verdict is `pass` or `revise`, plus blocking issues. Each blocking issue starts",
        "  with `[the criterion it violates]`; an issue that cannot cite a criterion is",
        "  advisory and belongs in notes.",
        "- **Compare the delivery against `SPEC.yaml`. A deviation that is not written down in",
        "  偏離情況 is itself a blocking issue.** A deviation that IS written down gets judged",
        "  on whether its stated reason holds.",
        "- A reviewer's notes never decide a gate. Only the gate's `verdict_source` does.",
        "",
        "**4 · Record the iteration.** Append one record to",
        f"`{observ.get('state_file', STATE_FILE)}` — this file is the loop's memory, not your context:",
        "",
        "```json",
        json.dumps(
            {
                "iterations": [
                    {
                        "n": 1,
                        "gate": "delivery_gate",
                        "verdict": "revise",
                        "blocking_issues": ["[criterion-id] what was wrong"],
                        "signature": "short stable phrase for the blocker",
                        "fault_source": "executor",
                        "criteria": {"criterion-id": "fail"},
                    }
                ],
                "gate_revisions": {"delivery_gate": 1},
                "spend": {"wall_clock_min": 6},
            },
            indent=2,
        ),
        "```",
        "",
        "`fault_source` matters: `max_revisions` counts **executor** faults only. A judge or",
        "transport fault is a free re-query. Rework the human asked for opens a NEW iteration",
        "and never burns gate quota.",
        "",
        "**5 · Regenerate the dashboard.**",
        "",
        "```text",
        f"{py} {script} render <dir>",
        "```",
        "",
        "## Stop conditions",
        "",
    ]
    out += [f"- {c}" for c in control.get("stop_conditions", [])] or ["- (none listed in SPEC)"]
    out += [
        f"- `check` returns non-zero (max {control.get('max_iterations')} iterations, "
        f"gate revision quota, budget {budget_bits(control)}, or "
        f"no progress x{control.get('no_progress', {}).get('max_stalled_iterations')})",
        f"- `{FINAL_GATE}` passes — and only a human can pass it",
        "",
        "## Human checkpoint agenda",
        "",
        "At every human checkpoint, and always before the final gate, put this in front of",
        "the person — do not summarize it away:",
        "",
        f"1. Every **{OPEN_QUESTIONS}** entry from `{notes}`.",
        "2. The **設計決策** entries that changed the shape of the deliverable.",
        "3. Any **偏離情況** the judge let through.",
        "",
        "Hand over the raw evidence with it — the actual check output, the judge's",
        "blocking issues verbatim, the 偏離情況 entries as written. A summary is your",
        "reading of the work; the final gate exists to get a second one.",
        "",
        "Whatever the human rules on gets **written back into `SPEC.yaml`** and recompiled.",
        "That is how the spec grows a trail: a question answered once never has to be",
        "re-litigated, and the next iteration's builder inherits the answer as a requirement.",
        "",
        f"Checkpoints declared in this spec: `{', '.join(control.get('human_checkpoints', [])) or 'final gate only'}`",
        "",
        "## Orchestrator handover",
        "",
        f"**Every {handover} iterations — or the moment verdicts start repeating — hand the loop to a",
        "fresh session.** An orchestrator that has read six revisions of the same artifact",
        "starts agreeing with the builder it has been reading. State lives in files precisely",
        "so the orchestrator can be replaced without losing anything.",
        "",
        "## Resume in a new session",
        "",
        "1. Read `SPEC.yaml` (what) and `PLAN.md` (why).",
        "2. Read this file (how).",
        f"3. Read `{observ.get('state_file', STATE_FILE)}` — iteration count, verdicts, spend so far.",
        f"4. Read `{notes}` — what the builder decided.",
        f"5. Run `{py} {script} check <dir>` and continue from step 1 above.",
        "",
        "Do not re-read the whole artifact history. The verdict record is the history.",
        "",
        "## Workspace",
        "",
        f"- dir: `{workspace.get('dir')}` · isolation: `{execution.get('isolation')}`",
        f"- side-effecting actions (push / publish / deploy / delete) require approval: "
        f"`{execution.get('side_effects', {}).get('requires_approval')}`",
        "",
    ]
    if execution.get("mode") == "external_runner":
        out += [
            "## External runner mode",
            "",
            f"This spec is set to `execution.mode: external_runner` (`{execution.get('runner')}`).",
            f"Hand `{RESOLVED_FILE}` to that runner and require it to honor every rule above,",
            "including the human final gate. See the appendix in the skill's SKILL.md.",
            "",
        ]
    if resolved.get("privacy", {}).get("egress"):
        out += [
            "## External judge egress",
            "",
            "This spec sends artifacts to an external judge. Before the first send: apply the",
            "redaction globs, scrub secret patterns from the artifact CONTENT (not just",
            "filenames), and get explicit consent from the human. Log every send.",
            "",
        ]
    return "\n".join(out)


# ---------- html dashboard ----------

def parse_notes(path: Path) -> dict[str, str]:
    """Split implementation-notes.md into the four contract sections."""
    sections = {name: "" for name, _ in NOTE_SECTIONS}
    if not path.exists():
        return sections
    current = None
    buffer: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            if current:
                sections[current] = "\n".join(buffer).strip()
            buffer = []
            current = next((name for name, _ in NOTE_SECTIONS if name in line), None)
            continue
        if current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


CSS = """
:root { color-scheme: light dark; --fg:#16181d; --bg:#fbfbfa; --muted:#6b7280;
  --line:#e3e3e0; --card:#fff; --ok:#0f7b46; --bad:#b4232c; --warn:#8a5a00; }
@media (prefers-color-scheme: dark) { :root { --fg:#e8e8e6; --bg:#16181d;
  --muted:#9aa0aa; --line:#2c3038; --card:#1d2027; --ok:#4ade80; --bad:#f87171; --warn:#fbbf24; } }
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
  font:15px/1.6 ui-sans-serif,-apple-system,Segoe UI,Roboto,"Noto Sans TC",sans-serif; }
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
h2 { font-size:1rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);
  margin:2.5rem 0 .75rem; font-weight:600; }
.sub { color:var(--muted); margin:0 0 1.5rem; }
.chips { display:flex; flex-wrap:wrap; gap:.5rem; }
.chip { border:1px solid var(--line); background:var(--card); border-radius:999px;
  padding:.3rem .85rem; font-size:.85rem; }
.chip b { font-weight:600; }
.chip.bad { border-color:var(--bad); color:var(--bad); }
.card { border:1px solid var(--line); background:var(--card); border-radius:.6rem;
  padding:1rem 1.15rem; margin-bottom:.85rem; }
.card h3 { margin:0 0 .5rem; font-size:.95rem; }
.card pre { margin:0; white-space:pre-wrap; word-break:break-word; font:inherit; color:var(--fg); }
.card.flag { border-left:4px solid var(--warn); }
.empty { color:var(--muted); font-style:italic; }
table { border-collapse:collapse; width:100%; font-size:.9rem; }
th,td { text-align:left; padding:.5rem .6rem; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; }
code { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:.9em; }
.pass { color:var(--ok); font-weight:600; }
.fail { color:var(--bad); font-weight:600; }
.unknown { color:var(--muted); }
.wrap { overflow-x:auto; }
"""

# meta.lang chrome strings for loop.html. Missing/unknown meta.lang -> "en"
# (zero behavior change for existing loops). cap_report()'s own strings
# (iteration/budget/no-progress chips) are shared with `check`'s terminal
# output and stay English in both languages -- only the labels render_html
# itself owns are translated here.
GATE_GLOSS_ZH = {"plan_gate": "計劃閘", "delivery_gate": "交付閘", FINAL_GATE: "終閘"}

LABELS: dict[str, dict[str, Any]] = {
    "en": {
        "html_lang": "en",
        "chip_iteration": "iteration",
        "chip_gate": "gate",
        "gate_not_started": "not started",
        "stop_prefix": "STOP: ",
        "open_q_suffix": " — for the human to rule on",
        "open_q_empty": "None raised yet.",
        "verdict_history_heading": "Verdict history",
        "th_num": "#", "th_gate": "gate", "th_verdict": "verdict",
        "th_fault": "fault", "th_issues": "blocking issues",
        "verdict_empty": "Not started. Nothing has run yet.",
        "verification_heading": "Verification criteria",
        "th_criterion": "criterion", "th_type": "type", "th_checks": "what it checks",
        "mark_pass": "PASS", "mark_fail": "FAIL", "mark_unknown": "—",
        "notes_heading": "Implementation notes",
        "notes_empty": "The builder has not written any notes yet.",
        "note_glosses": dict(NOTE_SECTIONS),
    },
    "zh": {
        "html_lang": "zh-HK",
        "chip_iteration": "輪",
        "chip_gate": "閘",
        "gate_not_started": "未開波",
        "stop_prefix": "停：",
        "open_q_suffix": "——等人類拍板",
        "open_q_empty": "未有提出。",
        "verdict_history_heading": "判決紀錄",
        "th_num": "#", "th_gate": "閘", "th_verdict": "判決",
        "th_fault": "責任", "th_issues": "阻塞問題",
        "verdict_empty": "未開波，未跑過任何嘢。",
        "verification_heading": "驗證準則",
        "th_criterion": "準則", "th_type": "類型", "th_checks": "驗咩",
        "mark_pass": "PASS", "mark_fail": "FAIL", "mark_unknown": "—",
        "notes_heading": "實作筆記",
        "notes_empty": "builder 仲未寫低筆記。",
        "note_glosses": {
            "設計決策": "spec 冇講嘅位，點解咁揀",
            "偏離情況": "刻意偏離 spec 嘅位，附埋原因",
            "價值取捨": "諗過嘅方案，點解揀呢個",
            OPEN_QUESTIONS: "要俾人類拍板嘅問題",
        },
    },
}


def resolve_lang(resolved: dict[str, Any]) -> str:
    lang = resolved.get("meta", {}).get("lang")
    return lang if lang in LABELS else "en"


def gate_display(gate_id: str, lang: str) -> str:
    """Gate ids stay code-style (plan_gate/delivery_gate/final_gate); zh adds a gloss."""
    if not gate_id:
        return ""
    gloss = GATE_GLOSS_ZH.get(gate_id)
    return f"{gate_id}（{gloss}）" if lang == "zh" and gloss else gate_id


def render_html(resolved: dict[str, Any], state: dict[str, Any], notes: dict[str, str]) -> str:
    esc = html.escape
    meta = resolved.get("meta", {})
    control = resolved.get("loop_control", {})
    iterations = state.get("iterations", [])
    blockers, remaining = cap_report(resolved, state)
    last = iterations[-1] if iterations else {}
    lang = resolve_lang(resolved)
    L = LABELS[lang]

    parts = [
        "<!doctype html>",
        f'<html lang="{L["html_lang"]}"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{esc(str(meta.get('name', 'LoopForge loop')))}</title>",
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>{esc(str(meta.get('name', 'LoopForge loop')))}</h1>",
        f"<p class=\"sub\">{esc(str(meta.get('description', '')))}</p>",
        '<div class="chips">',
        f'<span class="chip">{esc(L["chip_iteration"])} <b>{len(iterations)}</b> / {esc(str(control.get("max_iterations")))}</span>',
        f'<span class="chip">{esc(L["chip_gate"])} <b>'
        f'{esc(gate_display(str(last.get("gate", "")), lang) or L["gate_not_started"])}</b></span>',
    ]
    for line in remaining:
        parts.append(f'<span class="chip">{esc(line)}</span>')
    for blocker in blockers:
        parts.append(f'<span class="chip bad">{esc(L["stop_prefix"])}{esc(blocker)}</span>')
    parts.append("</div>")

    open_q = notes.get(OPEN_QUESTIONS, "").strip()
    parts.append(f"<h2>{esc(OPEN_QUESTIONS)}{esc(L['open_q_suffix'])}</h2>")
    parts.append(
        f'<div class="card flag"><pre>{esc(open_q)}</pre></div>'
        if open_q
        else f'<p class="empty">{esc(L["open_q_empty"])}</p>'
    )

    parts.append(f"<h2>{esc(L['verdict_history_heading'])}</h2>")
    if iterations:
        rows = [
            '<div class="wrap"><table><tr>'
            f"<th>{esc(L['th_num'])}</th><th>{esc(L['th_gate'])}</th><th>{esc(L['th_verdict'])}</th>"
            f"<th>{esc(L['th_fault'])}</th><th>{esc(L['th_issues'])}</th></tr>"
        ]
        for index, record in enumerate(iterations, 1):
            verdict = str(record.get("verdict", "?"))
            cls = "pass" if verdict == "pass" else "fail"
            issues = "<br>".join(esc(str(i)) for i in record.get("blocking_issues", [])) or "—"
            rows.append(
                f"<tr><td>{esc(str(record.get('n', index)))}</td>"
                f"<td><code>{esc(gate_display(str(record.get('gate', '')), lang))}</code></td>"
                f'<td class="{cls}">{esc(verdict)}</td><td>{esc(str(record.get("fault_source", "—")))}</td>'
                f"<td>{issues}</td></tr>"
            )
        parts.append("".join(rows) + "</table></div>")
    else:
        parts.append(f'<p class="empty">{esc(L["verdict_empty"])}</p>')

    parts.append(f"<h2>{esc(L['verification_heading'])}</h2>")
    latest: dict[str, str] = {}
    for record in iterations:
        results = record.get("criteria")
        if isinstance(results, dict):
            latest.update({str(k): str(v) for k, v in results.items()})
    rows = [
        '<div class="wrap"><table><tr>'
        f"<th></th><th>{esc(L['th_criterion'])}</th><th>{esc(L['th_type'])}</th><th>{esc(L['th_checks'])}</th></tr>"
    ]
    for item in resolved.get("goal", {}).get("verification", []):
        status = latest.get(item["id"], "")
        mark, cls = {"pass": (L["mark_pass"], "pass"), "fail": (L["mark_fail"], "fail")}.get(
            status, (L["mark_unknown"], "unknown")
        )
        detail = item.get("rubric") or item.get("prompt") or " ".join(item.get("check", []))
        rows.append(
            f'<tr><td class="{cls}">{esc(mark)}</td><td><code>{esc(item["id"])}</code></td>'
            f"<td>{esc(item['type'])}</td><td>{esc(str(detail).strip())}</td></tr>"
        )
    parts.append("".join(rows) + "</table></div>")

    parts.append(f"<h2>{esc(L['notes_heading'])}</h2>")
    wrote_any = False
    glosses = L["note_glosses"]
    for name, en_gloss in NOTE_SECTIONS:
        if name == OPEN_QUESTIONS:
            continue
        body = notes.get(name, "").strip()
        if not body:
            continue
        wrote_any = True
        gloss = glosses.get(name, en_gloss)
        parts.append(
            f'<div class="card"><h3>{esc(name)} <span class="empty">— {esc(gloss)}</span></h3>'
            f"<pre>{esc(body)}</pre></div>"
        )
    if not wrote_any:
        parts.append(f'<p class="empty">{esc(L["notes_empty"])}</p>')

    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"


# ---------- commands ----------

def cmd_compile(args) -> int:
    source = args.spec.resolve()
    resolved = normalize_spec(load_yaml(source), source)
    out = args.out or source.with_name(RESOLVED_FILE)
    write_json(out, resolved)
    print(f"Wrote {out}")
    for path, renderer in ((args.plan or source.with_name("PLAN.md"), render_plan),
                           (args.run or source.with_name("RUN.md"), render_run)):
        write_text(path, renderer(resolved))
        print(f"Wrote {path}")
    return 0


def cmd_check(args) -> int:
    directory = args.dir.resolve()
    resolved = load_resolved(directory)
    state = load_state(directory, resolved)
    blockers, remaining = cap_report(resolved, state)
    if blockers:
        print("STOP — do not open another iteration:")
        for blocker in blockers:
            print(f"  - {blocker}")
        return 1
    print(f"GO — iteration {len(state.get('iterations', [])) + 1} is allowed")
    for line in remaining:
        print(f"  {line}")
    return 0


def cmd_render(args) -> int:
    directory = args.dir.resolve()
    resolved = load_resolved(directory)
    state = load_state(directory, resolved)
    observ = resolved.get("observability", {})
    notes = parse_notes(resolve_in(directory, observ.get("notes_file", NOTES_FILE), "notes_file"))
    out = args.out or resolve_in(directory, observ.get("dashboard", DASHBOARD_FILE), "dashboard")
    write_text(out, render_html(resolved, state, notes))
    print(f"Wrote {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loopforge", description="LoopForge compiler (design-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compile", help="Compile SPEC.yaml -> loop.resolved.json + PLAN.md + RUN.md")
    c.add_argument("spec", type=Path)
    c.add_argument("--out", type=Path, help=f"default: <spec dir>/{RESOLVED_FILE}")
    c.add_argument("--plan", type=Path, help="default: <spec dir>/PLAN.md")
    c.add_argument("--run", type=Path, help="default: <spec dir>/RUN.md")
    c.set_defaults(func=cmd_compile)

    k = sub.add_parser("check", help="May the loop open another iteration? exit 0 = yes")
    k.add_argument("dir", type=Path)
    k.set_defaults(func=cmd_check)

    r = sub.add_parser("render", help=f"Render {DASHBOARD_FILE} from the spec + state")
    r.add_argument("dir", type=Path)
    r.add_argument("--out", type=Path)
    r.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except LoopForgeError as exc:
        print(f"loopforge: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
