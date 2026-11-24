# Nimbus Labs — HR & Payroll Policy (FY 2026)

Nimbus Labs is a fictional company. All amounts are in INR (₹). All dates are YYYY-MM-DD.

## 1. Employment status
- An employee's `exit_date` is their **last working day**. They are still active on that day.
- An employee is **active on date D** if `join_date <= D` and (`exit_date` is empty or `exit_date >= D`).

## 2. Monthly pay
- **HRA** = 40% of `monthly_basic`.
- **Gross** = `monthly_basic` + HRA + `special_allowance`.
- **LOP deduction** = Gross / 30 × (number of approved `LOP` leave days whose start date falls in the month).
- **PF (employee share)** = 12% of `monthly_basic`, where basic is capped at ₹15,000 for PF purposes (so PF is at most ₹1,800). PF is computed on the full basic, not reduced for LOP.
- **Professional Tax (PT)** = ₹200 if Gross > ₹21,000, otherwise ₹0.
- **Net pay** = Gross − LOP deduction − PF − PT. Round to the nearest rupee only at the end.

## 3. Overtime
- Only grades `L1` and `L2` are eligible. Grade `M` (managers) never receive overtime.
- Hourly rate = `monthly_basic` / 176.
- Overtime pay for a week = (hours worked − 40, if positive) × 1.5 × hourly rate. Round to the nearest rupee per employee.

## 4. Annual leave
- Accrual: **1.5 days** for each calendar month of 2026 whose 1st day is on or before the as-of date **and** on which the employee was employed (`join_date <= 1st of month`). Joining exactly on the 1st counts.
- Carry forward: `al_carry_2025` days are brought from 2025, **capped at 5**.
- Balance on date D = carry forward + accrued − days of `ANNUAL` leave with status `APPROVED` whose start date is in 2026 and on or before D.
- Leave with status `REJECTED` or `CANCELLED` never counts.

## 5. Leave request approval
Process pending requests in order of `submitted_at` (earliest first). For each request:
1. **Notice rule:** the start date must be at least 3 calendar days after the date part of `submitted_at` (start − submitted date >= 3). Otherwise → `REJECTED`.
2. **Staffing rule:** a team may have at most 2 people on leave on any calendar day. Count people from the same `team` who are on leave that day — leave in `leave_log.csv` with status `APPROVED` (any type), plus requests already approved earlier in this batch. If, on any day of the request, that count is already 2 → `REJECTED`.
3. Otherwise → `APPROVED`.
Leave ranges are inclusive and use calendar days.

## 6. Expense claims
Check rules in this order and report the **first** rule broken:
1. `NOT_EMPLOYEE` — the employee has an `exit_date` and the expense date is after it.
2. `LATE` — submitted more than 60 days after the expense date (submitted − expense > 60).
3. `MEAL_CAP` — category `MEAL` and amount > ₹500.
4. `NO_RECEIPT` — amount > ₹2,000 and `receipt` is `N`.
A claim breaking none of these is approved.

## 7. Full & final settlement (exits)
For an employee exiting in a month:
- Pro-rated pay = Gross × (day of month of `exit_date`) / 30.
- Leave encashment = max(annual leave balance on the exit date, 0) × `monthly_basic` / 30.
- Settlement = pro-rated pay + leave encashment. No deductions. Round to the nearest rupee at the end.

## 8. Parental leave eligibility
An employee is eligible if (`expected_date` − `join_date`) >= 80 days **and** they are active on `expected_date`.

## 9. New-hire import de-duplication
An imported row is a duplicate of an existing employee if its PAN matches (case-insensitive, ignore surrounding spaces) **or** its email matches (case-insensitive, ignore surrounding spaces). Names are not used for matching.
