# HR Suite — Employee Lifecycle Guide

Complete reference for the full employee lifecycle from hiring to exit: what is automated, how to test each stage, and how every step connects to Frappe HRMS.

---

## Contents

1. [Country Resolution](#1-country-resolution)
2. [Prerequisites — System Setup](#2-prerequisites--system-setup)
3. [Stage 1 — Requisition & Hiring](#3-stage-1--requisition--hiring)
4. [Stage 2 — Onboarding](#4-stage-2--onboarding)
5. [Stage 3 — Leave Management](#5-stage-3--leave-management)
6. [Stage 4 — Payroll](#6-stage-4--payroll)
7. [Stage 5 — Performance & Development](#7-stage-5--performance--development)
8. [Stage 6 — Exit](#8-stage-6--exit)
9. [Country Compliance Matrix](#9-country-compliance-matrix)
10. [HRMS Integration Map](#10-hrms-integration-map)
11. [Test Walkthrough — End-to-End by Country](#11-test-walkthrough--end-to-end-by-country)

---

## 1. Country Resolution

Every compliance action in HR Suite starts by resolving the employee's work country to an ISO-2 code. The resolution runs in this priority order:

```
1. Employee.work_country              ← explicit HR override
2. Country Employment Contract.work_country  ← active contract
3. Company.country → Country.code     ← Frappe's Country.code field (ISO-2)
4. Hr Suite Settings.default_work_country   ← global fallback
```

The resolved code (`SA` / `AE` / `BH` / `IN` / `OM`) determines:

| What changes | Driven by country code |
|---|---|
| Statutory deduction scheme | GOSI (SA), GPSSA/DEWS (AE), SIO (BH), EPF+ESI (IN), PASI (OM) |
| Settlement formula | Art. 84 (SA), Art. 51/132 (AE), Art. 116 (BH), Gratuity Act (IN), Art. 39 (OM) |
| Leave entitlement | Days from Country Config leave_types table |
| Minimum wage check | min_wage from Country Config |
| Employee form buttons | GOSI group (SA), GPSSA/DEWS group (AE), EPF/ESI group (IN), etc. |
| WPS file format | SIF (SA/AE/BH), bank CSV (IN/OM) |

**Where to configure:** HR Suite → Country Config → create one record per country code.

---

## 2. Prerequisites — System Setup

Complete these once before testing any lifecycle stage.

### 2.1 Company setup

1. Go to **Accounting → Company → New**
2. Set `Country` to the target country (e.g. "Saudi Arabia" for SA testing)
3. Set `Default Currency` (SAR / AED / BHD / INR / OMR)
4. Save

### 2.2 Country Config

1. Go to **HR Suite → Country Config → New**
2. Set `Country Code`: SA / AE / BH / IN / OM
3. Fill the statutory scheme fields:

   **For SA:**
   - Statutory Scheme: `GOSI`
   - Employee Rate: `9.75`  Employer Rate: `12.5`
   - Settlement Formula: `SA_EOSB`
   - Min Wage: `4000`
   - WPS Format: `SIF`
   - Nationalization Scheme: `Nitaqat`

   **For AE:**
   - Statutory Scheme: `GPSSA` (nationals) / `DEWS` (expats — set via employee nationality)
   - Employee Rate: `5` Employer Rate: `12.5`
   - Settlement Formula: `AE_GRATUITY`
   - Min Wage: `0` (no statutory min for private sector)
   - WPS Format: `SIF`
   - Nationalization Scheme: `Emiratization`

   **For IN:**
   - Statutory Scheme: `EPF_ESI`
   - Employee Rate: `12` (EPF) Employer Rate: `12`
   - Settlement Formula: `IN_GRATUITY`
   - Min Wage: `15000`
   - WPS Format: `BANK_CSV`

4. In the **Leave Types** child table, add rows:

   | Leave Type Name | Days Per Year | Days Below Threshold | Days Above Threshold |
   |---|---|---|---|
   | Annual Leave | 21 | 21 | 30 |
   | Sick Leave | 30 | — | — |
   | Emergency Leave | 3 | — | — |

   > The leave type names must exactly match Leave Types created in HRMS.

5. Save

### 2.3 HR Suite Settings

1. Go to **HR Suite → HR Suite Settings**
2. Set `Default Work Country` to your primary country code
3. Enable `Monthly Leave Allocation` if you want the scheduler to auto-allocate leave monthly
4. Set GOSI rates if testing SA (or leave defaults: 9.75 / 12.5 / 0 / 2)
5. Save

### 2.4 HRMS Leave Types

For each leave type in your Country Config, create a matching HRMS Leave Type:

1. Go to **HR → Leave Type → New**
2. Name: `Annual Leave` (must match Country Config exactly)
3. Max Leaves Allowed: `30`, Is Carry Forward: tick, Allow Negative: untick
4. Save
5. Repeat for Sick Leave, Emergency Leave

### 2.5 HRMS Salary Structure

1. Go to **Payroll → Salary Structure → New**
2. Name: e.g. `Standard SA`
3. Add Earnings components: Basic, Housing Allowance, Transport Allowance
4. Add Deductions components: GOSI (formula-based) or leave blank — HR Suite injects via hook
5. Save and Submit

---

## 3. Stage 1 — Requisition & Hiring

### How it works

```
Job Requisition (HRMS) ──► Job Opening (HRMS) ──► Job Applicant (HRMS)
                                                        │
                                                   Job Offer (HRMS)
                                                        │
                                              on_submit hook fires
                                                        │
                                               Employee (HRMS) auto-created
```

**HRMS hook:** `Job Offer → on_submit` → `hr_suite.hr_suite.integrations.hrms.on_job_offer_submit`

When a Job Offer is submitted:
- Looks up the Job Opening via `Job Applicant.job_title`
- Derives `work_country` from Job Opening branch or Company.country
- Creates an HRMS `Employee` record with name, company, designation, and `date_of_joining = offer_date`
- Sets `work_country` on the Employee (if the custom field exists)

The HR Suite-specific fields on **Job Requisition** (added as Custom Fields):
- `hrsuite_saudization_priority` — flag for Nitaqat compliance (SA)
- `hrsuite_budgeted_monthly_salary` — budget ceiling for approval
- `hrsuite_key_requirements` — free text
- `hrsuite_business_reason` — justification for the headcount

### Test steps

**Test 1.1 — Create requisition and generate offer**

1. **HR Suite → Job Requisition → New** (this opens HRMS Job Requisition)
   - Designation: `Software Engineer`
   - No. of Positions: `1`
   - Department: `Technology`
   - Company: *(your test company)*
   - HR Suite section: tick `Saudization Priority` if testing SA
   - Save and Submit

2. **HR → Job Opening → New**
   - Job Title: `Software Engineer - 2026`
   - Department: `Technology`
   - Company: *(your test company)*
   - Status: `Open`
   - Save

3. **HR → Job Applicant → New**
   - Applicant Name: `Test Employee SA`
   - Email: `test.sa@example.com`
   - Job Opening: *(select the one you created)*
   - Status: `Open`
   - Save

4. **HR → Job Offer → New**
   - Job Applicant: *(select above)*
   - Applicant Name: auto-filled
   - Designation: `Software Engineer`
   - Company: *(your test company)*
   - Offer Date: *(today)*
   - Save → **Submit**

**Expected result:** A new Employee record is auto-created. Check HR → Employee List — you should see `Test Employee SA` with Status = Active.

**What to verify:**
- Employee has correct `company`
- Employee has `designation` = Software Engineer
- If `work_country` custom field is present: it should match the Company's country code

---

## 4. Stage 2 — Onboarding

### How it works

After the Employee record exists, complete their profile and set up the statutory/contractual framework.

**HRMS hooks:**
- `Employee.after_insert` → `on_employee_insert`: sets work_country, applies statutory defaults
- `Employee.on_update` → `on_employee_update`: re-syncs when company or country changes
- `Salary Structure Assignment.on_submit` → blocks if base < Country Config min wage

### Test steps

**Test 2.1 — Complete employee profile**

1. Open the auto-created Employee record
2. Fill mandatory fields:
   - Date of Birth
   - Gender
   - Nationality (e.g. "Saudi Arabia" for SA national)
   - Department, Designation
3. Save — the `on_update` hook fires and sets `work_country` from Company.country if not already set

**Test 2.2 — Country Employment Contract**

1. Go to **HR Suite → Country Employment Contract → New**
2. Employee: *(test employee)*
3. Work Country: `SA` (or AE/BH/IN/OM)
4. Contract Type: `Indefinite`
5. Start Date: *(joining date)*
6. Basic Salary: `8000`, Housing: `2000`, Transport: `1000`
7. Contract Status: `Active`
8. Save

**Expected:** The employee form's contract banner now shows this contract. The work_country resolution will use this contract going forward.

**Test 2.3 — Salary Structure Assignment (with min wage enforcement)**

1. Go to **Payroll → Salary Structure Assignment → New**
2. Employee: *(test employee)*
3. Salary Structure: *(one you created in prerequisites)*
4. From Date: *(joining date)*
5. Base: `3000` ← deliberately below SA min wage of 4000
6. Save → **Submit**

**Expected:** An error appears: *"Base salary SAR 3,000 is below the minimum wage SAR 4,000 for SA"*. Change Base to `8000` and submit again — it should succeed.

**Test 2.4 — Work Permit / Iqama (SA / AE)**

1. Go to **HR Suite → Work Permit / Iqama → New**
2. Employee: *(test employee)*
3. Iqama Number: `2305999999`
4. Expiry Date: *(3 months from today)*
5. Save

**Expected:** The 90-day alert scheduler will pick this up. On the Employee form, the Muqeem group shows the Verify Iqama button (SA only).

**Test 2.5 — Leave Allocation**

If `Monthly Leave Allocation` is enabled in Settings, the scheduler creates this automatically. To test manually:

1. Go to **HR → Leave Allocation → New**
2. Employee: *(test employee)*
3. Leave Type: `Annual Leave`
4. From Date: *(start of year / joining date)*
5. To Date: *(end of year)*
6. New Leaves Allocated: `21`
7. Save → **Submit**

**Expected:** The `on_leave_allocation_submit` hook fires. If 21 does not match the Country Config entitlement for this employee's country, a warning appears but the allocation still goes through.

**Test 2.6 — GOSI Registration (SA)**

1. Open the Employee form
2. In the **GOSI** section → click **Register with GOSI**

> Requires Muqeem/GOSI API credentials in HR Suite Settings. Without credentials, the button call returns an authentication error — that is expected in test without live API.

---

## 5. Stage 3 — Leave Management

### How it works

```
Employee applies for leave
        │
HRMS Leave Application.validate
        │
on_leave_application_validate hook fires:
  ├─ Checks leave type matches Country Config leave_types for this employee's country
  │    └─ Warning if leave type not in Country Config (non-blocking)
  └─ If Sick Leave: checks cumulative sick days → warns when approaching tier threshold
        │
Manager approves → HR approves
        │
Leave balance auto-decremented (HRMS standard)
        │
Payroll picks up sick-leave half-pay deduction automatically
```

**Monthly scheduler (`allocate_monthly_leave`):**
Runs 1st of each month if `monthly_leave_allocation_enabled = 1` in Settings.
For each active employee: reads Country Config → creates Leave Allocation with `new_leaves_allocated = annual_days / 12`.

### Test steps

**Test 3.1 — Apply for Annual Leave**

1. Go to **HR → Leave Application → New**
2. Employee: *(test employee)*
3. Leave Type: `Annual Leave`
4. From Date / To Date: *(any 5-day range)*
5. Save

**Expected (validate hook):**
- If Leave Type is in Country Config for this country → no warning
- If Leave Type is NOT in Country Config → a warning message "Annual Leave is not configured for SA employees" (non-blocking, save still works)

6. Submit → Manager approves → HR approves

**Test 3.2 — Sick Leave with tier warning (SA)**

1. Go to **HR → Leave Application → New**
2. Employee: *(test employee)*
3. Leave Type: `Sick Leave`
4. From Date / To Date: 28-day range (approaching 30-day full-pay threshold)
5. Save

**Expected:** A warning appears indicating the employee is near the 30-day full-pay limit. No blocking.

**Test 3.3 — Monthly allocation (manual trigger for testing)**

To test without waiting for the scheduler:

```bash
# In the bench shell on the server
bench --site <site> execute hr_suite.hr_suite.tasks.allocate_monthly_leave
```

**Expected:** Leave Allocation records created for all active employees for the current month. Check HR → Leave Allocation List — filter by today's `from_date`.

---

## 6. Stage 4 — Payroll

### How it works

```
Payroll Entry (HRMS)
    │
    ├─ Processes all employees in the selected company + period
    ├─ Creates Salary Slips (HRMS standard)
    │       └─ before_submit hook: injects salary overrides + deductions
    │
    └─ on_submit hook fires:
            ├─ SA → creates GOSI Contribution record (if not exists for month/year)
            ├─ AE / BH / OM → creates Statutory Contribution record
            ├─ IN → creates EPF/ESI Contribution record
            └─ WPS Submission auto-linked (SA/AE/BH)
```

**HRMS hooks:**
- `Payroll Entry.on_submit` → `on_payroll_entry_submit`
- `Salary Slip.before_submit` → `before_salary_slip_submit`

### Test steps

**Test 4.1 — Run Payroll for SA**

Prerequisites: Employee has a submitted Salary Structure Assignment.

1. Go to **Payroll → Payroll Entry → New**
2. Company: *(SA company)*
3. Start Date / End Date: *(e.g. 01-Jun-2026 to 30-Jun-2026)*
4. Frequency: Monthly
5. **Get Employees** → your test employee appears
6. **Create Salary Slips** → slips created
7. Review one Salary Slip — confirm components
8. **Submit**

**Expected on submit:**
- A `GOSI Contribution` record is auto-created for `Company + June + 2026`
- The contribution shows: SA national → employee 9.75%, employer 12.5%; Expat → employer 2% only
- A `WPS Submission` record is auto-linked to the Payroll Entry

**Verify:** Go to HR Suite → GOSI Contribution → filter by company + year 2026 + month June. Record should exist and not be a duplicate.

**Test 4.2 — Run Payroll for IN**

1. Repeat with an Indian company employee
2. Submit Payroll Entry

**Expected:** An `EPF/ESI Contribution` record is created. Verify in HR Suite → EPF/ESI Contribution.

**Test 4.3 — Minimum wage enforcement**

This was tested in 2.3 above. If you skipped it, submit a Salary Structure Assignment with `base = 3000` for an SA employee — the hook blocks it.

**Test 4.4 — Salary Override**

1. Go to **HR Suite → Salary Override → New**
2. Employee: *(test employee)*
3. Override Type: `Bonus`
4. Amount: `500`
5. Effective Month: *(current month)*
6. Save and Submit

**Expected:** On the next Payroll run, the `before_salary_slip_submit` hook injects this OMR 500 bonus into the Salary Slip automatically. Status changes to `Applied`.

---

## 7. Stage 5 — Performance & Development

### How it works

HRMS Appraisal is the primary performance tool. HR Suite extends it with Custom Fields:
- `hrsuite_compliance_rating` — HR-assessed compliance score
- `hrsuite_promotion_recommended` — flag to trigger Promotion/Transfer
- `hrsuite_promotion_transfer` — Link to Promotion Transfer record
- `hrsuite_salary_adjustment_recommended` — flag to trigger Salary Adjustment
- `hrsuite_salary_adjustment` — Link to Salary Adjustment record

**HRMS hook:** `Appraisal.on_submit` → `on_appraisal_submit`
- Syncs `hrsuite_promotion_transfer` back to the linked Promotion Transfer (sets `appraisal` field)
- Syncs `hrsuite_salary_adjustment` back to the linked Salary Adjustment

### Test steps

**Test 5.1 — Create an Appraisal**

1. Go to **HR → Appraisal → New**
2. Employee: *(test employee)*
3. Start Date / End Date: *(review period)*
4. In the HR Suite section:
   - Compliance Rating: `4.5`
   - Promotion Recommended: tick
5. Save → **Submit**

**Expected:** `on_appraisal_submit` fires. If a Promotion Transfer is linked, that record's `appraisal` field is updated.

**Test 5.2 — Employee Penalty**

1. Go to **HR Suite → Employee Penalty → New**
2. Employee: *(test employee)*
3. Penalty Type: *(select one)*
4. Penalty Amount: `200`
5. Save → **Submit**

**Expected:** The penalty queues for deduction in the next Payroll Entry. On the next Payroll run, the `before_salary_slip_submit` hook deducts SAR 200 from the employee's Salary Slip.

**Test 5.3 — Training Agreement**

1. Go to **HR Suite → Training Agreement → New**
2. Employee: *(test employee)*
3. Training Cost: `5000`
4. Bond Period (months): `12`
5. Bond Start Date: *(today)*
6. Save → **Submit**

**Expected:** If the employee exits within 12 months, the EOSB calculation deducts the pro-rated bond amount.

---

## 8. Stage 6 — Exit

### How it works

Two exit paths exist:

**Path A — Employee Separation (HRMS)**
```
HRMS Employee Separation → on_submit hook
    ├─ Reads resignation_letter_date / boarding_begins_on / Employee.relieving_date
    ├─ Reads Employee.reason_for_leaving → maps to termination type
    ├─ Calls calculate_settlement(employee, country, date, reason)
    │       ├─ SA: Art. 84 formula (service years × monthly basic / 12 × applicable rate)
    │       ├─ AE: Art. 51/132 (21 days/year ≤5 yrs, 30 days/year >5 yrs, capped at 2yr salary)
    │       ├─ BH: Art. 116–117 (15 days/year first 3 yrs, 1 month/year thereafter)
    │       ├─ IN: Gratuity Act 1972 (15/26 × last salary × years, if ≥5 yrs service)
    │       └─ OM: Art. 39–40 (15 days/year first 3 yrs, 1 month/year thereafter)
    └─ Creates EOSB Calculation record automatically
```

**Path B — Termination Notice (HR Suite)**
```
Termination Notice → on_submit
    ├─ Auto-creates Exit Interview (HRMS)  [with hrsuite_termination_notice link]
    ├─ Auto-creates Exit Clearance
    └─ compliance_controls: creates Final Settlement SLA (5-day SLA for SA)
```

Both paths create the EOSB, Exit Interview, and Exit Clearance. Use Path A for resignations processed through the HRMS module; use Path B for formal terminations requiring the HR Suite audit trail.

### Test steps

**Test 6.1 — Employee Separation (resignation)**

1. On the Employee record, set:
   - `reason_for_leaving`: `Resigned`
   - `relieving_date`: *(last working day, e.g. 30-Jun-2026)*
   - Save

2. Go to **HRMS → Employee Separation → New**
3. Employee: *(test employee)*
4. Resignation Letter Date: *(date of resignation letter)*
5. Boarding Begins On: *(last day)*
6. Save → **Submit**

**Expected:**
- An `EOSB Calculation` record is auto-created. Open it and verify:
  - SA employee, 1.5 years service → EOSB = basic × 1.5 × (1/3) for resignation (partial entitlement)
  - AE employee, 3 years → EOSB = 21 days × 3 × monthly_basic/30
  - IN employee, <5 years service → Gratuity = 0 (Gratuity Act requires ≥5 years)
- Status on Employee changes to `Left`

**Test 6.2 — Termination Notice (employer-initiated)**

1. Go to **HR Suite → Termination Notice → New**
2. Employee: *(test employee)*
3. Termination Reason: `Redundancy` (not Art. 80 — ensures EOSB is not zeroed)
4. Notice Start Date: *(today)*
5. Notice Required Days: `30`
6. Save → **Submit**

**Expected:**
- An `Exit Interview` (HRMS) record is auto-created, linked to this Termination Notice via `hrsuite_termination_notice`
- An `Exit Clearance` record is auto-created
- A `Final Settlement SLA` record is auto-created with `risk_level = High` and settlement due in 5 days (SA)

**Test 6.3 — Exit Clearance and payment blocking**

1. Open the Exit Clearance record
2. Note that EOSB payment is blocked while `exit_interview_completed = 0`
3. Open the Exit Interview → set Status to `Completed` → Save
4. Go back to Exit Clearance — `exit_interview_completed` is now 1 (synced by `on_exit_interview_update` hook)
5. Complete all other checklist items on Exit Clearance
6. Set Exit Clearance Status to `Completed`

**Expected:** EOSB record is now unblocked for payment processing.

**Test 6.4 — EOSB with Art. 80 termination for cause (SA)**

1. Create a Termination Notice
2. Termination Reason: `Termination for Cause (Art. 80)`
3. Submit

**Expected:** EOSB amount = 0. The settlement formula detects Art. 80 and sets entitlement to zero.

**Test 6.5 — Loan deduction from EOSB**

1. Create an `Employee Loan` for the test employee: Principal 10,000, 12 monthly installments
2. After 3 months of payroll, outstanding balance = ~7,500
3. Submit Employee Separation
4. Open the EOSB Calculation — verify outstanding loan balance appears as a deduction

---

## 9. Country Compliance Matrix

| Feature | SA | AE | BH | IN | OM |
|---|---|---|---|---|---|
| Statutory scheme | GOSI | GPSSA / DEWS | SIO | EPF + ESI | PASI |
| Employee contribution | 9.75% basic | 5% (nationals) / 0% (expats) | 7% | 12% (EPF) + 0.75% (ESI) | 7% |
| Employer contribution | 12.5% + 0.75% injury | 12.5% (nationals) / DEWS (expats) | 12% | 12% (EPF) + 3.25% (ESI) | 11.5% |
| Settlement formula | Art. 84 (EOSB) | Art. 51/132 (Gratuity) | Art. 116 (Indemnity) | Gratuity Act 1972 | Art. 39–40 (Indemnity) |
| Leave entitlement | 21/30 days | 30 days | 30 days | 12 days | 15/30 days |
| Sick leave tiers | 30/60/30 days | 15/30/45 days | 15/20 days | 10 days | 10 days |
| Min wage | SAR 4,000 (SA nationals) | None (private) | BHD 300 | INR 15,000 (configurable) | OMR 325 |
| WPS format | SIF (Mudad) | SIF (CBUAE) | SIF | Bank transfer | Bank transfer |
| Nationalization | Nitaqat bands (HRSD) | Emiratization quota | Bahrainization | — | Omanization |
| Portal integrations | Muqeem, Qiwa, GOSI API, Mudad | — | — | — | — |
| Residency tracking | Work Permit / Iqama | Residency Permit | CPR | — | Residency Permit |

### Country-specific test scenarios

#### SA — Saudi employee leaving after 6 years (resignation)
- Settlement formula: full entitlement (>5 yrs resignation = full EOSB)
- GOSI deduction applied during all payroll runs
- Nitaqat quota affected on separation
- Muqeem final exit must be initiated for expat employees

#### AE — Expat employee leaving after 3 years
- DEWS contribution (not GPSSA) applies — employer pays to DEWS fund
- Gratuity = 21 days × 3 × (monthly basic / 30) = 63 days × daily rate
- WPS file must be in UAE SIF format
- No employee GPSSA contribution for expats

#### IN — Employee leaving after 4 years (resignation)
- EPF: employee 12% + employer 12% of basic throughout service
- ESI: applicable if monthly gross < INR 21,000
- Gratuity = 0 (< 5 years service required by Gratuity Act)
- PF withdrawal initiation is manual — HR Suite tracks but doesn't file
- No WPS — bank transfer file generated

#### BH — Employee leaving after 7 years (termination)
- SIO: employee 7% + employer 12% throughout service
- Indemnity = first 3 yrs × 15 days + remaining 4 yrs × 30 days = 45 + 120 = 165 days × daily rate
- WPS SIF format (Bahrain)

---

## 10. HRMS Integration Map

### Doc Events (hooks in hooks.py)

| HRMS DocType | Event | HR Suite Handler | What it does |
|---|---|---|---|
| Job Offer | on_submit | `on_job_offer_submit` | Creates Employee from offer; sets work_country from Job Opening branch or Company |
| Employee | after_insert | `on_employee_insert` | Detects country, sets work_country custom field, applies statutory defaults |
| Employee | on_update | `on_employee_update` | Re-syncs work_country when company or contract changes |
| Salary Slip | before_submit | `before_salary_slip_submit` | Injects pending salary overrides; applies deductions (loans, penalties) |
| Appraisal | on_submit | `on_appraisal_submit` | Syncs hrsuite_promotion_transfer and hrsuite_salary_adjustment to linked docs |
| Leave Application | validate | `on_leave_application_validate` | Warns if leave type not in Country Config; checks sick-pay tier |
| Leave Allocation | on_submit | `on_leave_allocation_submit` | Warns if allocated days mismatch Country Config entitlement |
| Salary Structure Assignment | on_submit | `on_salary_structure_assignment_submit` | Blocks if base < Country Config min_wage |
| Payroll Entry | on_submit | `on_payroll_entry_submit` | Routes to correct contribution creator (GOSI / EPF+ESI / Statutory) |
| Employee Separation | on_submit | `on_employee_separation_submit` | Resolves country, calculates settlement, auto-creates EOSB |
| Exit Interview | on_update | `on_exit_interview_update` | Syncs completion flag to linked Exit Clearance |
| Exit Interview | on_trash | `on_exit_interview_trash` | Clears completion flag on Exit Clearance |

### HRMS Custom Fields added by HR Suite

**Job Requisition** (HR Suite fields on HRMS doctype):
- `hrsuite_saudization_priority` — Nitaqat compliance flag (SA)
- `hrsuite_budgeted_monthly_salary` — headcount budget ceiling
- `hrsuite_key_requirements` — role requirements
- `hrsuite_business_reason` — justification text

**Appraisal** (HR Suite fields on HRMS doctype):
- `hrsuite_compliance_rating` — HR-assessed compliance score
- `hrsuite_promotion_recommended` — trigger flag
- `hrsuite_promotion_transfer` — Link → Promotion Transfer
- `hrsuite_salary_adjustment_recommended` — trigger flag
- `hrsuite_salary_adjustment` — Link → Salary Adjustment

**Exit Interview** (HR Suite fields on HRMS doctype):
- `hrsuite_termination_notice` — Link → Termination Notice
- `hrsuite_exit_clearance` — Link → Exit Clearance
- `hrsuite_interview_mode` — In Person / Video Call / Phone
- `hrsuite_primary_exit_reason` — structured exit reason
- `hrsuite_rehire_eligible` — rehire flag
- `hrsuite_overall_experience_rating` — Excellent/Good/Average/Poor
- `hrsuite_final_recommendation` — Rehire/Do Not Rehire/Case by Case
- `hrsuite_immediate_follow_up_required` — urgent flag
- `hrsuite_what_worked_well`, `hrsuite_improvement_suggestions`, `hrsuite_retention_opportunity`, `hrsuite_follow_up_actions`, `hrsuite_final_comments` — structured feedback fields

### Scheduled Jobs

| Frequency | Function | What it does |
|---|---|---|
| Daily | `send_iqama_expiry_alerts` | 90/30-day Work Permit / Iqama expiry alerts |
| Daily | `send_contract_expiry_alerts` | 60/30-day Country Employment Contract expiry alerts |
| Daily | `send_probation_end_alerts` | Probation end reminders |
| Daily | `send_sick_leave_threshold_alerts` | Sick leave 30/90/120-day threshold alerts |
| Daily | `send_final_settlement_sla_alerts` | Final Settlement SLA overdue escalation |
| Daily | `sync_expiring_iqamas` | Muqeem API sync for permits expiring in 90 days |
| Daily | `apply_pending_salary_overrides` | Apply queued overrides before payroll |
| Weekly | `send_iqama_expiry_alerts` | Mid-week expiry repeat |
| Monthly | `allocate_monthly_leave` | Creates Leave Allocations (annual_days / 12) for all active employees |
| Monthly | `send_gosi_due_alerts` | GOSI filing reminder (before 15th) |
| Monthly | `sync_nitaqat_monthly` | Qiwa Nitaqat band refresh |
| Monthly | `sync_wps_monthly` | Mudad WPS sync |

---

## 11. Test Walkthrough — End-to-End by Country

### Full SA test (hiring → payroll → exit)

**Setup:**
- Company `Steel Force SA` with country = Saudi Arabia
- Country Config: SA, GOSI, SA_EOSB, min_wage = 4000
- Leave Types: Annual Leave (21/30 days), Sick Leave

**Step 1 — Hire**
1. Job Requisition → tick Saudization Priority
2. Job Opening → Job Applicant (`Ahmed Al-Rashidi`) → Job Offer → Submit
3. Verify Employee `Ahmed Al-Rashidi` auto-created with work_country = SA

**Step 2 — Onboard**
4. Country Employment Contract: SA, Indefinite, Basic 8000, Housing 2000, Transport 1000
5. Salary Structure Assignment: base 8000 → Submit (no min wage error — 8000 > 4000 ✓)
6. Leave Allocation: Annual Leave, 21 days (or let monthly scheduler do it)
7. Work Permit / Iqama: for expat employees only

**Step 3 — Monthly payroll (month 1)**
8. Payroll Entry → company Steel Force SA → Get Employees → Create Slips → Submit
9. Verify GOSI Contribution created: month = current, year = 2026, employee contribution ~780 (9.75% × 8000), employer ~1000
10. Verify WPS Submission linked

**Step 4 — Leave**
11. Leave Application: Ahmed, Annual Leave, 5 days → approve
12. Next Payroll: leave dates reflected, deductions correct

**Step 5 — Exit after 2 years**
13. Employee record: reason_for_leaving = Resigned, relieving_date = 30-Jun-2026
14. Employee Separation → submit
15. EOSB Calculation auto-created:
    - Service: 2 years
    - Resignation <5 years → 1/3 entitlement
    - EOSB = 8000 × (2 × 12) months ÷ 12 × (1/3) = 8000 × 2 × 0.333 ≈ SAR 5,333

---

### Full AE test (hiring → payroll → exit)

**Setup:**
- Company `Steel Force AE` with country = United Arab Emirates
- Country Config: AE, GPSSA/DEWS, AE_GRATUITY, no min wage

**Step 1 — Hire**
1. Job Offer for `Sara Al-Mansoori` → Submit → Employee auto-created, work_country = AE

**Step 2 — Onboard**
2. Country Employment Contract: AE, 2-year Definite, Basic 10000 AED
3. Salary Structure Assignment: base 10000 → Submit (no min wage check for AE)

**Step 3 — Monthly payroll**
4. Payroll Entry → Submit
5. Verify Statutory Contribution created (AE): employer rate applied, DEWS fund contribution for expat

**Step 4 — Exit after 3 years (expat)**
6. Employee Separation → submit
7. EOSB (Gratuity):
   - ≤5 years service → 21 days per year
   - 3 years × 21 days × (10000/30) AED = 63 × 333.33 = AED 21,000

---

### Full IN test (hiring → payroll → exit)

**Setup:**
- Company `HR Suite India` with country = India
- Country Config: IN, EPF_ESI, IN_GRATUITY, min_wage 15000 INR

**Step 1 — Hire**
1. Job Offer for `Priya Sharma` → Submit → Employee work_country = IN

**Step 2 — Onboard**
2. Salary Structure Assignment: base 25000 INR → Submit (25000 > 15000 ✓)

**Step 3 — Monthly payroll**
3. Payroll Entry → Submit
4. Verify EPF/ESI Contribution created: employee EPF 3000 (12% × 25000), employer EPF 3000, employer ESI 812.5 (3.25% × 25000)

**Step 4 — Exit after 4 years**
5. Employee Separation → submit
6. EOSB: Gratuity = 0 (Gratuity Act requires minimum 5 years service)

**Step 4b — Exit after 6 years**
5. Set joining date so service = 6 years → Employee Separation → submit
6. EOSB: 15/26 × 25000 × 6 = INR 86,538

---

### Common testing commands (bench shell)

```bash
# Trigger monthly leave allocation manually
bench --site <site> execute hr_suite.hr_suite.tasks.allocate_monthly_leave

# Trigger GOSI due alert
bench --site <site> execute hr_suite.hr_suite.tasks.send_gosi_due_alerts

# Trigger contract expiry alerts
bench --site <site> execute hr_suite.hr_suite.tasks.send_contract_expiry_alerts

# Run all daily tasks
bench --site <site> execute frappe.utils.scheduler.trigger_scheduler_event --args '["daily"]'

# Test country resolution for a specific employee
bench --site <site> execute hr_suite.hr_suite.utils.get_employee_work_country --args '["EMP-0001"]'

# Check EOSB calculation for an employee
bench --site <site> execute hr_suite.hr_suite.utils.calculate_settlement \
  --args '["EMP-0001", "SA", "2026-06-30", "Termination by Employer"]'
```

---

## Appendix — Field Reference

### Employee fields used by HR Suite

| Field | Source | Used for |
|---|---|---|
| `work_country` | Custom (HR Suite) | Country resolution step 1 |
| `company` | Standard HRMS | Country resolution step 3 (via Company.country) |
| `date_of_joining` | Standard HRMS | EOSB service years calculation |
| `relieving_date` | Standard HRMS | EOSB separation date fallback |
| `reason_for_leaving` | Standard HRMS | Settlement termination type mapping |
| `nationality` | Standard HRMS | GOSI national vs expat rate selection |

### Country Config fields

| Field | Type | Effect |
|---|---|---|
| `country_code` | Data (ISO-2) | Primary lookup key |
| `statutory_scheme` | Select | Routes to GOSI / EPF_ESI / Statutory contribution creator |
| `employee_rate` | Percent | Employee statutory deduction % |
| `employer_rate` | Percent | Employer statutory contribution % |
| `settlement_formula` | Select | Dispatches EOSB formula (SA_EOSB / AE_GRATUITY / BH_INDEMNITY / IN_GRATUITY / OM_INDEMNITY) |
| `min_wage` | Currency | Salary Structure Assignment minimum wage check |
| `wps_format` | Select | WPS Submission file format |
| `nationalization_scheme` | Data | Label for Nitaqat/Emiratization/etc. |
| `leave_types` (child table) | Table | Monthly allocator + leave application validation |
