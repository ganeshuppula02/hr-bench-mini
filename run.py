"""Run agents on HR-Bench Mini and report pass@1 and pass^k.

Examples:
  python -m hrbench.run --agent oracle                  # sanity check: must score 100%
  python -m hrbench.run --agent gemini --model gemini-3.8-flash -k 3
  python -m hrbench.run --agent gemini --model gemini-3.8-flash -k 3 --allow-python
  python -m hrbench.run --agent claude -k 3                      # Claude Opus 5.5 (needs ANTHROPIC_API_KEY)
  python -m hrbench.run --agent claude --model claude-haiku-5-5 -k 3
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .grader import grade
from .tasks import TASKS, WORLD

RESULTS = Path(__file__).resolve().parent.parent / "results"
MAX_STEPS = 15
OBS_LIMIT = 12000

SYSTEM = """You are an HR operations agent at Nimbus Labs. You work inside a folder of company files.
Use tools to inspect the files, then submit a final answer. Follow policy.md exactly.

Reply with exactly ONE JSON object per turn, one of:
  {"action": "list_files"}
  {"action": "read_file", "path": "<file name>"}
  {PYTHON}{"action": "submit", "answer": <answer in the requested format>}

You only get one submit. Be precise: every value is checked automatically."""
PY_LINE = '{"action": "run_python", "code": "<python code; files are in the current directory; print() results>"}\n  '


# ----------------------------------------------------------------- tools
def tool(action, allow_python):
    a = action.get("action")
    if a == "list_files":
        return "\n".join(sorted(p.name for p in WORLD.iterdir()))
    if a == "read_file":
        p = (WORLD / str(action.get("path", ""))).resolve()
        if p.parent != WORLD or not p.exists():
            return "ERROR: file not found"
        return p.read_text()
    if a == "run_python" and allow_python:
        with tempfile.TemporaryDirectory() as tmp:
            for f in WORLD.iterdir():
                (Path(tmp) / f.name).write_bytes(f.read_bytes())
            try:
                r = subprocess.run([sys.executable, "-I", "-c", str(action.get("code", ""))], cwd=tmp,
                                   capture_output=True, text=True, timeout=30)
                return (r.stdout + r.stderr) or "(no output)"
            except subprocess.TimeoutExpired:
                return "ERROR: timed out after 30s"
    return f"ERROR: unknown action {a!r}"


# ----------------------------------------------------------------- agents
def gemini_call(model, system, history):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": history,
            "generationConfig": {"responseMimeType": "application/json"}}
    key = os.environ.get("GEMINI_API_KEY", "proxy-injected")
    for attempt in range(8):
        r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt * 3))
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"].get("parts", [])
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    raise RuntimeError(f"Gemini kept failing: {r.status_code} {r.text[:200]}")


def run_gemini(task, model, allow_python):
    system = SYSTEM.replace("{PYTHON}", PY_LINE if allow_python else "")
    history = [{"role": "user", "parts": [{"text": "TASK: " + task["prompt"]}]}]
    for step in range(MAX_STEPS):
        text = gemini_call(model, system, history)
        history.append({"role": "model", "parts": [{"text": text}]})
        try:
            action = json.loads(text)
            if isinstance(action, list):
                action = action[0]
        except (json.JSONDecodeError, IndexError):
            obs = "ERROR: reply was not a single JSON object"
        else:
            if action.get("action") == "submit":
                return action.get("answer"), step + 1
            obs = tool(action, allow_python)
        history.append({"role": "user", "parts": [{"text": "OBSERVATION:\n" + obs[:OBS_LIMIT]}]})
    return None, MAX_STEPS


def parse_action(text):
    """Extract the first JSON object from a reply (Claude may add a sentence around it)."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in reply")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj


_claude_client = None


def run_claude(task, model, allow_python, effort):
    import anthropic  # imported lazily so Gemini/oracle runs don't need the package
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(max_retries=6)  # reads ANTHROPIC_API_KEY
    system = SYSTEM.replace("{PYTHON}", PY_LINE if allow_python else "")
    messages = [{"role": "user", "content": "TASK: " + task["prompt"]}]
    for step in range(MAX_STEPS):
        resp = _claude_client.messages.create(
            model=model, max_tokens=16000, system=system, messages=messages,
            output_config={"effort": effort},
        )
        if resp.stop_reason == "refusal":
            # No fallback model on purpose: a benchmark must measure the model it names.
            raise RuntimeError(f"refusal: {resp.stop_details}")
        # Pass the full content back unchanged (keeps thinking blocks valid for the next turn).
        messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            action = parse_action(text)
        except ValueError:
            obs = "ERROR: reply must contain exactly one JSON object"
        else:
            if action.get("action") == "submit":
                return action.get("answer"), step + 1
            obs = tool(action, allow_python)
        messages.append({"role": "user", "content": "OBSERVATION:\n" + obs[:OBS_LIMIT]})
    return None, MAX_STEPS


def run_one(agent, task, model, allow_python, effort="high"):
    t0 = time.time()
    try:
        if agent == "oracle":
            answer, steps = task["solver"](), 0
        elif agent == "empty":
            answer, steps = {}, 0
        elif agent == "claude":
            answer, steps = run_claude(task, model, allow_python, effort)
        else:
            answer, steps = run_gemini(task, model, allow_python)
        err = None
    except Exception as e:  # count infrastructure errors as failures but record them
        answer, steps, err = None, 0, repr(e)[:300]
    passed, partial, detail = grade(task, answer)
    return dict(task=task["id"], passed=passed, partial=round(partial, 3), steps=steps,
                seconds=round(time.time() - t0, 1), detail=detail, error=err, answer=answer)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["oracle", "empty", "gemini", "claude"], default="oracle")
    ap.add_argument("--model", help="default: claude-opus-5-5 for claude, gemini-3.8-flash for gemini")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Claude effort level (default high)")
    ap.add_argument("-k", type=int, default=1, help="runs per task (for pass^k)")
    ap.add_argument("--allow-python", action="store_true", help="give the agent a run_python tool")
    ap.add_argument("--tasks", help="comma-separated task id prefixes, e.g. T01,T07")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if not args.model:
        args.model = "claude-opus-5-5" if args.agent == "claude" else "gemini-3.8-flash"

    tasks = [t for t in TASKS if not args.tasks or any(t["id"].startswith(p) for p in args.tasks.split(","))]
    jobs = [(t, i) for t in tasks for i in range(args.k)]
    with ThreadPoolExecutor(args.workers) as ex:
        runs = list(ex.map(lambda j: run_one(args.agent, j[0], args.model, args.allow_python, args.effort), jobs))

    label = args.agent if args.agent in ("oracle", "empty") else f"{args.model}{'+python' if args.allow_python else ''}"
    if args.agent == "claude":
        label += f"-{args.effort}"
    print(f"\nHR-Bench Mini — {label} — k={args.k}\n")
    # API/infrastructure failures are excluded from scores (they say nothing about the model).
    # pass^k is only reported when all k runs of a task actually completed.
    print(f"{'task':28} {'diff':7} {'runs':>5} {'pass@1':>7} {'pass^k':>7} {'partial':>8}")
    rows = []
    for t in tasks:
        rs = [r for r in runs if r["task"] == t["id"] and not r["error"]]
        if not rs:
            print(f"{t['id']:28} {t['difficulty']:7} {0:>5} {'n/a':>7} {'n/a':>7} {'n/a':>8}")
            continue
        p1 = sum(r["passed"] for r in rs) / len(rs)
        pk = all(r["passed"] for r in rs) if len(rs) == args.k else None
        part = sum(r["partial"] for r in rs) / len(rs)
        rows.append((p1, pk, part))
        pk_s = "n/a" if pk is None else ("✓" if pk else "✗")
        print(f"{t['id']:28} {t['difficulty']:7} {len(rs):>5} {p1:7.0%} {pk_s:>7} {part:8.0%}")
    if rows:
        n = len(rows)
        full = [r[1] for r in rows if r[1] is not None]
        pk_all = f"{sum(full)/len(full):7.0%}" if full else f"{'n/a':>7}"
        print(f"\n{'OVERALL (scored tasks: ' + str(n) + ')':42} {sum(r[0] for r in rows)/n:7.0%} {pk_all} {sum(r[2] for r in rows)/n:8.0%}")
    errs = [r for r in runs if r["error"]]
    if errs:
        print(f"\n{len(errs)}/{len(runs)} run(s) excluded due to API/infrastructure errors, e.g. {errs[0]['error'][:160]}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{label.replace('/', '_')}_k{args.k}.json"
    out.write_text(json.dumps(dict(label=label, k=args.k, runs=runs), indent=1, default=str))
    print(f"\nFull transcripts of answers + grading details: {out}")


if __name__ == "__main__":
    main()
