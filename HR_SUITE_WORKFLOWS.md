# HR Suite — Workflows & Implementation Guide

**App:** `hr_suite` | **Author:** siva@enfono.com | **Framework:** Frappe / ERPNext 15

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Approval Engine (Ladder Approve)](#approval-engine-ladder-approve)
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
hr_suite
├── Approval Engine        Ladder Approve (PM Workflow)
│   ├── PM Workflow        Define multi-level approval chains per doctype
│   ├── PM Workflow Action Tracks each pending approval task per user
│   └── Approval Inbox     /app/pm-approval-inbox — unified to-do list
│
├── Leave Management       Saudi Annual Leave · Sick Leave · Special Leave
│                          Maternity/Paternity · Annual Leave Disbursement
│
├── Penalties              Employee Penalty · Penalty Type
│                          Auto-deducts salary via Additional Salary
│
├── Payroll                Saudi Monthly Payroll · GOSI · Salary Adjustment
│                          Overtime Request · Employee Loan
│
├── HR Letters             HR Letter · HR Letter Template
│                          Jinja-rendered, submittable, printable
│
├── Compliance (25+)       Work Regulation · Ministry Filing Tracker
│                          NITAQAT · WPS · Iqama · GOSI · Safety · Legal
│
└── Employee Lifecycle     Hiring → Onboarding → Contract → Promotion
                           → Performance → Termination → EOSB → Exit
```

---

## Approval Engine (Ladder Approve)

### How It Works

The **Ladder Approve** engine (PM Workflow) replaces Frappe's built-in single-approver workflow with a configurable multi-level approval chain stored on each Employee record.

```
Employee Record
  └── PM Approval Chain (child table: custom_pm_approval_chain)
        ├── Level 1 → Direct Manager (user)
        ├── Level 2 → Department Head (user)
        └── Level 3 → HR Manager (user)
```

When a document (Leave Application, Overtime Request, etc.) is saved/submitted:

```
Document Saved
      │
      ▼
PM Workflow engine (process_workflow_actions)
      │
      ├─ Looks up active PM Workflow for the doctype
      ├─ Resolves approver from Employee's approval chain (level 1 first)
      ├─ Creates PM Workflow Action record (status = Open)
      └─ Sends email notification to approver

Approver opens PM Approval Inbox
      │
      ├─ Sees all Open PM Workflow Actions assigned to them
      ├─ Clicks Approve / Reject / Return for Correction
      └─ PM Workflow moves document to next state or closes chain
```

### Setting Up an Approval Chain

1. Open the **Employee** record.
2. Go to the **PM Approval** section.
3. Add rows to **PM Approval Chain**:
   | Level | Approver (User) | Applies To |
   |-------|----------------|------------|
   | 1 | manager@company.com | All DocTypes |
   | 2 | dept.head@company.com | All DocTypes |
   | 3 | hr@company.com | All DocTypes |
4. Save the Employee record.

### Creating a PM Workflow

1. Go to **PM Workflow** list → New.
2. Set **Document Type** (e.g., `Saudi Annual Leave`).
3. Define **Document States** — each state has a `doc_status` (0=Draft, 1=Submitted, 2=Cancelled) and edit permissions.
4. Define **Transitions** — each transition has:
   - From State → To State
   - Action name (e.g., "Approve", "Reject")
   - Approver Type: Role / User / Approval Matrix
   - Matrix Level (1, 2, 3 from the employee chain)
5. Save. The engine activates automatically on next document save.

### Delegation (Out-of-Office Cover)

When an approver is on leave, create a **PM Approver Delegation**:
- Original Approver → Substitute Approver
- From Date / To Date
- Scope: All DocTypes or specific module/doctype

---

## Leave Management Workflows

### 1. Saudi Annual Leave

**Doctype:** `Saudi Annual Leave`  
**Frappe Workflow:** `annual_leave_approval_workflow`  
**Ladder Approve:** Wired via `on_update` hook

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
Salary deduction applied per Saudi Labor Law (first 30 days full pay,
days 31–90 at 75%, days 91–120 at 50%, beyond 120 — employer may terminate)
```

**Daily alert:** `send_sick_leave_threshold_alerts` fires when an employee's cumulative sick days cross configurable thresholds.

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
| First Offense | Warning Letter | Value: 0.5 days |
| Second Offense | Written Warning | Value: 1 day |
| Third Offense | Suspension Warning | Value: 2 days |
| Fourth Offense | Termination Notice | Value: 3 days |

#### Employee Penalty Workflow

```
[HR/Manager] Creates Employee Penalty
    │  (system auto-counts same penalty_type in current month for employee)
    │  (auto-sets repeat_status: First / Second / Third / Fourth)
    │  (auto-sets penalty_value from Penalty Type)
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
**Frappe Workflow:** (validate hook via `compliance_controls.validate_compliance_doc`)

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
**Ladder Approve:** Wired via `on_update` + `on_cancel`

```
[Employee/Manager] Creates Overtime Request
    │
    ▼
Draft → Pending Approval (via PM Approval Chain Level 1)
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
**Ladder Approve:** Wired via `on_update` + `on_cancel`

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

### 4. GOSI Contribution

**Doctype:** `GOSI Contribution`

```
Monthly auto-calculation:
    Employee Share: 9.75% of Basic Salary
    Employer Share: 11.75% of Basic Salary (Saudi nationals)
    Expat employees: Occupational Hazard only (2%)
    │
    ▼
On Submit: Payroll Entries created in ERPNext GL
Monthly GOSI report exported for Ministry submission
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
Employee Onboarding (checklist-based, In Progress → Completed)
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
| Approval SLA | PM Workflow Action | Overdue approvals (Ladder Approve) |

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

- [ ] Install hr_suite on site: `bench --site <site> install-app hr_suite`
- [ ] Run `bench --site <site> migrate`
- [ ] Open **Hr Suite Settings** and configure:
  - Default salary component for penalty deductions
  - GOSI rates (employer / employee shares)
  - Probation period defaults
- [ ] Create **Penalty Types** (Unauthorised Absence, Late Arrival, Policy Violation, etc.)
- [ ] Create **HR Letter Templates** (Experience, Salary Certificate, NOC, Confirmation)
- [ ] Create **Attendance Locations** for each branch (GPS coordinates)

### Phase 2 — Employee Setup

- [ ] For each employee, set **PM Approval Chain** (Level 1 = direct manager, Level 2 = dept head, Level 3 = HR)
- [ ] Assign **Department Approver** role to all line managers
- [ ] Create **Saudi Employment Contracts** for all active employees
- [ ] Create **Work Permit Iqama** records for all expat employees
- [ ] Set up **Salary Structure Assignments** in ERPNext (required for penalty deduction calculations)

### Phase 3 — Compliance Setup

- [ ] Create **Work Regulation** document (upload company's registered labor regulation)
- [ ] Set up **Ministry Filing Tracker** entries for each recurring obligation (GOSI, WPS, etc.)
- [ ] Create **Statutory HR Records Register** and mark status for each required register
- [ ] Configure **GOSI Contribution** settings
- [ ] Set up **WPS Submission** workflow parameters

### Phase 4 — Approval Workflows

- [ ] Create **PM Workflows** for each key doctype:
  - Saudi Annual Leave
  - Saudi Sick Leave
  - Overtime Request
  - Salary Adjustment
  - Employee Penalty
  - HR Letter
- [ ] Configure **PM Workflow Document States** with correct doc_status values
- [ ] Configure **PM Workflow Transitions** with matrix levels
- [ ] Test approval flow: submit a leave request → check PM Approval Inbox

### Phase 5 — Go Live

- [ ] Run `bench --site <site> execute "frappe.get_attr('hr_suite.hr_suite.demo_lifecycle.seed_employee_lifecycle_demo')"` to seed demo data
- [ ] Train HR team on **PM Approval Inbox** (`/app/pm-approval-inbox`)
- [ ] Train managers on approving via Approval Inbox
- [ ] Configure email notifications (SMTP) so approval alerts are delivered
- [ ] Set up scheduled tasks: `bench --site <site> scheduler enable`

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
| GOSI Contribution | Social security monthly contribution |
| Employee Loan | Loan agreement and disbursement |
| Employee Loan Installment | Monthly installment schedule |
| Overtime Request | Overtime approval and payroll linking |
| End of Service Benefit | EOSB calculation on termination |

### HR Letters & Documents
| Doctype | Purpose |
|---------|---------|
| HR Letter Template | Reusable Jinja2 letter templates |
| HR Letter | Individual letter issuance (Experience, NOC, etc.) |
| HR Policy Document | Company policy with acknowledgement tracking |
| Policy Acknowledgement | Employee acknowledgement of a policy |
| Saudi Employment Contract | Employment contract with terms |
| Contract Portal Evidence | Uploaded contract evidence documents |

### Approval Engine
| Doctype | Purpose |
|---------|---------|
| PM Workflow | Define multi-level approval workflow for any doctype |
| PM Workflow Action | Pending approval task assigned to a user |
| PM Workflow Action Permitted Role | Roles allowed to act on an approval |
| PM Workflow Transition | State transition rules |
| PM Workflow Document State | Per-state document permissions |
| PM Employee Approval Chain | Employee's approval hierarchy |
| PM Approver Delegation | Out-of-office approval delegation |

### Employee Lifecycle
| Doctype | Purpose |
|---------|---------|
| Hiring Requisition | Position request with approval |
| Candidate Profile | Applicant tracking |
| Employee Onboarding | Onboarding checklist |
| Performance Review | Probation/quarterly/annual review |
| Promotion Transfer | Role/salary/department change |
| Training Record | Individual training history |
| Training Agreement | Pre-training bond agreement |
| Exit Clearance | Multi-department exit checklist |
| Exit Interview | Exit discussion documentation |
| Termination Notice | Formal termination with workflow |

### Compliance & Governance
| Doctype | Purpose |
|---------|---------|
| Work Permit Iqama | Expat visa/Iqama tracking |
| Ministry Filing Tracker | Government submission deadlines |
| NITAQAT Record | Saudi worker quota compliance |
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

*Generated: 2026-06-09 | hr_suite v0.0.1 | For internal HR use*
