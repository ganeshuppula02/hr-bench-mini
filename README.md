# HR-Bench Mini

A small, **automatically verifiable** benchmark for AI agents doing HR & payroll work.

Most knowledge-work evals are one-shot tasks graded by humans or LLM judges. Coding evals are different:
the agent works in a repo and tests decide pass/fail. HR-Bench Mini tries the coding recipe on HR:

| Coding benchmark | HR-Bench Mini |
|---|---|
| A repository | A fictional company "world": employees, leave log, timesheets, expense claims, policy |
| Unit tests | Reference solvers that recompute the right answer from the data + a deterministic grader |
| Agent edits files over many steps | Agent explores files (and optionally runs Python) over up to 15 steps |
| pass@1 | pass@1 **and** pass^k (did it succeed on *every* one of k runs — reliability) |

## Tasks (10)

| ID | What the agent must do | Traps planted in the data |
|---|---|---|
| T01 | Headcount by department on a date | exit *on* the date still counts; future joiner doesn't |
| T02 | Find duplicate rows in a new-hire import | email in different case/spaces, PAN in lowercase, same name but not a duplicate |
| T03 | Annual leave balance | carry-forward cap, join on the 1st vs mid-month, rejected/cancelled leave, December leave after as-of date, negative balance |
| T04 | Net pay | LOP from October vs November, rejected LOP, PF cap, PT threshold |
| T05 | Weekly overtime | managers not eligible, multiple weeks in file |
| T06 | Expense audit with reason codes | rule precedence (a claim breaking 3 rules), boundary at exactly 60 days / ₹500 / ₹2000 |
| T07 | Approve/reject leave requests | submission order ≠ ID order, notice boundary, 2-per-team cap incl. LOP, rejected requests don't consume capacity |
| T08 | Full & final settlement | exit on the 30th, leave balance on the exit date |
| T09 | Parental leave eligibility | 79 vs 80 days of service, employee exits before due date |
| T10 | Total payroll for the month | long aggregation over everyone; one error anywhere fails it |

Answers are compared exactly (₹1 tolerance on money). No human, no LLM judge.

## Run it

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python -m hrbench.generate_world            # rebuild world/ from seed 42
python -m hrbench.run --agent oracle         # sanity check -> must be 100%
python -m hrbench.run --agent gemini --model gemini-3.8-flash -k 3
python -m hrbench.run --agent gemini --model gemini-3.8-flash -k 3 --allow-python
python -m hrbench.run --agent claude -k 3                         # Claude Opus 5.5
python -m hrbench.run --agent claude --model claude-haiku-5-5 -k 3
```

Set `GEMINI_API_KEY` to run Gemini models, or `ANTHROPIC_API_KEY` to run Claude models (`--effort low|medium|high|xhigh|max`, default high). Results (every answer + why it failed) go to `results/`.
`--allow-python` executes model-written code locally (in a temp copy of `world/`, 30s timeout) — only use it on a machine you're fine with that on.

## Results

**Preliminary — one small model, incomplete run.** `gemini-3.5-flash-lite`, file tools only (no Python), k=3, Nov 2026.
18 of 30 runs completed; 12 were lost to API timeouts/quota limits and are **excluded**, not counted as failures.

| Task | Completed runs | pass@1 | Avg. partial credit |
|---|---|---|---|
| T01 headcount | 3 | 0% | 25% |
| T02 dedupe import | 3 | 33% | 83% |
| T03 leave balance | 2 | 0% | 25% |
| T04 net pay | 3 | 0% | 0% |
| T05 overtime | 2 | 0% | 0% |
| T06 expense audit | 3 | 0% | 37% |
| T07 leave approvals | 2 | 0% | 54% |
| T08–T10 | 0 | n/a | n/a |
| **Scored tasks (7)** | | **5%** | **32%** |

pass^3 (passes all 3 runs): 0 of the 4 tasks with 3 completed runs.

Typical mistakes seen in the logs:
- Marked a claim submitted **exactly** 60 days later as late (policy says *more than* 60) — in all 3 runs.
- Marked a ₹650 meal claim submitted after 59 days as `LATE` instead of `MEAL_CAP` (miscounted days).
- Approved a 3rd person off in the same team on the same day, and a request with only 2 days' notice.
- Missed a duplicate new hire who had a different name but the same email as an existing employee (2 of 3 runs).

Not yet run: the `--allow-python` setting, stronger models, and a complete k=3 pass. Treat these numbers as a demo of the harness, not a model ranking.

## Limitations (honest)

- 10 tasks, 1 fictional company, 1 seed — a toy, not a leaderboard.
- The policy is simplified and fictional; it is **not** Indian labour law or real payroll rules.
- Tasks have a single correct answer. Real HR work also has judgment calls (e.g. how to word a rejection), which this does not measure.
- Reference solvers were hand-checked on a few cases, but a bug in a solver is a bug in the benchmark — issues welcome.

## Next steps

- Randomise the world per run (new seed → new answers) so models can't memorise it.
- Add multi-turn tasks where requirements change mid-task ("the CFO just changed the policy").
- Add "write" tasks graded on final state (e.g. agent must update `leave_log.csv` correctly).
- Add checklist-graded judgment tasks (an employee-facing email) next to the exact-match ones.

## Credits

Built by Ganesh Uppula (B.Tech CSE, AI & ML) with help from Claude (Anthropic). Licensed under MIT.
