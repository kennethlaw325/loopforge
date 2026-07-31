#!/usr/bin/env python3
"""Runnable check for loopforge.py. stdlib unittest, no framework, no fixtures.

  py -3 scripts/test_loopforge.py        (POSIX: python3 scripts/test_loopforge.py)
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep __pycache__ out of the skill package
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loopforge as lf  # noqa: E402

import yaml  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "SPEC.yaml"


def valid_spec() -> dict:
    return copy.deepcopy(yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")))


def run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = lf.main(argv)
    return code, buf.getvalue()


class TempSpec:
    """Write a spec dict to a temp dir and compile it there."""

    def __init__(self, spec: dict):
        self.dir = Path(tempfile.mkdtemp(prefix="loopforge-test-"))
        self.spec_path = self.dir / "SPEC.yaml"
        self.spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")

    def compile(self) -> tuple[int, str]:
        return run(["compile", str(self.spec_path)])

    def write_state(self, state: dict) -> None:
        (self.dir / lf.STATE_FILE).write_text(json.dumps(state), encoding="utf-8")


class CompileHappyPath(unittest.TestCase):
    def test_bundled_template_compiles_to_three_artifacts(self):
        env = TempSpec(valid_spec())
        code, out = env.compile()
        self.assertEqual(code, 0, out)
        resolved = json.loads((env.dir / lf.RESOLVED_FILE).read_text(encoding="utf-8"))
        self.assertEqual(resolved["gates"]["final_gate"]["verdict_source"], "human")
        self.assertTrue((env.dir / "PLAN.md").read_text(encoding="utf-8").startswith("# PLAN"))
        run_md = (env.dir / "RUN.md").read_text(encoding="utf-8")
        self.assertIn("orchestrator", run_md)
        self.assertIn("開放式問題", run_md)  # human-checkpoint agenda is wired
        self.assertIn("check", run_md)

    def test_external_judge_shorthand_resolves_to_adapter_argv(self):
        spec = valid_spec()
        spec["council"].append({"id": "judge-ext", "role": "judge", "judge": "deepseek"})
        env = TempSpec(spec)
        self.assertEqual(env.compile()[0], 0)
        resolved = json.loads((env.dir / lf.RESOLVED_FILE).read_text(encoding="utf-8"))
        argv = resolved["council_by_id"]["judge-ext"]["invoke"]
        self.assertTrue(argv[-1].endswith("judge_deepseek.py"), argv)


class CompileRejects(unittest.TestCase):
    def assert_rejected(self, spec: dict, *needles: str):
        code, out = TempSpec(spec).compile()
        self.assertEqual(code, 2, f"expected reject, got 0:\n{out}")
        for needle in needles:
            self.assertIn(needle, out)

    def test_final_gate_verdict_source_must_be_human(self):
        spec = valid_spec()
        spec["gates"]["final_gate"]["verdict_source"] = "judge-1"
        self.assert_rejected(spec, "final_gate.verdict_source must be `human`")

    def test_reviewer_cannot_be_a_verdict_source(self):
        spec = valid_spec()
        spec["council"].append({"id": "reviewer-1", "role": "reviewer"})
        spec["gates"]["delivery_gate"]["members"] = ["reviewer-1"]
        spec["gates"]["delivery_gate"]["verdict_source"] = "reviewer-1"
        self.assert_rejected(spec, "reviewers write notes, only a judge writes a verdict")

    def test_missing_cap_is_rejected(self):
        for path, needle in (
            (("loop_control", "max_iterations"), "max_iterations is a required cap"),
            (("loop_control", "budget"), "budget is a required cap"),
            (("loop_control", "no_progress"), "no_progress is a required cap"),
        ):
            spec = valid_spec()
            del spec[path[0]][path[1]]
            with self.subTest(cap=path[1]):
                self.assert_rejected(spec, needle)
        spec = valid_spec()
        del spec["gates"]["delivery_gate"]["max_revisions"]
        self.assert_rejected(spec, "delivery_gate.max_revisions is a required cap")

    def test_fixed_passes_over_no_progress_window_is_rejected(self):
        spec = valid_spec()
        spec["gates"]["delivery_gate"]["verdict_policy"] = "fixed_passes"
        spec["gates"]["delivery_gate"]["max_revisions"] = 5  # window is 2
        self.assert_rejected(spec, "exceeds the no-progress window",
                             "stops the loop before the gate can proceed")

    def test_builder_may_not_sit_on_a_gate(self):
        spec = valid_spec()
        spec["gates"]["delivery_gate"]["members"] = ["builder", "judge-1"]
        self.assert_rejected(spec, "may not grade its own work")

    def test_unknown_gate_name_is_rejected(self):
        spec = valid_spec()
        spec["gates"]["ship_gate"] = dict(spec["gates"]["delivery_gate"])
        self.assert_rejected(spec, "Unknown gate(s): ship_gate", "rejected here rather than silently dropped")

    def test_a_fake_gate_cannot_smuggle_a_builder_verdict_source(self):
        # The invariants only run on the known gates, so an extra gate would
        # otherwise carry `verdict_source: builder` straight into the output.
        spec = valid_spec()
        spec["gates"]["delivery_gate_2"] = {"verdict_policy": "revise_until_clean",
                                            "verdict_source": "builder", "max_revisions": 9,
                                            "criteria": ["does-not-exist"]}
        self.assert_rejected(spec, "Unknown gate(s): delivery_gate_2")

    def test_fixed_passes_verdict_source_must_exist(self):
        spec = valid_spec()
        spec["gates"]["delivery_gate"]["verdict_policy"] = "fixed_passes"
        spec["gates"]["delivery_gate"]["max_revisions"] = 2
        spec["gates"]["delivery_gate"]["verdict_source"] = "judge-typo"
        self.assert_rejected(spec, "names `judge-typo`, which is not a council member id or `human`")

    def test_reviewer_may_be_a_fixed_passes_verdict_source(self):
        spec = valid_spec()
        spec["council"].append({"id": "reviewer-1", "role": "reviewer"})
        spec["gates"]["delivery_gate"].update(verdict_policy="fixed_passes", max_revisions=2,
                                              verdict_source="reviewer-1", members=["reviewer-1"])
        code, out = TempSpec(spec).compile()
        self.assertEqual(code, 0, out)

    def test_builder_may_not_be_a_verdict_source_under_any_policy(self):
        for policy in ("revise_until_clean", "fixed_passes"):
            spec = valid_spec()
            spec["gates"]["delivery_gate"].update(verdict_policy=policy, max_revisions=2,
                                                  verdict_source="builder")
            with self.subTest(policy=policy):
                self.assert_rejected(spec, "may not grade its own work")

    def test_council_without_a_builder_is_rejected(self):
        spec = valid_spec()
        spec["council"] = [m for m in spec["council"] if m["role"] != "builder"]
        self.assert_rejected(spec, "at least one `builder`")


class CheckCommand(unittest.TestCase):
    def setUp(self):
        self.env = TempSpec(valid_spec())
        self.assertEqual(self.env.compile()[0], 0)

    def test_no_state_file_counts_as_iteration_zero(self):
        self.assertFalse((self.env.dir / lf.STATE_FILE).exists())
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 0, out)
        self.assertIn("iteration 1 is allowed", out)

    def test_under_cap_is_allowed(self):
        self.env.write_state({"iterations": [{"n": 1, "verdict": "revise", "signature": "a"}],
                              "gate_revisions": {"delivery_gate": 1},
                              "spend": {"wall_clock_min": 5}})
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 0, out)
        self.assertIn("1/8 used", out)

    def test_at_cap_stops_the_loop(self):
        self.env.write_state({"iterations": [{"n": i, "verdict": "revise", "signature": f"s{i}"}
                                             for i in range(1, 9)]})
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 1, out)
        self.assertIn("max_iterations reached (8/8)", out)

    def test_budget_cap_stops_the_loop(self):
        self.env.write_state({"iterations": [], "spend": {"wall_clock_min": 45}})
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 1, out)
        self.assertIn("budget cap wall_clock_min", out)

    def test_repeated_signature_trips_no_progress(self):
        same = "[followable] step 3 assumes a value the doc never names"
        self.env.write_state({"iterations": [
            {"n": 1, "verdict": "revise", "blocking_issues": [same]},
            {"n": 2, "verdict": "revise", "blocking_issues": [same.upper() + "   "]},
        ]})
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 1, out)
        self.assertIn("no progress", out)

    def test_custom_state_file_name_is_honored(self):
        spec = valid_spec()
        spec.setdefault("observability", {})["state_file"] = "my-state.json"
        env = TempSpec(spec)
        self.assertEqual(env.compile()[0], 0)
        (env.dir / "my-state.json").write_text(
            json.dumps({"iterations": [{"n": i} for i in range(1, 9)]}), encoding="utf-8")
        # The default name must be ignored entirely, not merged in.
        (env.dir / lf.STATE_FILE).write_text(json.dumps({"iterations": []}), encoding="utf-8")
        code, out = run(["check", str(env.dir)])
        self.assertEqual(code, 1, out)
        self.assertIn("max_iterations reached (8/8)", out)

    def test_spec_may_not_write_outside_the_loop_directory(self):
        for field, value in (("dashboard", str(Path(tempfile.gettempdir()) / "pwned.html")),
                             ("dashboard", "../pwned.html"),
                             ("state_file", "../../state.json")):
            spec = valid_spec()
            spec.setdefault("observability", {})[field] = value
            env = TempSpec(spec)
            self.assertEqual(env.compile()[0], 0)
            with self.subTest(field=field, value=value):
                code, out = run(["render", str(env.dir)])
                self.assertEqual(code, 2, out)
                self.assertIn("resolves outside", out)
                self.assertFalse(Path(value).is_absolute() and Path(value).exists())

    def test_malformed_resolved_json_gives_a_clean_error_not_a_traceback(self):
        path = self.env.dir / lf.RESOLVED_FILE
        resolved = json.loads(path.read_text(encoding="utf-8"))
        resolved["loop_control"]["max_iterations"] = "eight"
        path.write_text(json.dumps(resolved), encoding="utf-8")
        for command in ("check", "render"):
            with self.subTest(command=command):
                code, out = run([command, str(self.env.dir)])
                self.assertEqual(code, 2, out)
                self.assertIn("max_iterations must be a number, got str", out)
                self.assertNotIn("Traceback", out)

    def test_malformed_state_gives_a_clean_error_not_a_traceback(self):
        self.env.write_state({"iterations": ["oops, a string"]})
        for command in ("check", "render"):
            with self.subTest(command=command):
                code, out = run([command, str(self.env.dir)])
                self.assertEqual(code, 2, out)
                self.assertIn("iterations[0] must be an object, got str", out)
                self.assertNotIn("Traceback", out)

    def test_exhausted_gate_quota_stops_the_loop(self):
        self.env.write_state({"iterations": [], "gate_revisions": {"delivery_gate": 3}})
        code, out = run(["check", str(self.env.dir)])
        self.assertEqual(code, 1, out)
        self.assertIn("escalate to a human", out)


class RenderCommand(unittest.TestCase):
    def setUp(self):
        self.env = TempSpec(valid_spec())
        self.assertEqual(self.env.compile()[0], 0)

    def read_html(self) -> str:
        code, out = run(["render", str(self.env.dir)])
        self.assertEqual(code, 0, out)
        return (self.env.dir / lf.DASHBOARD_FILE).read_text(encoding="utf-8")

    def assert_self_contained(self, page: str):
        self.assertTrue(page.startswith("<!doctype html>"))
        for forbidden in ("http://", "https://", "<script", "src=", "@import"):
            self.assertNotIn(forbidden, page, f"page is not self-contained: {forbidden}")

    def test_renders_before_the_loop_starts(self):
        page = self.read_html()
        self.assert_self_contained(page)
        self.assertIn("Not started", page)
        self.assertIn("None raised yet", page)

    def test_renders_state_notes_and_criteria(self):
        self.env.write_state({
            "iterations": [
                {"n": 1, "gate": "delivery_gate", "verdict": "revise", "fault_source": "executor",
                 "blocking_issues": ["[structure] Troubleshooting section missing"],
                 "criteria": {"structure": "fail", "followable": "pass"}},
                {"n": 2, "gate": "delivery_gate", "verdict": "pass",
                 "criteria": {"structure": "pass", "followable": "pass"}},
            ],
            "gate_revisions": {"delivery_gate": 1},
            "spend": {"wall_clock_min": 12},
        })
        (self.env.dir / lf.NOTES_FILE).write_text(
            "# implementation-notes\n"
            "## 設計決策 (Design decisions)\nUsed uv, not pip: the repo already pins uv.\n"
            "## 偏離情況\nSkipped the Windows path section.\n"
            "## 價值取捨\nConsidered a Makefile; a doc is closer to what was asked.\n"
            "## 開放式問題\nShould the quickstart cover Docker?\n",
            encoding="utf-8",
        )
        page = self.read_html()
        self.assert_self_contained(page)
        self.assertIn("Should the quickstart cover Docker?", page)
        self.assertIn("Troubleshooting section missing", page)
        self.assertIn("Used uv, not pip", page)
        self.assertIn("iteration <b>2</b>", page)

    def test_html_escapes_every_state_supplied_field(self):
        payload = "<b onmouseover=alert(1)>pwn</b>"  # no `src=`/`<script`: those trip the self-contained check
        self.env.write_state({"iterations": [
            {"n": payload, "gate": payload, "verdict": payload, "fault_source": payload,
             "blocking_issues": [payload]}]})
        page = self.read_html()
        self.assert_self_contained(page)
        self.assertNotIn(payload, page)
        # 5 row fields, plus the gate name again in the header chips.
        self.assertGreaterEqual(page.count("&lt;b onmouseover=alert(1)&gt;pwn&lt;/b&gt;"), 5)

    def test_html_escapes_note_content(self):
        (self.env.dir / lf.NOTES_FILE).write_text(
            "## 開放式問題\n<script>alert(1)</script>\n", encoding="utf-8"
        )
        self.assert_self_contained(self.read_html())


class NoteParsing(unittest.TestCase):
    def test_headings_match_by_substring_and_missing_file_is_empty(self):
        directory = Path(tempfile.mkdtemp(prefix="loopforge-test-"))
        self.assertEqual(lf.parse_notes(directory / "nope.md")[lf.OPEN_QUESTIONS], "")
        path = directory / lf.NOTES_FILE
        path.write_text("## 開放式問題 (Open questions)\nq1\n## 價值取捨\nt1\n", encoding="utf-8")
        parsed = lf.parse_notes(path)
        self.assertEqual(parsed[lf.OPEN_QUESTIONS], "q1")
        self.assertEqual(parsed["價值取捨"], "t1")
        self.assertEqual(parsed["設計決策"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
