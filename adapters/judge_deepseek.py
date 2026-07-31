#!/usr/bin/env python3
"""LoopForge DeepSeek judge adapter — OPTIONAL cross-family judge.

The DEFAULT judge in LoopForge is a fresh same-family subagent, which needs no
adapter and sends nothing off the machine. Use this one only when a delivery is
high-stakes enough that a same-family blind spot is a real risk, and accept that
it costs money and crosses a vendor boundary (see the privacy contract in
references/council-rubric.md).

Contract (argv + stdin, so any runner can call it):
  - Reads the full judge prompt from STDIN.
  - Calls DeepSeek (OpenAI-compatible chat completions).
  - Prints exactly one fenced JSON verdict block to STDOUT:
        {"verdict": "pass"|"revise", "blocking_issues": [...],
         "confidence": 0.0-1.0, "notes": "..."}
  - ALWAYS exits 0. A network/API failure degrades to a `revise` verdict
    carrying warning="adapter_error" instead of killing the loop: a non-zero
    model exit that aborts the whole run is a worse failure than a bad verdict.

Hardening baked in:
  - truststore.inject_into_ssl() before any TLS (survives a TLS-inspecting
    antivirus / corporate MITM proxy).
  - transient 429 / 5xx / timeout -> retry with exponential backoff.
  - secret scrub on the outbound prompt: real content redaction, not just
    matching globs against filenames.
  - stdin read as BYTES + UTF-8 decode, so the adapter never depends on the
    host's locale codepage.
  - mojibake guard: CJK mangled to `????` by a re-encoding shell pipe is refused
    with warning="mojibake_input" instead of being judged as garbage. Invoke
    through a byte-transparent pipe; on Windows that means Git Bash, not a
    PowerShell 5.1 `|`.
  - verdict consistency: "revise" with zero actionable blocking issues gets
    ONE re-ask; still inconsistent -> warning="verdict_inconsistent" so the
    orchestrator logs a bad judge call instead of burning a revision.
  - usage passthrough: verdict carries {"usage": {...}} so USD/token budget
    caps are enforceable, not advisory.

Usage:
  echo "<judge prompt>" | py -3 judge_deepseek.py     (POSIX: python3)
  py -3 judge_deepseek.py --selftest     # offline check of the pure logic
Env:
  DEEPSEEK_API_KEY   required
  DEEPSEEK_MODEL     default deepseek-chat
  LOOPFORGE_JUDGE_RETRIES   default 4
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

try:
    import truststore  # type: ignore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - adapter must never die on import
    pass

API_URL = "https://api.deepseek.com/chat/completions"
PASS = "pass"
REVISE = "revise"

# Outbound secret scrub. Applied to the prompt before it leaves the machine.
SCRUB_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]

SYSTEM_PROMPT = (
    "You are the LoopForge judge. Apply the given criteria to the artifact "
    "strictly. Return ONLY a fenced ```json code block with keys: verdict "
    '("pass" or "revise"), blocking_issues (array of short strings), '
    "confidence (0.0-1.0), notes (one short string). No prose outside the "
    "block. Each blocking issue MUST start with [a short quote of the "
    "criterion it violates]; an issue that cannot cite a criterion is "
    "advisory and belongs in notes, not blocking_issues. A revise verdict "
    "MUST carry at least one blocking issue; if nothing blocks, the verdict "
    "is pass. Default to revise when uncertain."
)

# A re-encoding shell pipe turns CJK into literal `?`; runs of 4+ never occur
# in real prompts. Seen live: a judge received all-`??` text and graded it anyway.
MOJIBAKE = re.compile(r"\?{4,}")

# "Blocking" issues that actually say nothing blocks — the verdict-field/body
# contradiction: the verdict field said revise, the body said all-acceptable.
BENIGN_ISSUE = re.compile(
    r"(?i)^\W*(no (blocking )?issues?|acceptable|criteria met|meets? (the )?criteria|none)\b"
)

RECONSIDER = (
    "\n\nREMINDER: your previous verdict was internally inconsistent - verdict "
    'was "revise" but no blocking issue cited a violated criterion. '
    "Re-evaluate once: if nothing actually blocks, return pass; otherwise each "
    "blocking issue must start with [the criterion it violates]."
)


def inconsistent(verdict: dict) -> bool:
    """revise-with-no-actionable-issue = the judge contradicted itself."""
    if verdict.get("warning") or verdict.get("verdict") != REVISE:
        return False
    issues = [str(issue).strip() for issue in verdict.get("blocking_issues", [])]
    return not [i for i in issues if i and not BENIGN_ISSUE.match(i)]


def scrub(text: str) -> str:
    for pattern in SCRUB_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def fence(verdict: dict) -> str:
    return "```json\n" + json.dumps(verdict, ensure_ascii=False, indent=2) + "\n```"


def degraded(reason: str, detail: str = "", warning: str = "adapter_error") -> dict:
    return {
        "verdict": REVISE,
        "blocking_issues": [f"Judge unavailable: {reason}"],
        "confidence": 0.0,
        "notes": detail[:400],
        "warning": warning,
    }


def call_deepseek(prompt: str) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return degraded("DEEPSEEK_API_KEY not set")

    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    retries = int(os.environ.get("LOOPFORGE_JUDGE_RETRIES", "4"))
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": scrub(prompt)},
            ],
            "temperature": 0.0,
            "stream": False,
        }
    ).encode("utf-8")

    last = ""
    for attempt in range(retries):
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            verdict = parse_verdict(content)
            usage = payload.get("usage")
            if isinstance(usage, dict):
                verdict["usage"] = {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                }
            return verdict
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            transient = exc.code == 429 or 500 <= exc.code < 600
            if not transient:
                return degraded(last, exc.read().decode("utf-8", "ignore"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = str(exc)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return degraded("bad response shape", str(exc))
        time.sleep(min(2 ** attempt, 30))
    return degraded("retries exhausted", last)


def parse_verdict(content: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    candidate = match.group(1) if match else content.strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {
            "verdict": REVISE,
            "blocking_issues": ["Judge output was not parseable JSON."],
            "confidence": 0.0,
            "notes": content.strip()[:400],
            "warning": "unparseable_judge_output",
        }
    if not isinstance(parsed, dict):
        parsed = {}
    # A judge that returns the right keys with the wrong types is still a bad
    # judge call, not a crash: coerce, then let the caller see a revise verdict.
    issues = parsed.get("blocking_issues")
    parsed["blocking_issues"] = issues if isinstance(issues, list) else ([] if issues is None else [str(issues)])
    if parsed.get("verdict") not in {PASS, REVISE}:
        parsed["verdict"] = REVISE
        parsed["blocking_issues"].append("Judge verdict missing or invalid.")
    parsed.setdefault("confidence", 0.0)
    parsed.setdefault("notes", "")
    return parsed


def selftest() -> int:
    ok = parse_verdict('```json\n{"verdict": "pass", "blocking_issues": []}\n```')
    assert ok["verdict"] == PASS
    bad = parse_verdict("not json at all")
    assert bad["verdict"] == REVISE and bad["warning"] == "unparseable_judge_output"
    assert parse_verdict('```json\n{"verdict": "maybe"}\n```')["verdict"] == REVISE
    # Right keys, wrong types: coerced, never a crash.
    weird = parse_verdict('```json\n{"verdict": "maybe", "blocking_issues": "just one"}\n```')
    assert weird["blocking_issues"][0] == "just one" and weird["verdict"] == REVISE
    assert parse_verdict("```json\n[1, 2]\n```")["verdict"] == REVISE
    assert MOJIBAKE.search("normalize + URL dedup ????????")
    assert not MOJIBAKE.search("what? really? sure?")
    assert inconsistent({"verdict": REVISE, "blocking_issues": []})
    assert inconsistent({"verdict": REVISE, "blocking_issues": ["No issues found. Criteria met"]})
    assert not inconsistent({"verdict": REVISE, "blocking_issues": ["[has-five] only 4 items"]})
    assert not inconsistent({"verdict": PASS, "blocking_issues": []})
    assert not inconsistent(degraded("x"))
    print("selftest ok")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    # Bytes + explicit UTF-8: never trust the locale codepage (cp950).
    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if not prompt.strip():
        print(fence(degraded("empty prompt on stdin")))
        return 0
    if MOJIBAKE.search(prompt):
        print(fence(degraded(
            "mojibake on stdin (`????` runs) - refusing to judge mangled text; "
            "invoke via a byte-transparent pipe (Git Bash), not PowerShell 5.1",
            warning="mojibake_input",
        )))
        return 0
    verdict = call_deepseek(prompt)
    if inconsistent(verdict):
        verdict = call_deepseek(prompt + RECONSIDER)
        if inconsistent(verdict):
            verdict["warning"] = "verdict_inconsistent"
    print(fence(verdict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
