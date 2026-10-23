# GCC leave, leave salary, sick leave, gratuity and payment advice

How HR Suite handles these for Saudi Arabia, Bahrain, Oman, UAE, Qatar and Kuwait, driven by **Country Config**. Values are the legal defaults as of September 2026; confirm them with the client's legal adviser before go-live.

## One policy, many countries
Set `Company.country` (or an Employee's Work Country). Everything below reads that country's **Country Config**:

| Section | Holds |
|---|---|
| Annual Leave Policy | Entitlement bands by service (leave days and leave-salary days a year), wait before leave can be taken, carry-forward |
| Leave Salary Settlement | Minimum earned salary days (30), minimum service (365 days), whether the settlement pays the worked days |
| Sick Leave Policy | Days a year, pay tiers in order, eligibility, medical certificate |
| Gratuity Policy | Accrual slabs, resignation factors, cap, minimum service, wage base, scheme cut-off, dismissal forfeiture |

An **Employee** shows the policy that applies (read-only) and an optional override block: leave days and salary days a year, 2-year cycle, air ticket.

## Three switches, all off on existing sites
A new site starts with all three on. An existing Country Config is **never** switched automatically.

| Switch (Country Config / Hr Suite Settings) | Turn on when |
|---|---|
| Leave Accrual Engine = HR Suite Ledger | Opening balances are imported |
| Split Sick Leave Into Pay Tiers Automatically | The site does not already model sick pay as separate part-pay Leave Types (it would be reduced twice) |
| Route Expense Claims Through A Payment Advice | Approvers are set in Hr Suite Settings |

## Go-live order for the ledger engine
1. Set up Country Config bands and the leave-salary settings; check the Employee override block for anyone on a company option.
2. Import each employee's balance at a **month end** as a Leave Accrual Ledger **Opening** row (Data Import; `hr_suite/data/leave_opening_balance_template.csv`). Leave days post into the HRMS allocation; salary days stay in the ledger.
3. Set **Leave Accrual Engine = HR Suite Ledger**. Accrual runs 03:00 on the 1st for the month just ended and catches up missed months.
4. Create **Leave Salary Settlement** from each approved annual Leave Application on the last working day.
5. Month-end payroll: the leave days (and the worked days, when the settlement paid them) are already kept out by Additional Salary deductions.

Only users with the **HR Leave Override** role can approve annual leave beyond the balance, before the waiting period, or pay leave salary below the barrier.

## Gratuity
One slab-driven engine for every country except India (Gratuity Act). Qualifying service = days to the exit (or the scheme cut-off) less unpaid leave and absence, over 365. Exit types: Resignation, Termination, Dismissal, Partial Settlement (accrued to date, employee not marked Left).

## HR Payment Advice
Every payment outside payroll: Draft -> Pending Approval (level 1 -> level 2) -> Approved -> Sent to Finance -> Paid, or Rejected back to HR. HR sanctions amounts (never above the claim); Finance pays the sanctioned total. Approvers per company in Hr Suite Settings; a company with none keeps "submit is the approval". HR does no accounting.

## Reports
Leave and Salary Days Balance, Leave Accrual Ledger Report, Leave Salary Settlements Due, Gratuity Liability, HR Payment Advice Queue.

## Not built / open
- 2-year leave cycle is stored on the Employee but does not change accrual or eligibility yet.
- A late return inside the leave balance needs HR to record the extension Leave Application by hand.
- `send_sick_leave_threshold_alerts` (tasks.py) still reads the legacy Saudi-only Sick Leave document.
- Spec open points to settle with each client: part-month accrual basis (default: over 30), whether unearned salary days on advance leave are paid as they accrue (default: yes), 2-year-cycle employees, ticket amounts and frequency, KSA/UAE/Qatar/Kuwait carry-forward caps, Bahrain SIO coverage of pre-March-2024 expats.
