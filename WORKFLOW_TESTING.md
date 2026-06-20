# HR Suite — Workflow Testing Guide

> Use the **Seed Demo Data** button (Professional HR Hub → Menu → Seed Demo Data) to create 4 test employees before running these tests.

---

## Prerequisites

1. Run bench migrate and bench build after any code change
2. Ensure at least one Company exists
3. Use the seeder: `HR Hub → Menu → Seed Demo Data (4 Employees)`
4. Log in as Administrator for full access

---

## Test 1 — Full Hire-to-Active Lifecycle (Ahmed Al-Ghamdi, Saudi National)

**Goal:** Verify the automated chain: Candidate → Employee → Contract → GOSI salary sync

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open `Candidate Profile` → New | Form opens |
| 2 | Set Status = "Accepted", set Expected Joining Date | On save: Employee record auto-created, Employee Onboarding draft auto-created |
| 3 | Open the auto-created `Employee Onboarding` | All 6 checklist items visible |
| 4 | Check all 6 checklist items, Save | Completion % = 100%, Status = "Completed" |
| 5 | Submit the Employee Onboarding | Employee status set to "Active" |
| 6 | Open `Saudi Employment Contract` → New for Ahmed | Fill basic_salary = 10000, nationality = "Saudi Arabia" |
| 7 | Submit the contract | Employee's `GOSI Contribution Base` = 10,000; `Employee Type` = "Saudi National" auto-set |
| 8 | Open Ahmed's Employee form | GOSI Contribution Base visible in Overview, Employee Type = Saudi National, Active Contract banner visible |
| 9 | Click "HR Suite → EOSB Estimate" button | Shows EOSB estimate: ~2 years × 2/3 month = ~SAR 6,667 |

**GOSI Determination Check:**
- Open `GOSI Contribution` → New for Ahmed
- System should default `employee_rate` = 10%, `employer_rate` = 12% (Saudi rates)

---

## Test 2 — Expatriate Onboarding & Iqama Tracking (John Smith)

**Goal:** Verify expatriate flow — GOSI rates 0%/2%, Iqama expiry alert

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open John Smith's Employee form | `Employee Type` = "Expatriate", GOSI Contribution Base = 8,500 |
| 2 | Open `Work Permit Iqama` for John | Iqama record visible, expiry ~290 days |
| 3 | Create `GOSI Contribution` for John | Employee rate = 0%, Employer rate = 2% (expat rates) |
| 4 | Set John's Iqama expiry_date to 25 days from today | Dashboard on Employee form shows **orange** alert: "Iqama expires in 25 days" |
| 5 | Set John's Iqama expiry_date to yesterday | Dashboard shows **red** alert: "Iqama EXPIRED" |
| 6 | Restore correct expiry date | Alert clears |

**Probation Alert (John is in probation — 90 days, currently day ~75):**
- Daily scheduler `send_probation_end_alerts` should fire alert to HR
- Manual test: `bench execute hr_suite.hr_suite.tasks.send_probation_end_alerts`

---

## Test 3 — Disciplinary Procedure (Sara Al-Dosari)

**Goal:** Verify warning → investigation → disciplinary decision chain

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open Sara's `Employee Warning Notice` | Warning level = "First Written Warning" |
| 2 | Create `Investigation Record` for Sara, link to warning | Record saved |
| 3 | Create `Disciplinary Procedure` for Sara | Status = "Under Investigation" |
| 4 | Update Disciplinary Procedure status to "Decision Made" | Can add `Disciplinary Decision Log` |
| 5 | Create `Disciplinary Decision Log` — outcome: "Second Written Warning" | Record saved |
| 6 | Create `Employee Penalty` for Sara — reason: "Repeated Unauthorised Absence" | Penalty amount auto-calculated from Penalty Type |
| 7 | Submit the Employee Penalty | Next payroll run for Sara will show deduction |

**Employee Penalty → Payroll Integration Check:**
- Create `Saudi Monthly Payroll` for current month
- Sara's employee line should show the penalty amount as a deduction
- Submit payroll → verify Salary Slip has the deduction

---

## Test 4 — Full Exit Lifecycle (Tariq Al-Mutairi, Resignation after 7 years)

**Goal:** Verify Termination → auto-create Exit Interview + Exit Clearance + EOSB

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open Tariq's `Termination Notice` (seeded as draft) | Reason = "Resignation by Employee", notice 60 days |
| 2 | Submit the Termination Notice | 3 documents auto-created: Exit Interview, Exit Clearance, End of Service Benefit |
| 3 | Open auto-created `Exit Interview` | Status = "Scheduled", linked to Termination Notice |
| 4 | Open auto-created `Exit Clearance` | Status = "Open", checklist items visible, EOSB linked |
| 5 | Open auto-created `End of Service Benefit` | Years = ~7, EOSB calculated: (5 × 2/3 × 14,000) + (2 × 1 × 14,000) = ~SAR 74,667 |
| 6 | Add `Annual Leave Disbursement` (seeded: 22 days) | Amount = 22 × (14,000 ÷ 30) = SAR 10,267 |
| 7 | Check all clearance items in Exit Clearance | Clearance % increases to 100% |
| 8 | Submit EOSB | Employee status automatically set to "Left" |

**EOSB Calculation Verification (7 years, SAR 14,000 basic):**
```
Years 1–5:  5 × (2/3 × 14,000) = 5 × 9,333 = SAR 46,667
Years 5–7:  2 × (1 × 14,000)   = 2 × 14,000 = SAR 28,000
Gross EOSB: SAR 74,667
+ Leave Disbursement: 22 × 467 = SAR 10,267
Net Settlement: SAR 84,934 (before deductions)
```

---

## Test 5 — Saudi Annual Leave with Payroll Integration

**Goal:** Verify leave → payroll flow for Saudi nationals

| Step | Action | Expected Result |
|---|---|---|
| 1 | Create `Saudi Annual Leave` for Ahmed — 14 days | Balance check: needs 30-day entitlement (3-year employee) |
| 2 | Submit leave (or approve via workflow) | Status = Approved |
| 3 | Create `Saudi Monthly Payroll` for current month | Ahmed's line shows 14 leave days — full pay (paid annual leave) |
| 4 | Submit payroll | Salary slip created, leave days noted, no deduction |

---

## Test 6 — GOSI Contribution with Correct Rates

**Goal:** Verify automatic rate determination by employee type

| Employee | Expected Employee Rate | Expected Employer Rate |
|---|---|---|
| Ahmed Al-Ghamdi (Saudi National) | 10% | 12% |
| John Smith (Expatriate) | 0% | 2% |

**Manual test:**
```bash
bench --site ksa execute "frappe.call" --args "{'method': 'hr_suite.hr_suite.utils.get_gosi_rates', 'args': {'employee': 'EMP-AHMED-ID'}}"
```

---

## Test 7 — WPS Compliance Alert

**Goal:** Verify WPS submission deadline alert

| Step | Action | Expected Result |
|---|---|---|
| 1 | Submit `Saudi Monthly Payroll` for current month | WPS Submission document linked |
| 2 | Leave WPS status as "Pending" for 8 days | Daily alert fires — `send_wps_correction_due_alerts` |
| 3 | Update WPS status to "Submitted" | Alert stops |

Manual trigger: `bench --site ksa execute hr_suite.hr_suite.tasks.send_wps_correction_due_alerts`

---

## Test 8 — Employee Overview Fields

**Goal:** Verify Employee form shows correct HR Suite data

| Step | Check | Expected |
|---|---|---|
| Open any Employee | Overview tab → after General Details | GOSI Contribution Base field visible |
| Open Saudi employee | Overview tab | Employee Type = "Saudi National" |
| Open expatriate | Overview tab | Employee Type = "Expatriate" |
| Open any Employee | Overview tab → Employee Documents section | Documents child table visible, can add Iqama/Passport rows |
| Open Employee with active contract | Form loads | Active Contract banner in dashboard (basic, total salary) |
| Open Employee with active onboarding | Form loads | Onboarding progress banner visible |
| Open Employee with expiring Iqama (< 90 days) | Form loads | Yellow/orange/red banner on dashboard |
| Click "HR Suite → EOSB Estimate" | Popup | Shows years of service + gross + net EOSB |

---

---

## Test 9 — Salary Component Override (Clock & Pen Icons)

**Goal:** Verify the clock/pen icon buttons work on Salary Structure Assignment for future-dated and immediate overrides.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open any submitted `Salary Structure Assignment` | Each numeric field (base salary, allowances) shows a 🕐 and ✏ icon button in the field label |
| 2 | Click the ✏ pen icon on the **base** field | Edit dialog opens: Component = "base" (read-only), Last Value = current, Effective From = today (default) |
| 3 | Set New Value = current + 500, leave date = today, add Notes, click "Save & Submit" | Alert: "Override Applied" (green); form reloads; field value updates immediately |
| 4 | Click 🕐 clock icon on **base** | History dialog shows 1 row: today's change with old/new value, modified by, applied on |
| 5 | Click ✏ pen again, set Effective From = 3 months from today, new value = current + 1000 | Alert: "Pending — will apply on [date]" (blue); form does NOT reload |
| 6 | Open `Salary Component Override` list filtered by this employee | Two records: status = Applied (today's), status = Pending (future-dated) |
| 7 | Run scheduler: `bench --site ksa execute hr_suite.hr_suite.salary_override_api.apply_pending_salary_overrides` | Pending records with past effective date applied; status → Applied |

**Year filter check:**
- In history dialog: select a prior year → list clears (no records for that year)
- Select current year → shows today's records

---

## Test 10 — Muqeem Integration (Iqama Verification)

**Goal:** Verify Muqeem buttons appear when enabled and call the correct endpoint.

**Prerequisites:** Enable Muqeem in Hr Suite Settings; provide test establishment ID + credentials.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Hr Suite Settings → Muqeem section → tick Enable Muqeem → Save | Muqeem fields become visible |
| 2 | Open Employee with a Work Permit / Iqama record | **Muqeem** button group appears (Verify Iqama, Exit Re-entry Status, Sync Log) |
| 3 | Click **Muqeem → Verify Iqama** | API called; result dialog shows status, expiry date, profession |
| 4 | Open Work Permit / Iqama record for same employee | iqama_expiry_date and iqama_status auto-updated from API response |
| 5 | Open Government Portal Sync Log filtered by portal=Muqeem | Entry created: sync_type="Iqama Verify", status="Success" or "Failed", response_data = raw JSON |
| 6 | Open Work Permit / Iqama form → click **Initiate Final Exit** | Dialog asks for exit date + confirm; on confirm: POST to Muqeem API |

**Scheduler test:**
```bash
bench --site ksa execute hr_suite.hr_suite.integrations.muqeem.sync_expiring_iqamas
```
Expected: All Work Permit records expiring within 90 days get re-verified; sync log entries created.

---

## Test 11 — GOSI API Integration

**Goal:** Verify GOSI registration, status check, contribution submission, and batch flow.

**Prerequisites:** Enable GOSI API in Hr Suite Settings; provide establishment ID and API key.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Hr Suite Settings → GOSI — API Integration → tick Enable → fill ID + key → Save | GOSI button group appears on Employee form |
| 2 | Open Employee (Ahmed Al-Ghamdi, Saudi national) → GOSI → **Register with GOSI** | Confirm dialog; on confirm: API called; "Registered with GOSI successfully" alert |
| 3 | Click **GOSI → GOSI Member Status** | Dialog shows: status, registration date, last contribution month |
| 4 | Open a submitted `GOSI Contribution` for Ahmed (payment_status = Pending) | **GOSI Portal → Submit to GOSI** button visible |
| 5 | Click **Submit to GOSI** → confirm | reference_number set on record; payment_status → Paid; payment_date = today |
| 6 | Click **GOSI Portal → Check Member Status** on the GOSI Contribution | Status dialog shown |
| 7 | Click **GOSI Portal → Sync Log** | Government Portal Sync Log opens filtered by GOSI + this employee |
| 8 | Employee → GOSI → **Deregister from GOSI** | Dialog: exit date + reason; on confirm: API called; "Deregistered from GOSI" alert (orange) |

**Scheduler test:**
```bash
bench --site ksa execute hr_suite.hr_suite.integrations.gosi_api.sync_monthly_gosi
```
Expected: `get_employer_account()` called; sync log entry created.

**Negative test:** Disable GOSI API in Settings → open Employee → confirm GOSI button group is gone.

---

## Test 12 — Qiwa Integration (Wathiqa + Nitaqat)

**Goal:** Verify Qiwa contract verification and Nitaqat sync.

**Prerequisites:** Enable Qiwa in Hr Suite Settings; provide establishment ID, client ID, client secret.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Hr Suite Settings → Qiwa section → enable → fill credentials → Save | Qiwa button group on Employee form |
| 2 | Open Employee → Qiwa → **Verify Wathiqa Contract** | API called with Iqama; dialog shows contract status, dates, job title, salary |
| 3 | Open Employee → Qiwa → **Labor Notices** | API called; result dialog shows open notices (empty = compliant) |
| 4 | Open `Nitaqat Record` → click **Sync from Qiwa** | Progress bar → band color and Saudization % updated; frm.reload_doc() |
| 5 | Government Portal Sync Log filtered by portal=Qiwa | Entries for each call: Nitaqat Status, Labor Contract Verify |

**Scheduler test:**
```bash
bench --site ksa execute hr_suite.hr_suite.integrations.qiwa.sync_nitaqat_monthly
```
Expected: All Saudi companies refreshed; Nitaqat Records updated; sync log entries created.

---

## Test 13 — Mudad / WPS Integration

**Goal:** Verify WPS file generation, submission, and status check from Payroll Entry.

**Prerequisites:** Enable Mudad in Hr Suite Settings; fill IBAN, bank code, establishment ID, API key. Have at least one submitted Payroll Entry with submitted Salary Slips.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Hr Suite Settings → Mudad section → enable → fill credentials → Save | WPS/Mudad button group appears on submitted Payroll Entry forms |
| 2 | Open a submitted `Payroll Entry` | WPS/Mudad buttons visible: Preview WPS File, Submit WPS to Mudad, Check WPS Status, Sync Log |
| 3 | Click **Preview WPS File** | Dialog: employee count, total net salary, table with employee ID / name / IBAN / net salary per row |
| 4 | Click **Submit WPS to Mudad** → confirm | API called; "WPS submitted — Ref: [ref] | Status: [status]" green alert |
| 5 | Click **Check WPS Status** | Dialog: period, status, employee count, is_compliant, submitted_on |
| 6 | Click **Sync Log** | Government Portal Sync Log filtered by Mudad |

**SIF file content check:**
- Every row must have employer_iban from Settings
- net_salary = Salary Slip net_pay
- If an employee's IBAN is blank on their Employee record → row has `employee_iban: ""`

**Scheduler test:**
```bash
bench --site ksa execute hr_suite.hr_suite.integrations.mudad.sync_wps_monthly
```
Expected: `get_establishment_status()` called; sync log entry created.

---

## Scheduler Task Tests

Run these manually to verify all scheduled tasks work:

```bash
# ─── Expiry & alert tasks ────────────────────────────────
bench --site ksa execute hr_suite.hr_suite.tasks.send_iqama_expiry_alerts
bench --site ksa execute hr_suite.hr_suite.tasks.send_probation_end_alerts
bench --site ksa execute hr_suite.hr_suite.tasks.send_sick_leave_threshold_alerts
bench --site ksa execute hr_suite.hr_suite.tasks.send_contract_expiry_alerts
bench --site ksa execute hr_suite.hr_suite.tasks.send_wps_correction_due_alerts
bench --site ksa execute hr_suite.hr_suite.tasks.send_gosi_due_alerts

# ─── Salary override ─────────────────────────────────────
bench --site ksa execute hr_suite.hr_suite.salary_override_api.apply_pending_salary_overrides

# ─── Portal integrations ─────────────────────────────────
bench --site ksa execute hr_suite.hr_suite.integrations.muqeem.sync_expiring_iqamas
bench --site ksa execute hr_suite.hr_suite.integrations.gosi_api.sync_monthly_gosi
bench --site ksa execute hr_suite.hr_suite.integrations.qiwa.sync_nitaqat_monthly
bench --site ksa execute hr_suite.hr_suite.integrations.mudad.sync_wps_monthly
```

---

## Automation Chain Summary

```
Candidate Profile (status=Accepted)
    └─► Employee (draft) + Employee Onboarding (draft)  [auto]

Employee Onboarding (all tasks checked, submitted)
    └─► Employee status = "Active"  [auto]

Saudi Employment Contract (submitted)
    └─► Employee: GOSI salary, Employee Type, Designation synced  [auto]

Termination Notice (submitted)
    └─► Exit Interview (draft)  [auto]
    └─► Exit Clearance (draft)  [auto]
    └─► End of Service Benefit (draft, calculated)  [auto]

EOSB (submitted)
    └─► Employee status = "Left"  [auto]
```
