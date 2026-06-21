# HR Suite — Employee Lifecycle Workflow

Complete map of every lifecycle stage from hiring to exit: what HR Suite automates, where each step lives, and how it connects to the default Frappe HRMS app.

---

## Country Resolution (applies everywhere)

Before any compliance action fires, HR Suite resolves the employee's work country using a 4-step chain:

1. `Employee.work_country` — explicit override
2. Active `Country Employment Contract.work_country`
3. `Company.country` → `Country.code` (ISO-2 via Frappe's Country DocType)
4. `Hr Suite Settings.default_work_country` — global fallback

The resolved code (SA / AE / BH / IN / OM) drives statutory rates, leave entitlement, settlement formula, and portal buttons throughout the lifecycle. Country Config stores all per-country parameters.

---

## Stage 1 — Requisition & Sourcing

| Action | HR Suite DocType | Automation | HRMS Connection |
|---|---|---|---|
| Create headcount request | **Hiring Requisition** | Nationalization/Nitaqat check flag built in (SA) | Triggers Job Opening creation |
| Screen candidates | Hiring Requisition | Status workflow: Draft → Approved → Sourcing | — |
| Generate offer | **Job Offer** | On submit → creates HRMS Employee record with defaults | HRMS `Job Offer.on_submit` hook |

**HRMS hook:** `Job Offer → on_submit` → `hr_suite.hr_suite.integrations.hrms.on_job_offer_submit`  
Creates the Employee record stub so HR doesn't have to manually re-enter data.

---

## Stage 2 — Onboarding

| Action | HR Suite DocType / HRMS | Automation | HRMS Connection |
|---|---|---|---|
| Complete employee record | HRMS `Employee` | `after_insert`: set work_country + show country-specific button groups | `Employee.after_insert` hook |
| Issue employment contract | **Country Employment Contract** | Expiry alerts at 60 + 30 days; contract banner on Employee form | — |
| Register with statutory body | Employee form buttons | SA: GOSI Register; AE: GPSSA; IN: EPF/ESI | Country-aware buttons from `employee.js` |
| Enrol leave entitlement | HRMS `Leave Allocation` | Monthly scheduler creates allocations if enabled; manual annual allocation also supported | `Leave Allocation.on_submit` hook validates against Country Config |
| Issue salary structure | HRMS `Salary Structure Assignment` | `on_submit`: blocks if base < Country Config min wage | `Salary Structure Assignment.on_submit` hook |
| Track residency permit | **Work Permit / Iqama** (SA) | 90- and 30-day expiry alerts; Muqeem live status sync | — |
| Assign company policies | HRMS `Employee` / Policy Acknowledgement | Policy Acknowledgement tracks receipt + signature | — |

**HRMS hooks:**  
- `Employee.after_insert` / `on_update` → country detection, work_country sync  
- `Leave Allocation.on_submit` → warns if days mismatch Country Config entitlement  
- `Salary Structure Assignment.on_submit` → minimum wage enforcement

---

## Stage 3 — Leave Management

| Action | HR Suite / HRMS | Automation | HRMS Connection |
|---|---|---|---|
| Monthly leave accrual | `allocate_monthly_leave()` scheduler | On 1st of month: annual_days / 12 per employee, per Country Config leave type | Creates HRMS `Leave Allocation` (submitted) |
| Apply for leave | HRMS `Leave Application` | Country leave type warning; sick-pay tier check on validate | `Leave Application.validate` hook |
| Approve leave | HRMS `Leave Application` | Manager → HR approval flow; balance auto-decremented | Standard HRMS workflow |
| Sick leave tiering | **Sick Leave** (SA custom) | Full / half / no-pay tiers per Country Config; threshold alerts at 30/90/120 days | Feeds HRMS Payroll as deduction |
| Annual leave encashment | HRMS `Leave Allocation` | Unused leave fed into EOSB settlement on exit | — |
| Hajj leave (SA) | HRMS `Leave Application` | Once-per-employment flag enforced | Country Config leave type |

**HRMS hooks:**  
- `Leave Application.validate` → leave type country-match warning, sick-pay tier alert  
- `Leave Allocation.on_submit` → days-vs-config validation

**Monthly allocation scheduler** (`scheduler_events.monthly`):  
`hr_suite.hr_suite.tasks.allocate_monthly_leave` — enabled via `Hr Suite Settings → Monthly Leave Allocation`.

---

## Stage 4 — Payroll

| Action | HR Suite / HRMS | Automation | HRMS Connection |
|---|---|---|---|
| Create payroll run | HRMS `Payroll Entry` | On submit: auto-creates statutory contribution record per country | `Payroll Entry.on_submit` hook |
| SA: GOSI contribution | **GOSI Contribution** | Month/year dedup; employer + employee share per nationality | Created by payroll hook |
| AE/BH/OM: Statutory contribution | **Statutory Contribution** | Per-country rates from Country Config | Created by payroll hook |
| IN: EPF + ESI contribution | **EPF/ESI Contribution** | Employee + employer PF/ESI rates; Gratuity fund deduction | Created by payroll hook |
| WPS bank transfer (SA/AE/BH) | **WPS Submission** | Auto-linked on Payroll Entry submit; SIF export | Standard salary flow |
| Deductions auto-applied | HRMS `Salary Slip` | GOSI, loans, penalties, sick leave half-pay — all auto-populated | `before_salary_slip_submit` hook |
| Salary override | **Salary Override** | Pending overrides applied daily before payroll run | Daily scheduler |
| Overtime | **Overtime Request** | On submit: creates GL journal entry | — |
| Compliance deadline | **Ministry Filing Tracker** | GOSI due alert before 15th monthly | `monthly` scheduler |

**HRMS hooks:**  
- `Payroll Entry.on_submit` → statutory contribution auto-creation  
- `Salary Slip.before_submit` → override + deduction injection

---

## Stage 5 — Performance & Development

| Action | HR Suite / HRMS | Automation | HRMS Connection |
|---|---|---|---|
| Appraisal cycle | HRMS `Appraisal` | On submit: links to promotion/salary review workflow | `Appraisal.on_submit` hook |
| Promotion / Transfer | **Promotion & Transfer** | Updates Employee record; triggers contract amendment | — |
| Training | **Training Agreement** | Bond period tracked; repayment auto-deducted from EOSB if early exit | Feeds EOSB settlement |
| Disciplinary action | **Disciplinary Procedure** | Full investigation → hearing → decision → appeal chain; Art. 80 dismissal sets EOSB to zero | — |
| Penalty | **Employee Penalty** | On submit: auto-deduction queued for next Payroll Entry | `before_save`, `on_submit`, `on_cancel` hooks |

---

## Stage 6 — Employee Exit

| Action | HR Suite / HRMS | Automation | HRMS Connection |
|---|---|---|---|
| Resignation / termination | HRMS `Employee Separation` | On submit: resolves country, calculates settlement, creates EOSB | `Employee Separation.on_submit` hook |
| End of Service Benefit | **EOSB Calculation** | Formula selected by country: SA Art.84, AE Art.51/132, BH Art.116, IN Gratuity Act 1972, OM Art.39–40 | Auto-created from Employee Separation |
| Termination Notice | **Termination Notice** | On submit: triggers Final Settlement SLA (5-day KSA rule) | — |
| Exit clearance | **Exit Clearance** | EOSB payment blocked until clearance = Completed | Linked to EOSB |
| Exit interview | HRMS `Exit Interview` | Auto-created from Employee Separation | Standard HRMS |
| SA: Muqeem final exit | **Work Permit / Iqama** | PRO initiates final exit via Muqeem API | SA only |
| SA: Iqama cancellation | **Work Permit / Iqama** | Alert to PRO on separation; cancellation tracked | SA only |
| Loan recovery | **Employee Loan** | Outstanding balance auto-deducted from EOSB | — |
| Training bond recovery | **Training Agreement** | Pro-rated bond deducted from EOSB | — |

**HRMS hook:**  
- `Employee Separation.on_submit` → `on_employee_separation_submit`:
  - Reads `resignation_letter_date` / `boarding_begins_on` / `Employee.relieving_date`
  - Reads `Employee.reason_for_leaving` to set termination type
  - Calls `calculate_settlement(employee, country, separation_date, termination_reason)` which dispatches the correct country formula
  - Creates EOSB Calculation record automatically

---

## HRMS Doc Events Summary

| HRMS DocType | Event | HR Suite Function | What fires |
|---|---|---|---|
| Job Offer | on_submit | `on_job_offer_submit` | Creates Employee record |
| Employee | after_insert | `on_employee_insert` | Sets work_country, statutory defaults |
| Employee | on_update | `on_employee_update` | Syncs country changes |
| Salary Slip | before_submit | `before_salary_slip_submit` | Injects overrides + deductions |
| Appraisal | on_submit | `on_appraisal_submit` | Links to promotion flow |
| Leave Application | validate | `on_leave_application_validate` | Country leave type + sick-pay tier check |
| Leave Allocation | on_submit | `on_leave_allocation_submit` | Days-vs-Country Config validation |
| Salary Structure Assignment | on_submit | `on_salary_structure_assignment_submit` | Min wage enforcement |
| Payroll Entry | on_submit | `on_payroll_entry_submit` | Statutory contribution auto-creation |
| Employee Separation | on_submit | `on_employee_separation_submit` | Country-aware settlement + EOSB |

---

## Scheduled Jobs Summary

| Frequency | Task | What it does |
|---|---|---|
| Daily | `send_iqama_expiry_alerts` | 90/30-day Iqama expiry notifications |
| Daily | `send_contract_expiry_alerts` | 60/30-day contract expiry notifications |
| Daily | `send_probation_end_alerts` | Probation completion reminders |
| Daily | `send_sick_leave_threshold_alerts` | 30/90/120-day sick leave threshold alerts |
| Daily | `send_final_settlement_sla_alerts` | EOSB 5-day payment SLA escalation |
| Daily | `sync_expiring_iqamas` | Muqeem API sync for expiring permits |
| Daily | `apply_pending_salary_overrides` | Applies queued salary overrides before payroll |
| Monthly | `allocate_monthly_leave` | Creates Leave Allocations (annual/12) for all active employees |
| Monthly | `send_gosi_due_alerts` | GOSI filing due reminder (before 15th) |
| Monthly | `sync_nitaqat_monthly` | Qiwa Nitaqat band refresh |
| Monthly | `sync_wps_monthly` | Mudad WPS sync |
| Weekly | `send_iqama_expiry_alerts` | Mid-week Iqama expiry repeat |

---

## Country Config — What it controls

Every parameter below is read from `Country Config` for the employee's resolved country code. Nothing is hardcoded in application logic.

| Parameter | Used by |
|---|---|
| `statutory_scheme` | Payroll hook — which contribution record to create |
| `employer_rate` / `employee_rate` | Contribution amount calculation |
| `settlement_formula` | EOSB calculation dispatch |
| `leave_types[]` | Monthly allocator + Leave Application validate + Leave Allocation validate |
| `wps_format` | WPS Submission file format |
| `min_wage` | Salary Structure Assignment min wage check |
| `nationalization_scheme` | Nitaqat / Emiratization / Bahrainization labels |

---

## Key Integration Points

```
Hiring Requisition
    └── Job Opening (HRMS)
            └── Job Offer (HRMS)
                    └── on_submit → Employee (HRMS) [auto-created]
                                        └── Country Employment Contract
                                        └── Work Permit / Iqama (SA/AE)
                                        └── Salary Structure Assignment (HRMS)
                                                └── on_submit → min wage check
                                        └── Leave Allocation (HRMS) ← monthly scheduler
                                                └── on_submit → Country Config validation

Payroll Entry (HRMS)
    └── on_submit → GOSI Contribution (SA) / EPF+ESI Contribution (IN) / Statutory Contribution (AE/BH/OM)
    └── Salary Slip (HRMS)
            └── before_submit → overrides + deductions injected

Employee Separation (HRMS)
    └── on_submit → EOSB Calculation [country-formula auto-selected]
                 → Exit Clearance
                 → Exit Interview (HRMS)
                 → Muqeem Final Exit (SA only)
```
