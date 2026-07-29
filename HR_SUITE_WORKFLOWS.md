# HR Suite — Workflows & Implementation Guide

**App:** `hr_suite` | **Author:** siva@enfono.com | **Framework:** Frappe / ERPNext 15

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Approval Engine (permission_manager)](#approval-engine-permission_manager)
3. [Leave Management Workflows](#leave-management-workflows)
4. [Penalty & Disciplinary Workflows](#penalty--disciplinary-workflows)
5. [Payroll & Compensation Workflows](#payroll--compensation-workflows)
6. [Compliance & Governance Workflows](#compliance--governance-workflows)
7. [Employee Lifecycle Workflows](#employee-lifecycle-workflows)
8. [HR Letters & Forms](#hr-letters--forms)
9. [Automated Alerts (Scheduler)](#automated-alerts-scheduler)
10. [Role & Permission Matrix](#role--permission-matrix)
11. [Implementation Checklist for HR](#implementation-checklist-for-hr)
12. [Doctype Reference](#doctype-reference)

---

## Architecture Overview

```
hr_suite                               permission_manager (separate app)
├── Leave Management                   ├── Approval Engine (Ladder Approve)
│   ├── Saudi Annual Leave             │   ├── PM Workflow
│   ├── Saudi Sick Leave               │   ├── PM Workflow Action
│   ├── Special Leave                  │   ├── PM Employee Approval Chain
│   └── Maternity / Paternity Leave    │   ├── PM Approver Delegation
│                                      │   └── Approval Inbox  /app/pm-approval-inbox
├── Penalties                          │
│   ├── Employee Penalty               └── Permission Studio  /app/permission-studio
│   └── Penalty Type
│
├── Payroll
│   ├── Saudi Monthly Payroll
│   ├── Overtime Request
│   ├── GOSI Contribution          ──► GOSI API (gosi.gov.sa)
│   ├── WPS / Mudad Submission     ──► Mudad WPS (mudad.com.sa)
│   ├── Salary Adjustment
│   │   └── Salary Component Override (pen/clock on SSA fields)
│   ├── Salary Breakup Table       (per-company band lookup, 489 rows)
│   └── Salary Structure Assignment Import  (bulk SSA from Excel)
│       └── Salary Structure Assignment  ←─ custom_import_reference
│
├── Government Portal Integrations
│   ├── Muqeem  ──► MOI (muqeem.sa)        Iqama verify / final exit
│   ├── Qiwa    ──► HRSD (qiwa.info)       Wathiqa / Nitaqat / notices
│   ├── GOSI    ──► gosi.gov.sa            Register / submit / account
│   └── Mudad   ──► mudad.com.sa           SIF file / WPS submit / status
│       └── Government Portal Sync Log  (all calls audited here)
│
├── HR Letters
│   ├── HR Letter
│   └── HR Letter Template
│
├── Compliance (25+)
│   ├── Work Regulation
│   ├── Ministry Filing Tracker
│   ├── NITAQAT · WPS · Iqama · GOSI
│   └── Safety · Legal · Disability
│
└── Employee Lifecycle
    ├── Hiring → Onboarding → Contract
    ├── Performance → Promotion
    └── Termination → EOSB → Exit
```

> **Approval routing** for hr_suite documents (Leave, Overtime, Salary Adjustment, etc.) is
> handled entirely by the **`permission_manager`** app. Both apps must be installed on the site.

---

## Approval Engine (permission_manager)

The multi-level approval engine lives in the `permission_manager` custom app. `hr_suite` does **not** contain any ladder_approve or PM Workflow code — it simply relies on the engine running alongside it on the same site.

### How It Works

```
Employee Record  (in hr_suite)
  └── PM Approval Chain  (custom field managed by permission_manager)
        ├── Level 1 → Direct Manager
        ├── Level 2 → Department Head
        └── Level 3 → HR Manager

HR Suite Document saved / submitted
      │
      ▼
permission_manager PM Workflow engine  (process_workflow_actions)
      │
      ├─ Looks up active PM Workflow for the doctype
      ├─ Resolves approver from Employee's approval chain (level 1 first)
      ├─ Creates PM Workflow Action record  (status = Open)
      └─ Sends email notification to approver

Approver opens PM Approval Inbox  (/app/pm-approval-inbox)
      │
      ├─ Sees all Open PM Workflow Actions assigned to them
      ├─ Clicks Approve / Reject / Return for Correction
      └─ PM Workflow moves document to next state or closes chain
```

### Setting Up an Approval Chain

1. Open the **Employee** record.
2. Go to the **PM Approval** section (added by permission_manager fixtures).
3. Add rows to **PM Approval Chain**:

   | Level | Approver (User) | Applies To |
   |-------|----------------|------------|
   | 1 | manager@company.com | All DocTypes |
   | 2 | dept.head@company.com | All DocTypes |
   | 3 | hr@company.com | All DocTypes |

4. Save the Employee record.

### Creating a PM Workflow

All PM Workflow configuration is done in the **permission_manager** app:

1. Go to **PM Workflow** list → New.
2. Set **Document Type** (e.g., `Saudi Annual Leave`).
3. Define **Document States** — each state has a `doc_status` (0=Draft, 1=Submitted, 2=Cancelled) and edit permissions.
4. Define **Transitions**:
   - From State → To State
   - Action name ("Approve", "Reject")
   - Approver Type: Role / User / Approval Matrix
   - Matrix Level (1, 2, 3 from the employee chain)
5. Save. The engine activates automatically on the next document save.

### Delegation (Out-of-Office Cover)

Create a **PM Approver Delegation** in permission_manager:
- Original Approver → Substitute Approver
- From Date / To Date
- Scope: All DocTypes or specific doctype

---

## Leave Management Workflows

### 1. Saudi Annual Leave

**Doctype:** `Saudi Annual Leave`
**Frappe Workflow:** `annual_leave_approval_workflow`
**Approval Engine:** PM Workflow (via permission_manager)

```
[Employee]
    │  Creates Saudi Annual Leave (Draft)
    ▼
Draft ──────────────────────────────────────────────────────┐
    │  Submit for Review                                     │
    ▼                                                        │ Reject
Pending Approval (Level 1 — Direct Manager)                 │
    │  Approve                                               │
    ▼                                                        │
Finance Approval (Level 2 — Finance/HR Manager)  ◄──────────┘
    │  Approve
    ▼
Approved ──► Employee notified, leave balance updated
    │  (On Cancel)
    ▼
Cancelled ──► Leave balance restored
```

**Key rules:**
- Leave balance checked on save (cannot exceed entitlement).
- Saudi Labor Law: minimum 21 days/year (years 1–5), 30 days/year (5+ years).
- `Annual Leave Disbursement` can be created to pay out unused leave on resignation.

---

### 2. Saudi Sick Leave

**Doctype:** `Saudi Sick Leave`
**Frappe Workflow:** `sick_leave_approval_workflow`

```
[Employee]
    │  Creates Saudi Sick Leave with medical certificate attachment
    ▼
Draft
    │  Submit
    ▼
Pending HR Review ──► HR checks certificate
    │  Approve                 │ Reject → back to employee
    ▼
Approved
    │  (If sick days exceed threshold → daily alert fires)
    ▼
Salary deduction applied per Saudi Labor Law:
    Days 1–30:   Full pay
    Days 31–90:  75% pay
    Days 91–120: 50% pay
    Beyond 120:  Employer may terminate
```

**Daily alert:** `send_sick_leave_threshold_alerts` fires when cumulative sick days cross configurable thresholds.

---

### 3. Special Leave (Hajj / Bereavement / Marriage)

**Doctype:** `Special Leave`

| Leave Type | Duration | Documents Required |
|------------|----------|--------------------|
| Hajj Leave | Up to 20 days (once per employment) | Ministry approval |
| Bereavement Leave | 3–5 days | Relationship to deceased |
| Marriage Leave | 5 days | Marriage certificate |

Workflow: Draft → Approved / Rejected (single HR Manager step).

---

### 4. Maternity / Paternity Leave

**Doctype:** `Maternity Paternity Leave`

| Type | Duration |
|------|----------|
| Maternity | 10 weeks (Article 151, Saudi Labor Law) |
| Paternity | 3 days |
| Miscarriage after 6 months | Available |

Workflow: Draft → Approved (HR Manager).

---

### 5. Annual Leave Disbursement

**Doctype:** `Annual Leave Disbursement`
**Triggered by:** Resignation / End of service

```
[HR] Creates Annual Leave Disbursement
    │
    ▼
Draft → Under Review → Approved → Paid
    │
    ▼
Disburse Type: Basic Salary Only / Full Salary
Amount = (Daily Rate) × (Unused Leave Days)
```

---

## Penalty & Disciplinary Workflows

### 1. Employee Penalty (Auto Salary Deduction)

**Doctypes:** `Penalty Type` + `Employee Penalty`

#### Penalty Type Setup

Create Penalty Types with escalating consequences:

| Field | Example Value |
|-------|--------------|
| Penalty Relation | Unauthorised Absence |
| First Offense | Warning Letter — Value: 0.5 days |
| Second Offense | Written Warning — Value: 1 day |
| Third Offense | Suspension Warning — Value: 2 days |
| Fourth Offense | Termination Notice — Value: 3 days |

#### Employee Penalty Workflow

```
[HR/Manager] Creates Employee Penalty
    │  System auto-counts same penalty_type in current month for employee
    │  Auto-sets repeat_status: First / Second / Third / Fourth
    │  Auto-sets penalty_value from Penalty Type
    ▼
Draft
    │  Set Status = Approved, then Submit
    ▼
Submitted (status = Approved)
    │
    ▼
System creates Additional Salary (deduction):
    Amount = (Base Salary ÷ 30) × penalty_value days
    └── Linked in employee_penalty.additional_salary field

    │  (On Cancel)
    ▼
Additional Salary cancelled → deduction reversed
```

**Repeat offense tracking:** The system counts submitted `Employee Penalty` records for the same employee + penalty_type within the same calendar month to determine the escalation level automatically.

---

### 2. Disciplinary Procedure (Formal Process)

**Doctype:** `Disciplinary Procedure`
**Hook:** `compliance_controls.validate_compliance_doc`

```
Incident Reported
    │
    ▼
Draft ──► Under Investigation ──► Pending Decision ──► Decision Issued
                                                              │
                                              ┌───────────────┼──────────────┐
                                              ▼               ▼              ▼
                                        Verbal Warning  Written Warning  Termination
                                              │               │              │
                                              ▼               ▼              ▼
                                         Employee        Employee       Termination
                                        Warning Notice   Warning Notice   Notice
                                              │
                                              ▼
                                    Employee may Appeal → Disciplinary Appeal workflow
```

---

### 3. Disciplinary Appeal

**Doctype:** `Disciplinary Appeal`
**Frappe Workflow:** `disciplinary_appeal_workflow`

```
Employee files appeal
    │
    ▼
Open → Under Review → Hearing Scheduled → Decided → Closed
                                               │
                             ┌─────────────────┼──────────┐
                             ▼                 ▼          ▼
                          Upheld           Modified    Cancelled
                      (penalty stands)  (reduced)  (penalty reversed)
```

---

### 4. Employee Grievance

**Doctype:** `Employee Grievance`
**Frappe Workflow:** `employee_grievance_workflow`

```
Employee submits grievance (Pay / Leave / Attendance / Manager Conduct / Other)
    │
    ▼
Open → In Review → Resolved → Closed
         │
         ▼ (if unresolved within SLA)
     Escalated to HR Director
```

Channels: Portal / Email / Meeting / Written Letter

---

### 5. Investigation Record

**Doctype:** `Investigation Record`
**Frappe Workflow:** `investigation_workflow`

```
Incident triggers investigation
    │
    ▼
Open → In Progress → Findings Issued → Closed
                          │
                          ▼
               Linked to: Disciplinary Procedure / Labor Dispute / Grievance
```

---

## Payroll & Compensation Workflows

### 1. Overtime Request

**Doctype:** `Overtime Request`
**Frappe Workflow:** `overtime_approval_workflow`
**Approval Engine:** PM Workflow (via permission_manager)

```
[Employee/Manager] Creates Overtime Request
    │
    ▼
Draft → Pending Approval (PM Approval Chain Level 1)
    │  Approved
    ▼
Approved ──► On Submit: Journal Entry created automatically
             (OT hours × hourly rate posted to payroll account)
    │
    ▼
Linked to Saudi Monthly Payroll as Payroll Adjustment Item (Addition)
```

**Saudi Labor Law:** Overtime rate = 150% of hourly wage (Article 107).

---

### 2. Saudi Monthly Payroll

**Doctype:** `Saudi Monthly Payroll`

```
[HR/Payroll] Creates Saudi Monthly Payroll for month/year/company
    │
    ▼
Draft → Processing → Completed → Cancelled
    │
    │  (Fetch Employees)
    ▼
Saudi Monthly Payroll Employee rows created with:
    ├── Basic Salary (from Salary Structure Assignment)
    ├── + Approved Overtime (from Overtime Request)
    ├── + Salary Adjustments (approved)
    ├── - GOSI Deduction (employee share 9.75%)
    ├── - Loan Installments (active Employee Loans)
    ├── - Penalty Deductions (submitted Employee Penalty this month)
    └── = Net Payable
    │
    ▼
WPS Submission created → submitted to government portal
```

---

### 3. Salary Adjustment

**Doctype:** `Salary Adjustment`
**Frappe Workflow:** `salary_adjustment_workflow`
**Approval Engine:** PM Workflow (via permission_manager)

```
[HR/Manager] Creates Salary Adjustment
    │
    ▼
Draft → Under Review (Level 1) → Approved (Level 2 — Finance) → Implemented
    │                                                    │
    │ Rejected                                           ▼
    ▼                                        ERPNext Salary Structure updated
  Rejected                                  Effective from next payroll cycle
```

Types: Merit Increase / Promotion Increase / Market Correction / Retention / Reduction

---

### 4. GOSI Contribution + Direct API Submission

**Doctype:** `GOSI Contribution`  
**Integration:** `integrations/gosi_api.py`

```
Monthly auto-calculation:
    Employee Share: 10% of Basic Salary (Saudi nationals) / 0% (expats)
    Employer Share: 12% of Basic Salary (Saudi nationals) / 2% (expats)
    Ceiling: SAR 45,000 contribution base
    │
    ▼
On Submit: Journal Entry created in ERPNext GL
    │
    ▼
GOSI Portal → Submit to GOSI button (visible when GOSI API enabled)
    │
    ├── API POST → gosi.gov.sa/v1/contributions/submit
    ├── reference_number stored on the GOSI Contribution record
    └── payment_status → Paid | payment_date = today
    │
    ▼
Government Portal Sync Log entry created (portal=GOSI, status=Success/Failed)
```

**Batch path (via API):** `submit_monthly_batch(company, month, year)` submits all pending records in one call and marks all as Paid with the batch reference number.

---

### 4a. WPS Submission via Mudad

**Integration:** `integrations/mudad.py`

```
Payroll Entry submitted (all Salary Slips submitted)
    │
    ▼
Payroll Entry → WPS/Mudad → Preview WPS File
    │  Builds SAMA SIF rows from Salary Slips:
    │  employer_iban (from Settings), employee IBAN, net_pay per slip
    │
    ▼
Payroll Entry → WPS/Mudad → Submit WPS to Mudad
    │  POST → mudad.com.sa/v1/wps/submit
    │  Returns: reference_number, status
    │
    ▼
Payroll Entry → WPS/Mudad → Check WPS Status
    │  GET → mudad.com.sa/v1/wps/status
    │  Returns: is_compliant, violation_reason (if non-compliant)
    │
    ▼
Government Portal Sync Log (portal=Mudad) — full audit trail
```

---

### 5. Employee Loan

**Doctype:** `Employee Loan` + `Employee Loan Installment`

```
[Employee/HR] Creates Employee Loan
    │
    ▼
Draft → Pending Approval → Approved → Ready for Disbursement → Disbursed
    │
    ▼
Installments auto-generated (Equal / Fixed amount)
Deducted automatically from Saudi Monthly Payroll each month
```

---

### 6. Salary Breakup Table — Setup (per company)

**Doctype:** `Salary Breakup Table`  
**File:** `salary_breakup_table/salary_breakup_table.py`

One `Salary Breakup Table` record exists per company (autoname = company name). It holds a lookup of Total Salary → Basic / HRA / Transport / Other Allowance splits derived from the client's HR Excel table.

```
[HR Admin] HR Suite Workspace → Payroll → Salary Breakup Table → New
    │
    ├── Select Company (Link field; record name = company name)
    ├── Save → attach Excel workbook (Salary breakup - <Company>.xlsx)
    ▼
Import Breakup Table button
    │  Reads Excel rows: Total Salary | Basic | HRA | Transport | Other Allowance
    ├── Clears existing rows and writes new child rows (Salary Breakup Row)
    └── Prompts: "Create {Company} Common Structure?"
    │
    ▼  (if confirmed)
Salary Structure auto-created:
    ├── Name:       "{Company} Common Structure"
    ├── Payroll Frequency: Monthly
    ├── Currency:   from Company.default_currency
    └── 4 Earnings components (Basic, HRA, Transport, Other Allowance)
            formula references SSA custom fields:
            Basic → base  |  HRA → custom_hra_amount
            Transport → custom_transport_amount
            Other → custom_other_allowance_amount
```

**Lookup logic** (`get_breakup_for_total_salary`):
- Exact match wins.
- No exact match → highest band ≤ requested total (nearest-lower fallback).
- Returns `None` if company has no Salary Breakup Table or salary is below all bands.

---

### 7. Apply Salary Breakup — Single Employee

**Entry point:** Salary Structure Assignment form → **Apply Salary Breakup** button  
**File:** `public/js/salary_structure_assignment.js`, `salary_override_api.py`

```
[HR] Opens Salary Structure Assignment → Apply Salary Breakup
    │
    ▼
Dialog opens:
    ├── Total Salary (Currency field)
    └── Effective From (Date field)
    │
    │  After 400 ms debounce
    ▼
Live preview (calls get_breakup_preview):
    ├── Exact match → ✓ Band: SAR X,XXX
    ├── Nearest-lower → ↓ Nearest band: SAR X,XXX
    └── 2×2 grid: Basic | HRA
                  Transport | Other Allowance
    │
    ▼  [Apply] clicked
apply_salary_breakup(employee, ssa, total_salary, effective_date)
    ├── Looks up company from Employee record
    ├── Calls get_breakup_for_total_salary(total_salary, company)
    └── Writes 5 Salary Component Override records:
            custom_total_salary, base, custom_hra_amount,
            custom_transport_amount, custom_other_allowance_amount
    │
    ├── Effective date = today / past → Applied immediately
    └── Effective date = future      → Pending (scheduler applies on due date)
```

---

### 8. Bulk Salary Structure Assignment Import

**Doctype:** `Salary Structure Assignment Import`  
**File:** `salary_structure_assignment_import/salary_structure_assignment_import.py`  
**Entry point:** HR Suite Workspace → Payroll → Bulk Salary Structure Assignment → New

#### Excel Template Columns

| Column | Required | Notes |
|--------|----------|-------|
| Employee | Yes | Employee ID, email, or full name (ambiguous name → row fails) |
| Employee Name | No | Display only |
| Salary Structure | Yes | Must be a submitted Salary Structure |
| From Date | No | Falls back to Default From Date on the import doc |
| Total Salary | No | Triggers automatic breakup lookup |
| Base | No | Overridden by breakup Basic when Total Salary is provided |
| Variable | No | Optional variable component |

#### Import Flow

```
[HR] Salary Structure Assignment Import → New
    ├── Select Company + Default From Date
    ├── Download Template (prefilled with active employees for the company)
    ├── Fill in salaries in Excel → attach as workbook
    └── Import Workbook button
    │
    ▼
_process_workbook_rows (per row):
    ├── Resolve Employee (ID / email / name)
    ├── Validate Salary Structure is submitted
    ├── Lookup Salary Breakup Table by employee's company
    ├── Create SSA via HRMS create_salary_structure_assignment
    ├── Tag SSA: custom_import_reference = import doc name
    └── Write breakup fields via db.set_value (bypasses submit lock):
            custom_total_salary, base, custom_hra_amount,
            custom_transport_amount, custom_other_allowance_amount
    │
    ▼
Result dialog (per row): Employee | Salary Structure | Total Salary | Band Applied | Status | SSA link
Dashboard headline: Assigned: N · Skipped: N · Failed: N

Status options: Draft → Queued → Completed | Completed with Errors
                                 Cancelled  | Cancelled with Errors
```

#### Connections

The Connections tab on the import doc lists all `Salary Structure Assignment` records where `custom_import_reference = this doc name` — enabling drill-through from import to created assignments.

#### Retry Failed Rows

**Button:** "Retry Failed Rows (N)" — visible when `status = Completed with Errors` and `failed_count > 0`

```
retry_failed_rows(doc_name)
    ├── Reads import_log JSON, collects row numbers with status = "Failed"
    ├── Re-reads original workbook, processes only those row numbers
    ├── Merges new results into existing log (Assigned / Skipped rows untouched)
    └── Recalculates totals from merged result set
```

Use case: a row failed because a Salary Structure was in Draft; after submitting it, retry without re-running the whole import.

#### Cancel Assignments (Undo Import)

**Button:** "Cancel Assignments" — visible when `status = Completed | Completed with Errors` and `success_count > 0`

```
cancel_import(doc_name)
    ├── Queries all SSAs with custom_import_reference = doc_name AND docstatus = 1
    ├── Cancels each SSA (fails gracefully if a salary slip already exists)
    ├── Lists errors in a dialog if any
    └── Sets status → Cancelled | Cancelled with Errors
```

> **Note:** Cancellation is blocked for any SSA that already has a submitted Salary Slip. Those names are listed in the error dialog so HR can decide individually.

---

## Compliance & Governance Workflows

### 1. Termination Notice → Final Settlement

**Doctypes:** `Termination Notice` → `Final Settlement SLA` → `Exit Clearance` → `Exit Interview`

```
[HR] Creates Termination Notice
    │
    ▼
Draft → HR Review → Management Approval → Approved
    │  (on_submit triggers)
    ▼
Final Settlement SLA auto-created (30-day SLA timer starts)
    │
    ├── End of Service Benefit calculated
    ├── Annual Leave Disbursement created (unused leave)
    ├── Employee Loans marked for immediate recovery
    └── Exit Clearance checklist generated
    │
    ▼
Exit Clearance (IT / Finance / Admin sign-off)
    │
    ▼
Exit Interview conducted
    │
    ▼
Final payment processed → Employee status = Left
```

---

### 2. WPS (Wage Protection System)

**Doctypes:** `WPS Submission` + `WPS Export Report`

```
Saudi Monthly Payroll Completed
    │
    ▼
WPS Submission record created
    │
    ▼
Draft → Submitted → Accepted (by Ministry) / Rejected
    │ (if Rejected)
    ▼
Corrective Action Required → Resubmitted
    │
    ▼
Daily alert: send_wps_correction_due_alerts fires if correction overdue
```

---

### 3. Ministry Filing Tracker

**Doctype:** `Ministry Filing Tracker`

Tracks all government submission deadlines:

| Filing Type | Frequency | Alert Lead Time |
|-------------|-----------|-----------------|
| GOSI Submission | Monthly | 5 days before |
| WPS Submission | Monthly | 3 days before |
| Iqama Renewals | Annual | 60 days before |
| Annual Workforce Disclosure | Annual | 30 days before |
| Training Disclosure | Annual | 30 days before |
| Job Vacancy Disclosure | As needed | Manual |

---

### 4. HR Policy Document

**Doctype:** `HR Policy Document`
**Frappe Workflow:** `hr_policy_review_workflow`

```
[HR] Drafts policy
    │
    ▼
Draft → Active → Under Review → Archived
    │
    ▼
Policy Acknowledgement records created for all employees in scope
    │
    ▼
Employees acknowledge via Portal / Email / Manual sign-off
    │
    ▼
Policy Acknowledgement Summary updated (% acknowledged)
```

---

### 5. Labor Inspection

**Doctype:** `Labor Inspection` + `Labor Inspection Violation`

```
Ministry inspector arrives / scheduled audit
    │
    ▼
[HR] Creates Labor Inspection record
    │
    ▼
Draft → Open Findings → Under Follow-up → Corrected → Closed
    │
    ├── Violations documented (category, severity, article reference)
    ├── Each violation linked to Saudi labor law article (Legal Reference Matrix)
    ├── Inspection Fine SLA created if fines issued
    └── Corrective actions assigned and tracked
```

---

## Employee Lifecycle Workflows

### Full Employee Journey

```
Hiring Requisition (approved by department head)
    │
    ▼
Candidate Profile (screening → interview → offer → accepted)
    │
    ▼
Employee Onboarding (HRMS, Pending → In Process → Completed)
    │
    ▼
Saudi Employment Contract (Draft → Active, expiry alert 60 days before)
    │
    ▼
Work Permit / Iqama (tracked, expiry alert 90 days before)
    │
    │ [During Employment]
    ├── Leave requests (Annual / Sick / Special / Maternity)
    ├── Overtime requests (approved, payroll-linked)
    ├── Performance Reviews (Probation / Quarterly / Annual)
    ├── Training Records (tracked for NITAQAT compliance)
    ├── Penalties (auto salary deduction)
    └── Salary Adjustments (merit / promotion)
    │
    ▼
Promotion Transfer (role/department/salary change with approval)
    │
    ▼
Termination Notice → Final Settlement → Exit Clearance → Exit Interview
```

---

## HR Letters & Forms

### HR Letter Templates

Pre-built templates using Jinja2 variables. Create via **HR Letter Template**:

| Template Type | Common Variables |
|---------------|-----------------|
| Experience Letter | `{{ doc.employee_name }}`, `{{ doc.designation }}`, `{{ doc.joining_date }}` |
| Salary Certificate | Above + `{{ doc.company }}`, salary from Salary Structure |
| NOC Letter | Above + `{{ doc.purpose }}` |
| Employment Confirmation | Above + `{{ doc.department }}`, `{{ doc.nationality }}` |
| Custom | Any field from HR Letter doctype |

### HR Letter Workflow

```
[HR] Creates HR Letter
    │  Select Employee + HR Letter Template
    │  Template terms auto-populate into 'terms' field
    │  Fill in 'Purpose' (addressed to / reason)
    ▼
Draft
    │  Submit
    ▼
Issued (status = Issued)
    │  Print using 'HR Letter' print format
    ▼
Signed & delivered to employee
    │  (If cancelled)
    ▼
Cancelled
```

**Print Format:** Company letterhead, reference number, date, body text (terms rendered), employee info table, HR Manager signature, "Valid for 3 months" notice.

---

## Automated Alerts (Scheduler)

All alerts run daily at midnight unless noted.

| Alert | Doctype | Trigger Condition |
|-------|---------|------------------|
| Iqama Expiry | Work Permit Iqama | 90, 60, 30, 7 days before expiry |
| Contract Expiry | Saudi Employment Contract | 60, 30, 7 days before expiry |
| Work Permit Expiry | Work Permit Iqama | 60, 30, 7 days before expiry |
| Sick Leave Threshold | Saudi Sick Leave | Cumulative days cross threshold |
| Probation End | Saudi Employment Contract | 7 days before probation ends |
| Ministry Filing Due | Ministry Filing Tracker | Per filing type lead time |
| Final Settlement SLA | Final Settlement SLA | Overdue SLA |
| Document Custody | Employee Document Custody Log | Return date passed |
| Inspection Fine SLA | Inspection Fine SLA | Payment deadline approaching |
| WPS Correction Due | WPS Submission | Correction deadline approaching |
| Work Regulation Review | Work Regulation | Annual review date |
| Expat Authorization Due | Expat Work Authorization Control | Renewal deadline |
| Training Disclosure Due | Training Disclosure Register | Submission deadline |
| GOSI Due | GOSI Contribution | 5th of each month (monthly) |
| Approval SLA | PM Workflow Action | Overdue approvals — run by **permission_manager** |

---

## Role & Permission Matrix

| Role | Saudi Annual Leave | Overtime Request | Employee Penalty | Salary Adjustment | HR Letter | Compliance Docs |
|------|-------------------|-----------------|-----------------|------------------|-----------|-----------------|
| Employee | Create Own | Create Own | — | — | — | — |
| Department Approver | Read + Approve (own dept) | Read + Approve | — | — | — | — |
| HR Manager | Full | Full | Create + Approve | Read + Approve | Full | Full |
| HR User | Read + Create | Read + Create | Create | Read | Create | Read |
| Finance Manager | — | Read | — | Approve | — | Read |
| System Manager | Full | Full | Full | Full | Full | Full |

**Row-level security:** `permission_query_conditions` in `hr_suite/permissions.py` ensures employees only see their own records; managers see records for employees they manage; HR sees all.

---

## Implementation Checklist for HR

### Phase 1 — Initial Setup

- [ ] Install both apps on the site:
  ```
  bench --site <site> install-app permission_manager
  bench --site <site> install-app hr_suite
  bench --site <site> migrate
  ```
- [ ] Open **Hr Suite Settings** and configure:
  - Default salary component for penalty deductions
  - GOSI rates (employer / employee shares)
  - Probation period defaults
- [ ] Create **Penalty Types** (Unauthorised Absence, Late Arrival, Policy Violation, etc.)
- [ ] Create **HR Letter Templates** (Experience, Salary Certificate, NOC, Confirmation)
- [ ] Create **Attendance Locations** for each branch (GPS coordinates)

### Phase 2 — Employee Setup

- [ ] For each employee, set **PM Approval Chain** in the PM Approval section (Level 1 = direct manager, Level 2 = dept head, Level 3 = HR)
- [ ] Assign **Department Approver** role to all line managers
- [ ] Create **Saudi Employment Contracts** for all active employees
- [ ] Create **Work Permit Iqama** records for all expat employees
- [ ] Set up **Salary Structure Assignments** in ERPNext (required for penalty deduction calculations)

### Phase 2a — Salary Breakup Table Setup (per company)

- [ ] HR Suite Workspace → Payroll → **Salary Breakup Table** → New
- [ ] Select **Company** (record name = company name; one record per company)
- [ ] Attach the company's salary breakup Excel file → **Import Breakup Table**
- [ ] When prompted, confirm creation of `{Company} Common Structure` Salary Structure
- [ ] Review the auto-created Salary Structure (4 earnings: Basic / HRA / Transport / Other) → Submit it
- [ ] For bulk assignment: HR Suite Workspace → Payroll → **Bulk Salary Structure Assignment** → New
  - Download Template (prefilled with active employees)
  - Fill in `Total Salary` column → attach workbook → **Import Workbook**

### Phase 3 — Compliance Setup

- [ ] Create **Work Regulation** document (upload company's registered labor regulation)
- [ ] Set up **Ministry Filing Tracker** entries for each recurring obligation (GOSI, WPS, etc.)
- [ ] Create **Statutory HR Records Register** and mark status for each required register
- [ ] Configure **GOSI Contribution** settings
- [ ] Set up **WPS Submission** workflow parameters

### Phase 4 — Approval Workflows (in permission_manager)

All multi-level approval configuration is done in the **permission_manager** app — not in hr_suite.

- [ ] Go to **PM Workflow** list → create workflows for each key doctype:
  - Saudi Annual Leave
  - Saudi Sick Leave
  - Overtime Request
  - Salary Adjustment
  - Employee Penalty
  - HR Letter
- [ ] Configure **PM Workflow Document States** with correct doc_status values
- [ ] Configure **PM Workflow Transitions** with matrix levels matching the employee approval chain
- [ ] Test approval flow: submit a leave request → check **PM Approval Inbox** (`/app/pm-approval-inbox`)
- [ ] For out-of-office cover, create **PM Approver Delegation** records as needed

### Phase 5 — Saudi Government Portal Integrations

Configure in **Hr Suite Settings** under each portal's section (all optional — enable only what you have API access to):

**Muqeem (MOI — Iqama management):**
- [ ] Enable Muqeem integration → enter Establishment ID, username, password
- [ ] Test: open any Employee with a Work Permit/Iqama record → Muqeem → Verify Iqama
- [ ] Confirm Government Portal Sync Log entry created

**Qiwa (HRSD — labor contracts & Nitaqat):**
- [ ] Enable Qiwa integration → enter Establishment ID, OAuth2 Client ID + Secret
- [ ] Test: Employee → Qiwa → Verify Wathiqa Contract
- [ ] Test: Nitaqat Record → Sync from Qiwa → band and % updated

**GOSI API (direct contribution submission):**
- [ ] Enable GOSI API → enter Establishment ID + API Key
- [ ] Test: Employee → GOSI → Register with GOSI
- [ ] Test: submitted GOSI Contribution → GOSI Portal → Submit to GOSI → reference number stored

**Mudad / WPS (wage protection submission):**
- [ ] Enable Mudad → enter Establishment ID, Employer IBAN, Bank Code, API Key
- [ ] Test: submitted Payroll Entry → WPS/Mudad → Preview WPS File → verify employee count matches
- [ ] Test: Submit WPS to Mudad → reference number returned
- [ ] Test: Check WPS Status → is_compliant = Yes

### Phase 6 — Go Live

- [ ] Train HR team on **PM Approval Inbox** (`/app/pm-approval-inbox`) in permission_manager
- [ ] Train managers on approving via Approval Inbox
- [ ] Configure email notifications (SMTP) so approval alerts are delivered
- [ ] Set up scheduled tasks: `bench --site <site> scheduler enable`
- [ ] Verify all scheduler tasks run: `bench --site <site> run-scheduler-events daily`

---

## Doctype Reference

### Leave Management
| Doctype | Purpose |
|---------|---------|
| Saudi Annual Leave | Annual leave requests with Saudi law entitlement |
| Saudi Sick Leave | Sick leave with medical certificate tracking |
| Special Leave | Hajj, Bereavement, Marriage leave |
| Maternity Paternity Leave | Statutory parental leave |
| Annual Leave Disbursement | Cash-out unused leave on resignation |
| Monthly Attendance Record | Monthly attendance summary per employee |
| Monthly Attendance Detail | Daily detail rows for attendance record |
| Saudi Daily Attendance | Individual daily attendance record |
| Saudi Employee Checkin | Check-in/out log |

### Penalties & Discipline
| Doctype | Purpose |
|---------|---------|
| Penalty Type | Define penalty categories with 4-level escalation |
| Employee Penalty | Individual penalty record, auto-deducts salary |
| Disciplinary Procedure | Formal disciplinary process |
| Disciplinary Decision Log | Record of disciplinary decisions |
| Disciplinary Appeal | Employee appeal against a decision |
| Disciplinary Violation Catalog | Library of standard violations |
| Employee Warning Notice | Formal warning letter |
| Investigation Record | Incident investigation tracking |
| Absence Case | Unauthorised absence management |

### Payroll & Compensation
| Doctype | Purpose |
|---------|---------|
| Saudi Monthly Payroll | Monthly payroll run |
| Saudi Monthly Payroll Employee | Per-employee row in payroll |
| Payroll Adjustment Item | Manual addition/deduction to payroll |
| Salary Adjustment | Salary change with approval workflow |
| Salary Component Override | Audit log for individual SSA field changes (pen/clock buttons) |
| Salary Breakup Table | Per-company band lookup: Total Salary → Basic / HRA / Transport / Other |
| Salary Breakup Row | Child table row: one salary band with 4 component splits |
| Salary Structure Assignment Import | Bulk creation of Salary Structure Assignments from Excel |
| GOSI Contribution | Social security monthly contribution |
| Employee Loan | Loan agreement and disbursement |
| Employee Loan Installment | Monthly installment schedule |
| Overtime Request | Overtime approval and payroll linking |
| End of Service Benefit | EOSB calculation on termination |

#### Custom Fields on Salary Structure Assignment

| Fieldname | Type | Purpose |
|-----------|------|---------|
| `custom_total_salary` | Currency | Total salary used for breakup lookup |
| `custom_hra_amount` | Currency | HRA split applied by breakup |
| `custom_transport_amount` | Currency | Transport allowance split |
| `custom_other_allowance_amount` | Currency | Other allowance split |
| `custom_import_reference` | Link → SSAI | Traces which bulk import created this SSA; hidden, read-only |

### HR Letters & Documents
| Doctype | Purpose |
|---------|---------|
| HR Letter Template | Reusable Jinja2 letter templates |
| HR Letter | Individual letter issuance (Experience, NOC, etc.) |
| HR Policy Document | Company policy with acknowledgement tracking |
| Policy Acknowledgement | Employee acknowledgement of a policy |
| Saudi Employment Contract | Employment contract with terms |
| Contract Portal Evidence | Uploaded contract evidence documents |

### Approval Engine (permission_manager app)

> These doctypes are owned by the **`permission_manager`** app. They are listed here for
> reference because hr_suite workflows depend on them.

| Doctype | App | Purpose |
|---------|-----|---------|
| PM Workflow | permission_manager | Define multi-level approval workflow for any doctype |
| PM Workflow Action | permission_manager | Pending approval task assigned to a user |
| PM Workflow Action Permitted Role | permission_manager | Roles allowed to act on an approval |
| PM Workflow Transition | permission_manager | State transition rules |
| PM Workflow Document State | permission_manager | Per-state document permissions |
| PM Employee Approval Chain | permission_manager | Employee's approval hierarchy |
| PM Approver Delegation | permission_manager | Out-of-office approval delegation |

### Employee Lifecycle
| Doctype | Purpose |
|---------|---------|
| Hiring Requisition | Position request with approval |
| Candidate Profile | Applicant tracking |
| Employee Onboarding | HRMS onboarding activities (not shipped by HR Suite) |
| Performance Review | Probation/quarterly/annual review |
| Promotion Transfer | Role/salary/department change |
| Training Record | Individual training history |
| Training Agreement | Pre-training bond agreement |
| Exit Clearance | Multi-department exit checklist |
| Exit Interview | Exit discussion documentation |
| Termination Notice | Formal termination with workflow |

### Saudi Government Portal Integrations
| DocType / Module | Purpose |
|---------|---------|
| Government Portal Sync Log | Unified audit log for all portal API calls (Muqeem, Qiwa, GOSI, Mudad) |
| `integrations/muqeem.py` | Muqeem MOI — Iqama verification, exit/re-entry, final exit |
| `integrations/qiwa.py` | Qiwa HRSD — labor contracts, Nitaqat, labor notices |
| `integrations/gosi_api.py` | GOSI — registration, contribution submission, employer account |
| `integrations/mudad.py` | Mudad WPS — SIF file generation, submission, compliance check |
| Salary Component Override | Audit-trail record for every salary field change via pen icon |

### Compliance & Governance
| Doctype | Purpose |
|---------|---------|
| Work Permit Iqama | Expat visa/Iqama tracking (Muqeem-integrated) |
| Ministry Filing Tracker | Government submission deadlines |
| NITAQAT Record | Saudi worker quota compliance (Qiwa-integrated) |
| Statutory HR Records Register | Legal document maintenance |
| Work Regulation | Company labor regulation |
| Working Time Compliance Check | Daily hours verification |
| Labor Inspection | Ministry inspection tracking |
| Labor Inspection Violation | Violations from inspection |
| Inspection Fine SLA | Fine payment deadline tracking |
| Final Settlement SLA | Exit process SLA tracking |
| WPS Submission | Wage protection system submission |
| Legal Reference Matrix | Saudi law article reference |
| HR Compliance Action Log | Compliance audit trail |
| Saudi Regulatory Task | Regulatory task backlog |
| Labor Dispute | Conflict documentation |
| Safety Inspection and Risk Control | Workplace safety audit |
| Disability Employment Compliance | Disability hiring quota |
| Special Employment Category Control | Gig/contractor classification |
| Work Arrangement Control | Remote/flexible work policy |
| Expat Work Authorization Control | Foreign worker classification |
| Training Disclosure Register | Mandated training register |
| Holiday Leave Overlap Rule | Holiday/leave conflict rules |
| Medical Examination | Pre-employment/periodic exam |

### Reports
| Report | Type | Purpose |
|--------|------|---------|
| Saudi Leave Balance Report | Query | Leave entitlement & balance |
| Team Attendance Review | Script | Manager attendance dashboard |
| Contract Expiry Report | Query | Contract renewal alerts |
| EOSB Calculation Report | Query | End-of-service benefit details |
| GOSI Monthly Report | Query | GOSI deduction summary |
| Loan Deduction Register | Query | Loan installment tracking |
| Monthly Loan Recovery Summary | Query | Loan recovery status |
| Outstanding Employee Loans | Query | Unpaid loan balances |
| Work Permit Expiry Report | Query | Iqama renewal schedule |
| WPS Export Report | Query | Payroll export for WPS |
| WPS Submission Tracker | Script | WPS submission audit |
| Compliance Case Tracker | Script | Absence case audit |
| Labor Inspection Tracker | Script | Ministry inspection tracking |
| Saudi Compliance Obligation Backlog | Script | Overdue regulatory tasks |
| Saudi Legal Review Queue | Script | Legal reference audit |
| Policy Compliance Register | Script | Policy acknowledgement status |
| NITAQAT Compliance Report | Script | Saudization quota compliance |
| Saudi Labor Coverage Matrix | Script | Labor law coverage mapping |

---

*Updated: 2026-06-09 | hr_suite v0.0.1 | Approval engine: permission_manager | For internal HR use*
