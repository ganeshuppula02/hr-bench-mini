"""Generate the Nimbus Labs world (CSV files) deterministically from a seed.

Usage: python -m hrbench.generate_world [--seed 42]
"""
import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

WORLD = Path(__file__).resolve().parent.parent / "world"

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Vikram", "Isha", "Arjun", "Priya",
         "Karthik", "Sneha", "Rahul", "Lakshmi", "Nikhil", "Pooja", "Siddharth", "Kavya", "Aditya",
         "Divya", "Harish", "Nandini", "Manoj", "Swathi", "Varun", "Revathi", "Gautam", "Shalini",
         "Pranav", "Tanvi", "Suresh", "Aishwarya"]
LAST = ["Iyer", "Reddy", "Sharma", "Nair", "Menon", "Rao", "Gupta", "Pillai", "Das", "Kumar",
        "Joshi", "Patel", "Krishnan", "Bose", "Verma", "Shetty"]
TEAMS = {
    "Engineering": ["Platform", "Mobile", "Data"],
    "Sales": ["Enterprise", "SMB"],
    "Operations": ["Support", "Finance"],
    "People": ["HR"],
}


def write_csv(name, header, rows):
    with open(WORLD / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def rand_pan(rng):
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(rng.choice(L) for _ in range(5)) + "".join(rng.choice("0123456789") for _ in range(4)) + rng.choice(L)


def d(s):
    return date.fromisoformat(s)


def main(seed=42):
    rng = random.Random(seed)
    WORLD.mkdir(exist_ok=True)

    # ---------------- employees ----------------
    employees = []
    names = rng.sample([f"{a} {b}" for a in FIRST for b in LAST], 32)
    team_list = [(dep, t) for dep, ts in TEAMS.items() for t in ts]
    for i, name in enumerate(names, start=1):
        dep, team = team_list[i % len(team_list)]
        grade = "M" if i % 7 == 0 else rng.choice(["L1", "L2"])
        basic = {"L1": rng.randrange(12000, 30000, 500), "L2": rng.randrange(30000, 60000, 500),
                 "M": rng.randrange(60000, 110000, 1000)}[grade]
        special = rng.randrange(2000, 20000, 500)
        join = date(2019, 1, 1) + timedelta(days=rng.randrange(0, 2400))
        carry = rng.choice([0, 2, 3.5, 5, 6, 8, 12]) if join < date(2026, 1, 1) else 0
        employees.append(dict(emp_id=f"E{i:03d}", name=name,
                              email=name.lower().replace(" ", ".") + "@nimbuslabs.example",
                              pan=rand_pan(rng), dept=dep, team=team, grade=grade,
                              join_date=join.isoformat(), exit_date="", monthly_basic=basic,
                              special_allowance=special, al_carry_2025=carry))

    # Hand-placed edge cases (the "traps")
    employees[2]["join_date"] = "2026-03-01"; employees[2]["al_carry_2025"] = 0     # joined on 1st -> March counts
    employees[5]["join_date"] = "2026-06-15"; employees[5]["al_carry_2025"] = 0     # mid-month joiner
    employees[8]["exit_date"] = "2026-11-18"                                         # Nov exit
    employees[11]["exit_date"] = "2026-11-30"                                        # exits on as-of date -> still active
    employees[14]["exit_date"] = "2026-09-30"                                        # old exit
    employees[17]["join_date"] = "2026-12-07"; employees[17]["al_carry_2025"] = 0   # future joiner
    employees[20]["exit_date"] = "2026-11-07"                                        # Nov exit
    employees[23]["join_date"] = "2026-10-20"; employees[23]["al_carry_2025"] = 0   # recent joiner
    employees[4]["monthly_basic"] = 13000; employees[4]["grade"] = "L1"               # PF below cap
    employees[4]["special_allowance"] = 1500                                          # gross <= 21000 -> no PT

    cols = list(employees[0].keys())
    write_csv("employees.csv", cols, [[e[c] for c in cols] for e in employees])
    emp = {e["emp_id"]: e for e in employees}

    def active_on(e, day):
        return d(e["join_date"]) <= day and (not e["exit_date"] or d(e["exit_date"]) >= day)

    # ---------------- leave log ----------------
    leave = []
    lid = 1
    for e in employees:
        if d(e["join_date"]) > date(2026, 11, 1):
            continue
        for _ in range(rng.randint(1, 4)):
            m = rng.randint(1, 12)
            start = date(2026, m, rng.randint(1, 24))
            if start < d(e["join_date"]) or (e["exit_date"] and start > d(e["exit_date"])):
                continue
            days = rng.randint(1, 4)
            typ = rng.choices(["ANNUAL", "SICK", "LOP"], [6, 2, 1])[0]
            status = rng.choices(["APPROVED", "REJECTED", "CANCELLED"], [8, 1, 1])[0]
            leave.append([f"L{lid:04d}", e["emp_id"], typ, start.isoformat(),
                          (start + timedelta(days=days - 1)).isoformat(), days, status])
            lid += 1
    # Guarantee some November LOP for payroll tasks (and a rejected LOP distractor)
    for eid, start, days, status in [("E001", "2026-11-10", 2, "APPROVED"), ("E005", "2026-11-03", 3, "APPROVED"),
                                     ("E013", "2026-11-20", 1, "APPROVED"), ("E013", "2026-11-24", 2, "REJECTED"),
                                     ("E007", "2026-10-29", 3, "APPROVED")]:
        s = d(start)
        leave.append([f"L{lid:04d}", eid, "LOP", start, (s + timedelta(days=days - 1)).isoformat(), days, status])
        lid += 1
    # December approved leave that collides with pending requests (staffing rule)
    for eid, start, end in [("E002", "2026-12-14", "2026-12-18"), ("E012", "2026-12-15", "2026-12-16")]:
        leave.append([f"L{lid:04d}", eid, "ANNUAL", start, end, (d(end) - d(start)).days + 1, "APPROVED"])
        lid += 1
    write_csv("leave_log.csv", ["leave_id", "emp_id", "type", "start", "end", "days", "status"], leave)

    # ---------------- timesheets ----------------
    ts = []
    for wk in ["2026-11-09", "2026-11-16", "2026-11-23"]:
        for e in employees:
            if active_on(e, d(wk)):
                ts.append([e["emp_id"], wk, rng.choice([32, 38, 40, 40, 42, 45, 47.5, 50, 52])])
    write_csv("timesheets.csv", ["emp_id", "week_start", "hours"], ts)

    # ---------------- expense claims ----------------
    claims = []
    for c in range(1, 31):
        e = rng.choice(employees[:17])
        cat = rng.choice(["MEAL", "TRAVEL", "HOTEL", "OTHER"])
        amt = {"MEAL": rng.choice([320, 480, 500, 650, 900]), "TRAVEL": rng.choice([800, 1999, 2000, 2400, 5600]),
               "HOTEL": rng.choice([1800, 3200, 7400]), "OTHER": rng.choice([250, 1200, 2600])}[cat]
        exp = date(2026, 8, 1) + timedelta(days=rng.randrange(0, 100))
        sub = exp + timedelta(days=rng.choice([1, 5, 20, 59, 60, 61, 75]))
        claims.append([f"C{c:03d}", e["emp_id"], cat, exp.isoformat(), sub.isoformat(), amt, rng.choice(["Y", "Y", "N"])])
    # Explicit trap: claim by exited employee after exit, which is ALSO late & over meal cap
    claims.append(["C031", "E015", "MEAL", "2026-10-05", "2026-12-20", 700, "N"])
    write_csv("expense_claims.csv", ["claim_id", "emp_id", "category", "expense_date", "submitted_date", "amount", "receipt"], claims)

    # ---------------- leave requests (pending, for December) ----------------
    reqs = []
    # Hand-designed so each request exercises a specific rule (see README "Traps").
    sched = [
        ("R01", "E008", "2026-12-15", "2026-12-17", "2026-12-01T09:10:00"),  # Platform
        ("R02", "E016", "2026-12-16", "2026-12-16", "2026-12-01T09:05:00"),  # Platform, submitted before R01
        ("R03", "E024", "2026-12-16", "2026-12-16", "2026-12-02T11:00:00"),  # Platform: 3rd person on 12-16 -> reject
        ("R04", "E001", "2026-12-04", "2026-12-05", "2026-12-02T17:45:00"),  # only 2 days notice -> reject
        ("R05", "E010", "2026-12-17", "2026-12-17", "2026-12-02T08:00:00"),  # Data: E002 already off -> 2nd ok
        ("R06", "E003", "2026-12-19", "2026-12-20", "2026-12-03T10:00:00"),  # Enterprise: with E019 (log) -> ok
        ("R07", "E011", "2026-12-19", "2026-12-19", "2026-12-03T10:30:00"),  # Enterprise: 3rd on 12-19 -> reject
        ("R08", "E005", "2026-12-07", "2026-12-08", "2026-12-04T23:59:00"),  # exactly 3 days notice -> ok
        ("R09", "E023", "2026-12-18", "2026-12-18", "2026-12-04T12:01:00"),  # HR: E007 on LOP -> 2nd ok
        ("R10", "E031", "2026-12-18", "2026-12-18", "2026-12-04T12:02:00"),  # HR: 3rd (LOP counts) -> reject
        ("R11", "E032", "2026-12-16", "2026-12-16", "2026-12-05T09:00:00"),  # Platform: R03 was rejected, still 2 -> reject
        ("R12", "E026", "2026-12-17", "2026-12-18", "2026-12-05T09:30:00"),  # Data: 12-17 has E002+E010 -> reject
        ("R13", "E027", "2026-12-20", "2026-12-20", "2026-12-05T10:00:00"),  # Enterprise: only E003 on 12-20 -> ok
        ("R14", "E032", "2026-12-14", "2026-12-14", "2026-12-05T11:00:00"),  # Platform: nobody on 12-14 -> ok
    ]
    for rid, eid, s, en, sub in sched:
        reqs.append([rid, eid, s, en, sub])
    write_csv("leave_requests.csv", ["req_id", "emp_id", "start", "end", "submitted_at"], reqs)

    # ---------------- parental leave requests ----------------
    par = [["P01", "E003", "2026-12-20"], ["P02", "E024", "2027-01-05"], ["P03", "E024", "2027-01-10"],
           ["P04", "E010", "2027-02-01"], ["P05", "E012", "2026-12-28"], ["P06", "E006", "2026-09-02"],
           ["P07", "E006", "2026-09-03"], ["P08", "E018", "2027-03-15"]]
    write_csv("parental_requests.csv", ["req_id", "emp_id", "expected_date"], par)

    # ---------------- new-hire import ----------------
    imp = [
        ["N01", "Rhea Kapoor", "rhea.kapoor@nimbuslabs.example", rand_pan(rng)],
        ["N02", employees[6]["name"], "  " + employees[6]["email"].upper() + " ", rand_pan(rng)],   # email dup (case/space)
        ["N03", "A. " + employees[9]["name"].split()[1], "new.person@nimbuslabs.example", employees[9]["pan"].lower()],  # PAN dup
        ["N04", employees[15]["name"], "different.mail@nimbuslabs.example", rand_pan(rng)],  # same name, NOT a dup
        ["N05", "Farhan Ali", "farhan.ali@nimbuslabs.example", rand_pan(rng)],
        ["N06", "Zoya Khan", employees[21]["email"], rand_pan(rng)],                          # email dup
        ["N07", "Ishaan Mehta", "ishaan.mehta@nimbuslabs.example", " " + employees[26]["pan"] + " "],  # PAN dup with spaces
    ]
    write_csv("new_hires_import.csv", ["import_id", "name", "email", "pan"], imp)
    print(f"World written to {WORLD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    main(ap.parse_args().seed)
