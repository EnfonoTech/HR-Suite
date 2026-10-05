# Leave opening balances (go-live import)

The Leave Accrual Ledger accrues from go-live onwards, so every employee's balance at that
date is imported once as an **Opening** row.

1. **Date it at a month end** (the last day of the month before the first accrual). Accrual
   resumes the month AFTER the date, so a mid-month date loses the rest of that month.
2. In Data Import, choose **Leave Accrual Ledger → Insert New Records** and upload
   `leave_opening_balance_template.csv`. Columns:
   - `Employee` - the Employee ID.
   - `Source` - always `Opening`.
   - `Period End / As Of` - the go-live date, `YYYY-MM-DD`.
   - `Leave Days` - the annual-leave balance. Posted into the employee's HRMS Leave Allocation
     (created if none covers the date), so Leave Application and payroll see it.
   - `Leave-Salary Days` - the earned leave-salary balance. Lives only in the ledger.
3. Only after that, on **Country Config**, set **Leave Accrual Engine = HR Suite Ledger**
   (and leave "Ledger Accrues From" at the first of the month after the opening date).
   Existing sites are never switched automatically.

Guards: one Opening row per employee; an Opening row is refused once accrual has run for that
employee (correct the balance with an **Adjustment** row instead); rows are never deleted.
Negative days are allowed on an Adjustment.

Before this month's payroll: opening balances imported, pending Leave Applications entered,
annual-leave days excluded from regular pay.
