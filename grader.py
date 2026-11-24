"""Deterministic grading: no human, no LLM judge."""


def _eq(a, b, tol):
    if isinstance(b, bool) or isinstance(a, bool):
        return a is b if isinstance(a, bool) else str(a).strip().lower() == str(b).lower()
    if isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) <= tol + 1e-9
        except (TypeError, ValueError):
            return False
    return str(a).strip().upper() == str(b).strip().upper()


def grade(task, answer):
    """Returns (passed: bool, partial: float in [0,1], detail: str)."""
    truth = task["solver"]()
    if task["kind"] == "list":
        got = {str(x).strip() for x in answer} if isinstance(answer, list) else set()
        exp = set(truth)
        union = got | exp
        partial = len(got & exp) / len(union) if union else 1.0
        return got == exp, partial, f"missing={sorted(exp - got)} extra={sorted(got - exp)}"
    if not isinstance(answer, dict):
        return False, 0.0, "answer is not an object"
    answer = {str(k).strip(): v for k, v in answer.items()}
    keys = set(truth) | set(answer)
    ok = [k for k in keys if k in truth and k in answer and _eq(answer[k], truth[k], task["tol"])]
    wrong = sorted(k for k in keys if k not in ok)
    detail = "; ".join(f"{k}: got {answer.get(k, '—')} want {truth.get(k, '—')}" for k in wrong[:6])
    return len(ok) == len(keys), (len(ok) / len(keys) if keys else 1.0), detail
