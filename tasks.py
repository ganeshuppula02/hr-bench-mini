"""Task definitions + reference solvers. Ground truth is computed from the world files,
so if the world changes, the answers change with it (no hand-written answer keys)."""
import csv
from datetime import date
from pathlib import Path

WORLD = Path(__file__).resolve().parent.parent / "world"
ASOF = date(2026, 11, 30)


def load(name):
    with open(WORLD / name) as f:
        return list(csv.DictReader(f))


def d(s):
    return date.fromisoformat(s.strip()) if s and s.strip() else None


def emps():
    return {e["emp_id"]: e for e in load("employees.csv")}


def active_on(e, day):
    return d(e["join_date"]) <= day and (d(e["exit_date"]) is None or d(e["exit_date"]) >= day)


def gross(e):
    b = float(e["monthly_basic"])
    return b + 0.4 * b + float(e["special_allowance"])


def al_balance(e, day):
    join = d(e["join_date"])
    months = sum(1 for m in range(1, 13)
                 if date(2026, m, 1) <= day and join <= date(2026, m, 1))
    carry = min(float(e["al_carry_2025"]), 5)
    taken = sum(float(l["days"]) for l in load("leave_log.csv")
                if l["emp_id"] == e["emp_id"] and l["type"] == "ANNUAL" and l["status"] == "APPROVED"
                and d(l["start"]).year == 2026 and d(l["start"]) <= day)
    return carry + 1.5 * months - taken


def net_pay_nov(e):
    g = gross(e)
    lop = sum(float(l["days"]) for l in load("leave_log.csv")
              if l["emp_id"] == e["emp_id"] and l["type"] == "LOP" and l["status"] == "APPROVED"
              and d(l["start"]).year == 2026 and d(l["start"]).month == 11)
    pf = 0.12 * min(float(e["monthly_basic"]), 15000)
    pt = 200 if g > 21000 else 0
    return round(g - g / 30 * lop - pf - pt)


# ---------------------------------------------------------------- solvers
def t01_headcount():
    out = {}
    for e in emps().values():
        if active_on(e, ASOF):
            out[e["dept"]] = out.get(e["dept"], 0) + 1
    return out


def t02_duplicates():
    E = emps().values()
    pans = {e["pan"].strip().upper() for e in E}
    mails = {e["email"].strip().lower() for e in E}
    return sorted(r["import_id"] for r in load("new_hires_import.csv")
                  if r["pan"].strip().upper() in pans or r["email"].strip().lower() in mails)


T03_IDS = ["E003", "E006", "E010", "E024"]
def t03_leave_balance():
    E = emps()
    return {i: al_balance(E[i], ASOF) for i in T03_IDS}


T04_IDS = ["E001", "E005", "E013"]
def t04_net_pay():
    E = emps()
    return {i: net_pay_nov(E[i]) for i in T04_IDS}


def t05_overtime():
    E = emps()
    out = {}
    for r in load("timesheets.csv"):
        if r["week_start"] != "2026-11-16":
            continue
        e = E[r["emp_id"]]
        h = float(r["hours"])
        if e["grade"] in ("L1", "L2") and h > 40:
            out[e["emp_id"]] = round((h - 40) * 1.5 * float(e["monthly_basic"]) / 176)
    return out


def t06_expenses():
    E = emps()
    out = {}
    for c in load("expense_claims.csv"):
        e = E[c["emp_id"]]
        exp, sub, amt = d(c["expense_date"]), d(c["submitted_date"]), float(c["amount"])
        if d(e["exit_date"]) and exp > d(e["exit_date"]):
            out[c["claim_id"]] = "NOT_EMPLOYEE"
        elif (sub - exp).days > 60:
            out[c["claim_id"]] = "LATE"
        elif c["category"] == "MEAL" and amt > 500:
            out[c["claim_id"]] = "MEAL_CAP"
        elif amt > 2000 and c["receipt"] == "N":
            out[c["claim_id"]] = "NO_RECEIPT"
    return out


def _days(s, e):
    s, e = d(s), d(e)
    return [date.fromordinal(o) for o in range(s.toordinal(), e.toordinal() + 1)]


def t07_leave_requests():
    E = emps()
    busy = {}  # (team, day) -> set(emp)
    for l in load("leave_log.csv"):
        if l["status"] == "APPROVED":
            for day in _days(l["start"], l["end"]):
                busy.setdefault((E[l["emp_id"]]["team"], day), set()).add(l["emp_id"])
    out = {}
    for r in sorted(load("leave_requests.csv"), key=lambda r: r["submitted_at"]):
        team = E[r["emp_id"]]["team"]
        days = _days(r["start"], r["end"])
        if (d(r["start"]) - date.fromisoformat(r["submitted_at"][:10])).days < 3:
            out[r["req_id"]] = "REJECTED"
        elif any(len(busy.get((team, day), set())) >= 2 for day in days):
            out[r["req_id"]] = "REJECTED"
        else:
            out[r["req_id"]] = "APPROVED"
            for day in days:
                busy.setdefault((team, day), set()).add(r["emp_id"])
    return out


def t08_settlement():
    out = {}
    for e in emps().values():
        x = d(e["exit_date"])
        if x and x.year == 2026 and x.month == 11:
            pro = gross(e) * x.day / 30
            enc = max(al_balance(e, x), 0) * float(e["monthly_basic"]) / 30
            out[e["emp_id"]] = round(pro + enc)
    return out


def t09_parental():
    E = emps()
    out = {}
    for r in load("parental_requests.csv"):
        e, exp = E[r["emp_id"]], d(r["expected_date"])
        out[r["req_id"]] = (exp - d(e["join_date"])).days >= 80 and active_on(e, exp)
    return out


def t10_total_payroll():
    return {"total_net_pay": sum(net_pay_nov(e) for e in emps().values()
                                 if not e["exit_date"] and d(e["join_date"]) <= date(2026, 11, 1))}


# ---------------------------------------------------------------- task list
# kind: "dict" (all keys must match), "list" (set equality). tol: numeric tolerance in ₹/days.
TASKS = [
    dict(id="T01_headcount", difficulty="easy", kind="dict", tol=0, solver=t01_headcount,
         prompt="Report the active headcount per department as of 2026-11-30. "
                'Answer format: {"<dept>": <count>, ...} including only departments with at least one active employee.'),
    dict(id="T02_dedupe_import", difficulty="easy", kind="list", tol=0, solver=t02_duplicates,
         prompt="new_hires_import.csv is about to be loaded into the HRIS. Which import rows are duplicates of existing employees? "
                'Answer format: ["<import_id>", ...]'),
    dict(id="T03_leave_balance", difficulty="medium", kind="dict", tol=0.01, solver=t03_leave_balance,
         prompt=f"What is the annual leave balance (in days) as of 2026-11-30 for employees {', '.join(T03_IDS)}? "
                'Answer format: {"<emp_id>": <days>, ...}'),
    dict(id="T04_net_pay", difficulty="medium", kind="dict", tol=1, solver=t04_net_pay,
         prompt=f"Compute November 2026 net pay for employees {', '.join(T04_IDS)}. "
                'Answer format: {"<emp_id>": <rupees>, ...}'),
    dict(id="T05_overtime", difficulty="medium", kind="dict", tol=1, solver=t05_overtime,
         prompt="Compute overtime pay for the week starting 2026-11-16 for every employee who earned any. "
                'Answer format: {"<emp_id>": <rupees>, ...} (omit employees with zero overtime pay).'),
    dict(id="T06_expense_audit", difficulty="medium", kind="dict", tol=0, solver=t06_expenses,
         prompt="Audit expense_claims.csv against policy. List every claim that must be rejected with the reason code. "
                'Answer format: {"<claim_id>": "<REASON_CODE>", ...} (omit approved claims).'),
    dict(id="T07_leave_approvals", difficulty="hard", kind="dict", tol=0, solver=t07_leave_requests,
         prompt="Process all pending requests in leave_requests.csv according to policy section 5. "
                'Answer format: {"<req_id>": "APPROVED" | "REJECTED", ...}'),
    dict(id="T08_final_settlement", difficulty="hard", kind="dict", tol=1, solver=t08_settlement,
         prompt="Compute the full & final settlement for every employee whose exit date is in November 2026. "
                'Answer format: {"<emp_id>": <rupees>, ...}'),
    dict(id="T09_parental_eligibility", difficulty="medium", kind="dict", tol=0, solver=t09_parental,
         prompt="For each row in parental_requests.csv decide whether the employee is eligible for parental leave. "
                'Answer format: {"<req_id>": true | false, ...}'),
    dict(id="T10_total_payroll", difficulty="hard", kind="dict", tol=1, solver=t10_total_payroll,
         prompt="Finance needs the total November 2026 net pay for all employees who have no exit date and joined on or before 2026-11-01. "
                'Answer format: {"total_net_pay": <rupees>}'),
]
