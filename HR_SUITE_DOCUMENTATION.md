# HR Suite — Saudi Arabia HR Management System
## Comprehensive Feature Documentation

**Version:** 1.0 | **Platform:** Frappe/ERPNext v15 | **Jurisdiction:** Kingdom of Saudi Arabia

---

## Table of Contents

1. [Leave Management](#1-leave-management)
   - 1.1 Saudi Annual Leave
   - 1.2 Saudi Sick Leave
   - 1.3 Special Leave
   - 1.4 Maternity / Paternity Leave
   - 1.5 Annual Leave Disbursement
2. [Time & Attendance](#2-time--attendance)
   - 2.1 Overtime Request
3. [Payroll & Compensation](#3-payroll--compensation)
   - 3.1 Saudi Monthly Payroll
   - 3.2 Salary Adjustment
   - 3.3 GOSI Contribution
   - 3.4 WPS Submission
   - 3.5 End of Service Benefit (EOSB)
   - 3.6 Employee Loan
4. [Disciplinary Management](#4-disciplinary-management)
   - 4.1 Employee Penalty
   - 4.2 Disciplinary Procedure
   - 4.3 Investigation Record
   - 4.4 Employee Warning Notice
   - 4.5 Disciplinary Appeal
   - 4.6 Absence Case
5. [Employee Lifecycle](#5-employee-lifecycle)
   - 5.1 Employee Onboarding
   - 5.2 Saudi Employment Contract
   - 5.3 Promotion & Transfer
   - 5.4 Performance Review
   - 5.5 Staff Rating
   - 5.6 Employee Grievance
   - 5.7 Exit Interview
   - 5.8 Exit Clearance
   - 5.9 Termination Notice
6. [HR Documents & Communications](#6-hr-documents--communications)
   - 6.1 HR Letter & HR Letter Template
   - 6.2 HR Policy Document
   - 6.3 Policy Acknowledgement
   - 6.4 Training Record
   - 6.5 Training Agreement
7. [Compliance & Regulatory](#7-compliance--regulatory)
   - 7.1 Labor Inspection
   - 7.2 Work Regulation
   - 7.3 Saudi Regulatory Task
   - 7.4 Nitaqat Record
   - 7.5 Work Injury & Safety
   - 7.6 Work Permit / Iqama Management
   - 7.7 Ministry Filing Tracker
   - 7.8 Statutory HR Records Register
   - 7.9 Disability Employment Compliance
   - 7.10 Expat Work Authorization Control
   - 7.11 Special Employment Category Control
   - 7.12 Working Time Compliance Check
   - 7.13 Work Arrangement Control
   - 7.14 Holiday Leave Overlap Rule
   - 7.15 Labor Dispute
8. [Recruitment](#8-recruitment)
   - 8.1 Hiring Requisition
   - 8.2 Candidate Profile
   - 8.3 Recruitment Service Provider Compliance
9. [Reports](#9-reports)
10. [ERPNext HRMS Integration Map](#10-erpnext-hrms-integration-map)
11. [System Roles & Permissions](#11-system-roles--permissions)
12. [Scheduled Automations](#12-scheduled-automations)

---

## 1. Leave Management

### 1.1 Saudi Annual Leave

**Legal Basis:** Saudi Labor Law Article 109 — employees earn 21 days/year for the first 5 years, then 30 days/year thereafter.

#### Workflow

```
Employee Submits Request
        │
        ▼
  Direct Manager Reviews
  (Approve / Reject / Return)
        │ Approved
        ▼
  HR Manager Final Approval
        │
        ▼
  Status: Approved → Leave Deducted from Balance
        │
        ▼
  ERPNext Leave Allocation Updated (custom hook)
        │
        ▼
  Payroll picks up leave dates during Salary Slip generation
```

#### Full Lifecycle Example

> **Scenario:** Ahmed Al-Ghamdi (EMP-0042), 6-year employee, applies for 14 days of annual leave starting 15 July 2025.

1. Ahmed opens **Saudi Annual Leave** → New. He selects From: 2025-07-15, To: 2025-07-28, reason: "Family Visit." The system auto-calculates 14 working days and checks his balance (30 days entitlement, 7 already taken → 23 remaining ✓).
2. On submit the record moves to **Pending Manager Approval**. Ahmed's direct manager Khalid receives an in-app notification.
3. Khalid approves. Record moves to **Pending HR Approval**.
4. HR Manager Sara approves. Status becomes **Approved**.
5. The `permission_query_conditions` hook ensures Ahmed can only see his own leave; HR can see all.
6. During July payroll run in **Saudi Monthly Payroll**, the system marks those 14 days as approved leave — no deduction from pay since it is paid annual leave.
7. Ahmed's leave allocation in ERPNext **Leave Allocation** is decremented by 14.

#### How It Reports in the System

- **Saudi Leave Balance Report** — real-time balance per employee, filterable by department/year.
- The leave record appears in the **Saudi Monthly Payroll** employee breakdown line so payroll officers can reconcile.
- Linked to ERPNext `Leave Application` (the HR Suite record is the Saudi-specific wrapper; ERPNext Leave Application is auto-created or updated for scheduling purposes).

#### Organizational Benefits

| Benefit | Detail |
|---|---|
| Legal compliance | Enforces KSA 21/30-day entitlement rules automatically |
| Scheduling visibility | Managers see overlapping leaves before approving |
| Payroll accuracy | Leave dates flow directly into payroll — no manual entry |
| Audit trail | Full approval chain with timestamps per Saudi Ministry of HR audit requirements |

---

### 1.2 Saudi Sick Leave

**Legal Basis:** Saudi Labor Law Article 117 — up to 120 days per year: first 30 days full pay, next 60 days half pay, remaining 30 days no pay.

#### Workflow

```
Employee / Manager Reports Sick Leave
        │
        ▼
  Medical Certificate Attached (if > 3 days)
        │
        ▼
  HR Records & Validates Against 120-Day Threshold
        │
        ▼
  Sick Leave Record Approved
        │
        ▼
  Payroll Applies Correct Pay-Tier (Full/Half/Zero)
        │
        ▼
  Threshold Alert sent when approaching 30/90/120 days
```

#### Full Lifecycle Example

> **Scenario:** Maha Saleh (EMP-0089) has taken 28 sick days so far this year. She falls ill again for 5 days.

1. HR creates **Saudi Sick Leave** for Maha. The system auto-tallies her year-to-date total: currently 28 days.
2. The first 2 days of the new request complete the 30-day full-pay tier. The remaining 3 days fall into the half-pay tier. The record stores both segments.
3. The daily scheduler task `send_sick_leave_threshold_alerts` fires the next morning, alerting HR that Maha is now at 33 days — approaching the 60-day half-pay limit.
4. In **Saudi Monthly Payroll**, the payroll processor sees the sick leave breakdown: 2 days full, 3 days half — salary calculations are automatically tiered.
5. If Maha reaches 90 days, a stronger alert notifies HR Manager for potential employment status review per Article 117.

#### Organizational Benefits

- Eliminates manual tracking of multi-tier sick leave pay rules.
- Automated threshold alerts prevent legal disputes from underpaying/overpaying.
- Integrates with ERPNext `Leave Application` to block double-booking on Attendance records.

---

### 1.3 Special Leave

**Covers:** Bereavement, Hajj (once per tenure), official exam leave, national service, and other Saudi-mandated special categories.

#### Workflow

```
Employee Requests Special Leave → HR Validates Category → Approved → Payroll
```

#### Full Lifecycle Example

> **Scenario:** Tariq Ibrahim (EMP-0034) needs Hajj leave (up to 15 days, paid, once per employment).

1. Tariq submits **Special Leave**, category: Hajj. The system checks his employment history — no prior Hajj leave recorded. ✓ Eligible.
2. HR approves. The record is flagged as "Hajj used" on Tariq's profile to prevent future claims.
3. Payroll treats these 15 days as fully paid.
4. If a second Hajj leave were attempted, the system raises a validation error citing prior usage.

---

### 1.4 Maternity / Paternity Leave

**Legal Basis:**
- Maternity: 10 weeks fully paid (Saudi Labor Law Art. 151)
- Paternity: 3 days paid

#### Workflow

```
Employee Submits → Medical Proof Attached → HR Reviews → Approved
        │
        ▼
 Payroll marks days as Paid Maternity/Paternity
        │
        ▼
 Return-to-Work date auto-calculated & tracked
```

#### Full Lifecycle Example

> **Scenario:** Fatima Al-Dosari (EMP-0056) is due to give birth. She submits Maternity Leave starting 2025-08-01.

1. Fatima submits **Maternity Paternity Leave**, Leave Type: Maternity, Expected Birth Date: 2025-08-01.
2. System auto-sets End Date to 2025-10-07 (70 calendar days = 10 weeks).
3. HR attaches the medical certificate, approves the record.
4. Payroll for August and September treats Fatima's days as fully paid maternity leave — no deduction.
5. A return-to-work tracking alert fires 1 week before 2025-10-07, reminding HR to prepare her re-integration.

---

### 1.5 Annual Leave Disbursement

Handles the conversion of accrued annual leave balance to cash — typically done at the end of service or by company policy once per year.

#### Workflow

```
HR Calculates Outstanding Leave Balance
        │
        ▼
Annual Leave Disbursement Record Created
        │
        ▼
Amount = (Daily Wage × Leave Days)
        │
        ▼
Submitted → Journal Entry Created in ERPNext Accounts
        │
        ▼
Reflected in Final Settlement or One-Off Payment
```

#### Full Lifecycle Example

> **Scenario:** Nasser Al-Qahtani is resigning with 18 unused annual leave days. Daily wage = SAR 400.

1. HR creates **Annual Leave Disbursement**, links employee, enters 18 days.
2. System computes SAR 7,200 (18 × 400).
3. On submit, a Journal Entry is created in ERPNext Accounting: Dr. HR Expense (SAR 7,200) / Cr. Payables.
4. This amount flows into the **End of Service Benefit** final settlement calculation.

---

## 2. Time & Attendance

### 2.1 Overtime Request

**Legal Basis:** Saudi Labor Law Article 107 — overtime pay at minimum 150% of regular hourly wage.

#### Workflow

```
Manager / Employee Submits Overtime Request
        │
        ▼
  Justification + Approval (HR Manager)
        │
        ▼
  Submitted → Journal Entry auto-created
        │ (doc_event: on_submit → create_overtime_journal_entry)
        ▼
  OT Hours & Amount reflected in Salary Slip via Salary Adjustment
```

#### Full Lifecycle Example

> **Scenario:** Engineering dept. worked an extra 3 hours on 2025-07-10 to meet a project deadline. 5 employees involved.

1. Manager creates **Overtime Request**, links 5 employees, date: 2025-07-10, hours: 3 each, reason: "Project milestone."
2. HR Manager approves and submits.
3. `create_overtime_journal_entry` fires automatically:
   - Dr. Overtime Expense / Cr. OT Payable (accrual)
   - Amount = (Monthly salary ÷ 30 ÷ 8) × 1.5 × 3 hours per employee.
4. Accountant processes the payable when running July payroll.
5. HR creates **Salary Adjustment** records for each employee with the OT amount, which attaches to their **Saudi Monthly Payroll** line.

#### System Reporting

- All OT requests visible under **Overtime Request** list with department/date filters.
- Journal Entries traceable via ERPNext Accounting → Journal Entry with reference to the OT Request name.
- Cost centre analysis possible in ERPNext to track OT cost per department.

---

## 3. Payroll & Compensation

### 3.1 Saudi Monthly Payroll

The master payroll document for each monthly payroll cycle. Unlike ERPNext's standard Payroll Entry (which processes one employee at a time), Saudi Monthly Payroll processes the entire company simultaneously with Saudi-specific components.

#### Workflow

```
Create Saudi Monthly Payroll (Month/Year + Company)
        │
        ▼
System fetches all Active Employees
        │
        ▼
Per Employee Line Auto-Populated:
  Base Salary + Housing + Transport + Other Allowances
  - Deductions (GOSI Employee Share, Loan Installments,
    Penalties, Tax, Absences, Half-Pay Sick Days)
  + Additions (OT, Bonuses, Adjustments)
        │
        ▼
HR Reviews → Adjustments if needed
        │
        ▼
Submit → Bulk Salary Slips created in ERPNext
        │
        ▼
WPS Submission Generated for SAMA compliance
        │
        ▼
Bank Transfer File Exported (SIF format)
```

#### Full Lifecycle Example

> **Scenario:** June 2025 payroll for a 50-person company.

1. Payroll officer opens **Saudi Monthly Payroll** → New. Month: June 2025. On save, 50 employee lines are auto-populated.
2. The system applies:
   - Salary Adjustments (bonuses approved during June)
   - Sick leave half-pay deductions for 2 employees
   - Loan installment deductions for 3 employees
   - GOSI deductions (10% employer share handled separately; 10% employee share deducted here)
   - 1 Employee Penalty deduction (previously submitted)
3. Payroll officer reviews totals. One employee has a salary change mid-month — the system pro-rates.
4. Submit → ERPNext Salary Slip created for all 50 employees. Accounting entries posted: Dr. Salary Expense / Cr. Salaries Payable.
5. **WPS Submission** document auto-linked and Bank SIF file exported.
6. After bank transfer, WPS status updated to "Submitted."

#### ERPNext Integration

Saudi Monthly Payroll drives standard ERPNext **Salary Slips** and **Payroll Entry** records. HR Suite adds Saudi-specific components (housing allowance, transport allowance, GOSI, WPS) that standard ERPNext does not have out-of-the-box.

---

### 3.2 Salary Adjustment

Ad-hoc additions or deductions to an employee's monthly pay that do not constitute a recurring change to their salary structure.

#### Workflow

```
HR Creates Salary Adjustment (Type: Addition/Deduction)
        │
        ▼
Links to: Overtime Request / Penalty / Bonus / Other
        │
        ▼
Approved → Attaches to next Saudi Monthly Payroll run
        │
        ▼
Reflected in employee's Salary Slip line item
```

**Examples of adjustments:**
- OT payment addition
- Performance bonus addition
- Deduction due to Equipment Damage
- Traffic fine reimbursement deduction

---

### 3.3 GOSI Contribution

GOSI (General Organization for Social Insurance) is a mandatory Saudi social security contribution.

**Rates (2025):**
- Employee: 10% of base salary (Saudi nationals only)
- Employer: 12.5% (Saudi: 11.75% GOSI + 0.75% workplace injury insurance)
- Expatriates: Only 2% workplace injury insurance (employer only)

#### Workflow

```
GOSI Contribution Record Created (Monthly, per company)
        │
        ▼
System calculates Employee & Employer shares per employee
(Saudi nationals vs. expats handled separately)
        │
        ▼
Submit → create_payroll_entries hook fires
        │
        ▼
ERPNext Additional Salary entries created for employee deduction
ERPNext Journal Entries for employer liability
        │
        ▼
GOSI Monthly Report generated for online submission to GOSI portal
```

#### Full Lifecycle Example

> **Scenario:** June GOSI for 30 Saudi nationals and 20 expatriates.

1. HR creates **GOSI Contribution** for June 2025.
2. System fetches all active employees, splits into Saudi/Expat.
3. For each Saudi national: employee deduction = 10% of basic; employer contribution = 11.75% of basic + 0.75% injury.
4. For each expat: employer contribution = 2% of basic (injury only).
5. On submit, `create_payroll_entries` creates **Additional Salary** records in ERPNext so the employee deductions appear automatically in Salary Slips.
6. Employer liability Journal Entry: Dr. GOSI Expense / Cr. GOSI Payable.
7. **GOSI Monthly Report** shows per-employee breakdown ready for upload to the GOSI portal.

---

### 3.4 WPS Submission

WPS (Wages Protection System) is a Saudi SAMA/Ministry of HR requirement to electronically record salary payments within 7 days of the due date.

#### Workflow

```
Saudi Monthly Payroll Submitted
        │
        ▼
WPS Submission document auto-created (or linked)
        │
        ▼
SIF (Salary Information File) generated in WPS format
        │
        ▼
File uploaded to bank / WPS portal
        │
        ▼
WPS Submission status updated to "Submitted"
        │
        ▼
If overdue: send_wps_correction_due_alerts fires daily
```

#### System Reporting

- **WPS Submission Tracker** report shows submission status per month — green (on time), amber (approaching deadline), red (overdue).
- **WPS Export Report** generates the SIF file content for audit review.
- Non-submission triggers automated daily alerts to the payroll officer.

#### Organizational Benefits

- Prevents Ministry of HR fines for late WPS submissions (up to SAR 10,000 per violation).
- Provides verifiable proof of timely salary payment per Saudi labor compliance.

---

### 3.5 End of Service Benefit (EOSB)

EOSB is a mandatory severance payment under Saudi Labor Law Art. 84-88, calculated based on years of service and last drawn salary.

**Calculation Rules:**
- Less than 2 years: no entitlement
- 2–5 years: 1/3 of monthly salary per year
- 5–10 years: 2/3 of monthly salary per year
- More than 10 years: 1 full month's salary per year

Additional adjustments based on resignation vs. termination and disciplinary history.

#### Workflow

```
Termination Notice Submitted
        │
        ▼ (doc_event: on_submit → create_final_settlement_from_termination)
End of Service Benefit Record Auto-Created
        │
        ▼
System Calculates: Service Duration + Applicable Rate
        │
        ▼
Adjustments Added: Unpaid Leave, Loan Balance, Penalties
Annual Leave Disbursement Amount Added
        │
        ▼
Final Settlement Amount = EOSB + Leave Cash + Other Entitlements
        │                         - Deductions
        ▼
HR Reviews → CFO/Finance Approves
        │
        ▼
Submitted → Journal Entry: Dr. EOSB Expense / Cr. EOSB Payable
        │
        ▼
Payment processed within 5 days (KSA legal requirement)
Final Settlement SLA alert tracks the deadline
```

#### Full Lifecycle Example

> **Scenario:** Mohammed Al-Harbi resigns after 8 years, 3 months. Last monthly salary: SAR 12,000.

1. **Termination Notice** submitted (category: Resignation). On submit, EOSB record is auto-created.
2. Service: 8 years 3 months = 8.25 years. Rate: 2/3 month per year for first 5 + 1 month per year for next 3.25.
   - EOSB = (12,000 × 2/3 × 5) + (12,000 × 1 × 3.25) = 40,000 + 39,000 = SAR 79,000
3. **Annual Leave Disbursement**: 12 unused days × (12,000 ÷ 30) = SAR 4,800.
4. Deductions: Employee loan balance SAR 3,000.
5. Net Settlement = 79,000 + 4,800 − 3,000 = **SAR 80,800**.
6. **Final Settlement SLA** tracker fires daily alert after Day 3 if not yet paid (must pay by Day 5 per KSA Labor Law).
7. Finance approves → Journal Entry posted → Bank transfer made.

#### Jinja Integration

`get_eosb_amount(employee, end_date)` utility function available in Frappe Jinja templates for use in HR Letters and print formats.

---

### 3.6 Employee Loan

Internal company loans to employees, recovered via monthly payroll deductions.

#### Workflow

```
Employee Requests Loan
        │
        ▼
HR Manager Approves + Finance Approves
        │
        ▼
Loan disbursed → Journal Entry (Dr. Employee Loan Receivable / Cr. Cash)
        │
        ▼
Installment Schedule Auto-Generated (monthly)
        │
        ▼
Each month: Deduction pulled into Saudi Monthly Payroll automatically
        │
        ▼
Loan Fully Paid → Status: Settled
```

#### Reports

- **Outstanding Employee Loans** — total outstanding per employee.
- **Loan Deduction Register** — monthly deduction history.
- **Monthly Loan Recovery Summary** — aggregate recovery per payroll cycle.

---

## 4. Disciplinary Management

### 4.1 Employee Penalty

A penalty is a formal financial deduction applied to an employee's salary for a specific violation. It is separate from and lighter than a full disciplinary procedure.

#### Workflow

```
HR Manager Records Violation + Creates Employee Penalty
        │
        ▼
Before Save: penalty_type rate fetched, amount calculated
        │
        ▼
Submitted → on_submit: penalty amount stored for payroll deduction
        │
        ▼
Next Saudi Monthly Payroll → deduction applied automatically
        │
        ▼
Accounting: Dr. HR Penalty Income / Cr. Penalty Payable (or offset salary)
        │
        ▼
On Cancel: Reversal entry created, payroll deduction reversed
```

#### Full Lifecycle Example

> **Scenario:** Fahad Al-Rashid arrives late 4 times in one month. Company policy: 3+ lates = 0.5 day salary deduction.

1. HR creates **Employee Penalty** for Fahad. Penalty Type: "Repeated Lateness." System looks up the rate from **Penalty Type** master (0.5 day).
2. Penalty amount calculated: SAR 12,000 ÷ 30 × 0.5 = SAR 200.
3. On submit, the penalty is recorded and flagged for payroll.
4. In next month's **Saudi Monthly Payroll**, Fahad's line automatically shows −SAR 200 deduction.
5. Accounting entry created with full reference to the Penalty record for audit.

#### Organizational Benefits

- Standardized penalty rates across all departments via **Penalty Type** master (prevents inconsistency).
- Full audit trail: every penalty ties to a specific violation and approver.
- Automatic payroll integration eliminates manual memo-to-payroll communication errors.

---

### 4.2 Disciplinary Procedure

For serious violations that may result in suspension, written warning, or termination — as per Saudi Labor Law.

#### Workflow

```
Violation Reported
        │
        ▼
Investigation Record Created → Investigation Committee Formed
        │
        ▼
Employee Notified (Employee Warning Notice)
        │
        ▼
Hearing Held → Decision Documented
        │
        ▼
Disciplinary Decision Log Created:
  Outcome: Warning / Penalty / Suspension / Termination
        │
        ▼
Employee Notified of Decision
        │
        ▼
Employee Files Disciplinary Appeal (if contested)
        │
        ▼
Appeal Committee Reviews → Upholds or Overturns
        │
        ▼
If Termination: Termination Notice auto-linked → EOSB triggered
```

#### Full Lifecycle Example

> **Scenario:** Saad Al-Mutairi is caught falsifying overtime records. Management initiates formal procedure.

1. **Investigation Record** created, linked to Saad's employee file. Committee of 3 managers named.
2. **Employee Warning Notice** issued — Saad must respond within 5 working days.
3. Saad submits written response. Committee reviews.
4. **Disciplinary Procedure** updated with committee findings: violation confirmed.
5. **Disciplinary Decision Log**: Outcome = "Termination for cause" per Saudi Labor Law Art. 80.
6. Since termination is for cause (Art. 80), EOSB eligibility is zero.
7. Saad files a **Disciplinary Appeal** within 15 days. Appeals committee reviews and upholds the decision.
8. **Termination Notice** submitted. No EOSB generated (Art. 80 termination).
9. Exit clearance process begins.

#### Organizational Benefits

- Documents every step of the disciplinary process — critical protection in Ministry of HR disputes.
- Ensures Saudi procedural requirements (notification, hearing, response time) are followed before any dismissal.
- Reduces wrongful termination claims by creating an auditable paper trail.

---

### 4.3 Investigation Record

Documents the formal workplace investigation before a disciplinary decision is made.

**Key Fields:** Case description, Investigating officer, Committee members, Hearing date, Employee response, Committee findings.

Linked to: Disciplinary Procedure, Disciplinary Decision Log.

---

### 4.4 Employee Warning Notice

The formal written notice issued to an employee before a disciplinary hearing. Serves as proof that due process was followed.

**ERPNext Integration:** Creates a notification in the employee's portal. If **HR Letter** is used, a warning letter template can be auto-generated from this record.

---

### 4.5 Disciplinary Appeal

Allows the employee to formally contest a disciplinary decision.

**Key Fields:** Original decision reference, Grounds for appeal, Appeal committee, Hearing date, Final outcome.

**Legal Significance:** Saudi Labor Law requires employers to have an appeal mechanism. This document provides that mechanism and its audit record.

---

### 4.6 Absence Case

Tracks unauthorized absences — a frequent disciplinary trigger under Saudi Labor Law (unexcused absences: Article 80 allows termination after 20 cumulative days in a year or 10 consecutive days).

**Workflow:**

```
Daily Attendance Reconciliation identifies unexplained absence
        │
        ▼
Absence Case Created → HR Contacts Employee
        │
        ▼
Employee Provides Justification (approved/rejected)
        │
        ▼
If Unexcused: Absence Day Counter incremented
        │
        ▼
Threshold Alert at 10 / 15 / 20 days → Escalate to Disciplinary Procedure
```

---

## 5. Employee Lifecycle

### 5.1 Employee Onboarding

Manages the structured onboarding process for new hires from offer acceptance to first working day.

#### Workflow

```
Hiring Requisition Fulfilled → Candidate Selected
        │
        ▼
Employee record created in ERPNext
        │
        ▼
Employee Onboarding Document Created
  Tasks: Iqama Processing, IT Setup, Document Collection,
         Orientation, Policy Acknowledgement, Contract Signing
        │
        ▼
Assigned to HR + IT + Department Head
        │
        ▼
Each task checked off → Progress tracked
        │
        ▼
Employee Onboarding completed → Employee status: Active
```

#### Full Lifecycle Example

> **Scenario:** New hire Ali Al-Zahrani joins as Accountant.

1. **Employee Onboarding** created the day before Ali's start date.
2. Tasks auto-loaded from the onboarding template:
   - IT: Laptop, email, ERP access (assigned to IT department)
   - HR: Iqama submission, medical insurance enrollment, contract signing
   - Finance: Bank account details, salary setup
   - Management: Office tour, introduction meeting
3. Each assignee checks off their task within their deadline.
4. Ali signs the **Saudi Employment Contract** (linked to this onboarding record).
5. Ali acknowledges the **HR Policy Document** via **Policy Acknowledgement**.
6. All tasks complete → Onboarding closed. Ali's ERPNext Employee record status updated to Active.

---

### 5.2 Saudi Employment Contract

The legally required employment contract per Saudi Labor Law, capturing all mandatory fields.

**Key Saudi-Specific Fields:**
- Contract type (Definite / Indefinite term)
- Probation period (max 90 days, extendable once)
- Job title + work location
- Agreed salary components (basic + housing + transport)
- Notice period
- Non-compete clause (if applicable)

#### Scheduled Automation

`send_contract_expiry_alerts` runs daily — alerts HR when a definite-term contract is 30 / 60 days from expiry, so renewal or termination can be processed without a labor dispute.

**ERPNext Integration:** Saudi Employment Contract supplements ERPNext's standard Employee record, which does not store contract-specific fields.

---

### 5.3 Promotion & Transfer

Documents official role changes, salary increases, or inter-department/site transfers.

#### Workflow

```
Manager Proposes Promotion/Transfer
        │
        ▼
HR Reviews + Finance Confirms Budget
        │
        ▼
Promotion/Transfer Record Approved
        │
        ▼
ERPNext Employee record updated (designation, department, salary)
        │
        ▼
New Saudi Employment Contract (or amendment) issued
        │
        ▼
Effective Date tracked — payroll effective from that date
```

---

### 5.4 Performance Review

Structured annual or mid-year formal performance evaluation.

**Key Fields:** Review period, KPI scores, Competency scores, Development plan, Reviewer comments, Final rating.

**Integration:**
- Feeds into **Staff Rating** aggregate scoring
- Can trigger **Promotion/Transfer** if exceptional performance
- Linked to **Salary Adjustment** for merit increases

---

### 5.5 Staff Rating

Lightweight 360-degree peer/manager rating system, operating alongside formal Performance Review.

#### Workflow

```
Rating Period Defined (e.g., "2025-Q2")
        │
        ▼
Manager submits Downward rating for direct reports
Employee submits Upward rating for their manager
        │
        ▼
before_insert: rated_by_employee auto-set from session user
validate:
  - Period format validated (YYYY-MM)
  - Self-rating prevented
  - Rater relationship validated (Downward: rater must be direct manager)
  - Duplicate rating for same period prevented
        │
        ▼
get_rating_summary(employee) returns aggregated scores
  (individual rater identities never exposed — anonymized)
```

**API Endpoints:**
- `submit_rating(employee, rating_direction, rating_period, rating, review)` — whitelisted
- `get_rating_summary(employee)` — returns averages and counts, no rater identity
- `get_rateable_relationship(employee)` — returns which employees the current user can rate

**Organizational Benefits:**
- Anonymous aggregated ratings encourage honest feedback.
- Downward + upward ratings give HR a 360-view without complex survey tools.
- Directly feeds into end-of-year performance calibration.

---

### 5.6 Employee Grievance

Allows employees to formally raise workplace complaints — mandatory channel under KSA labor regulations.

#### Workflow

```
Employee Raises Grievance (confidential)
        │
        ▼
HR Reviews → Assigns to relevant manager/committee
        │
        ▼
Investigation / Resolution Actions Documented
        │
        ▼
Resolution communicated to employee
        │
        ▼
Employee accepts resolution → Case Closed
  OR
Employee escalates to Ministry of HR Labor Office
        │
        ▼
Labor Dispute Record Created
```

---

### 5.7 Exit Interview

Captures feedback from departing employees for retention intelligence.

**Key Fields:** Departure reason, Job satisfaction scores, Would you rejoin (Y/N), Suggestions for improvement, Interviewer notes.

**Integration:** Linked to **Termination Notice**. Insights feed into HR analytics.

---

### 5.8 Exit Clearance

Tracks that all company assets are returned and all obligations cleared before an employee's final settlement is released.

**Key Fields (checklist):**
- IT Equipment returned ✓
- Company vehicle returned ✓
- Uniforms/PPE returned ✓
- Access cards deactivated ✓
- System accounts disabled ✓
- Petty cash settled ✓
- Outstanding loan balance confirmed ✓

**Integration:** Exit Clearance must be "Completed" before the **End of Service Benefit** payment is released.

---

### 5.9 Termination Notice

The official record of an employment ending — whether resignation, expiry of contract, retirement, or dismissal.

#### Workflow

```
Termination Notice Created
  Type: Resignation / Termination / Contract Expiry / Retirement
        │
        ▼
Notice Period Calculated (from Saudi Employment Contract)
        │
        ▼
Submit → on_submit event fires:
  create_final_settlement_from_termination(doc)
        │
        ▼
End of Service Benefit record auto-created
Exit Interview triggered
Exit Clearance checklist initiated
        │
        ▼
Final working day confirmed → Employee status: Left
```

---

## 6. HR Documents & Communications

### 6.1 HR Letter & HR Letter Template

The HR Letter system allows HR to generate formally branded letters — offer letters, salary certificates, experience letters, NOC letters, warning letters — from reusable templates.

#### Workflow

```
HR Letter Template Created (one-time setup per letter type)
  Jinja variables: {{ employee.employee_name }}, {{ doc.salary }}, etc.
        │
        ▼
HR Letter Created → Template Selected → Employee Linked
        │
        ▼
Jinja rendering populates all variables with live data
        │
        ▼
HR Manager Reviews & Approves
        │
        ▼
PDF Generated → Printed on company letterhead / emailed to employee
        │
        ▼
Letter archived against employee record
```

#### Full Lifecycle Example

> **Scenario:** Bank of Saudi Arabia requests a salary certificate for Omar Al-Hamad's mortgage application.

1. HR opens **HR Letter** → Template: "Salary Certificate."
2. Employee: Omar Al-Hamad linked. System auto-fills:
   - Employee name, job title, department
   - Start date, employment type
   - Monthly salary (pulled from salary structure)
   - Company letterhead details
3. HR Manager approves and generates PDF.
4. PDF delivered to Omar within 1 business day.
5. Letter archived — retrievable if the bank requests a re-issue.

**Available Jinja Utilities (from hooks.py):**
- `get_eosb_amount(employee, end_date)` — for EOSB letters
- `get_annual_leave_entitlement(employee)` — for leave balance certificates
- `get_gosi_rates()` — for GOSI contribution letters

---

### 6.2 HR Policy Document

Stores the company's official HR policies (attendance policy, leave policy, code of conduct, harassment policy, etc.) as versioned documents.

**Key Fields:** Policy name, Version, Effective date, Document file, Applicable to (All / Specific department), Review date.

**Scheduled Automation:** `send_work_regulation_review_alerts` alerts the policy owner when a scheduled review date approaches, ensuring policies remain current and legally compliant.

---

### 6.3 Policy Acknowledgement

Tracks which employees have acknowledged which policy documents.

#### Workflow

```
HR Policy Document Published
        │
        ▼
Policy Acknowledgement requests sent to all applicable employees
        │
        ▼
Each Employee reads & acknowledges (digital signature / checkbox)
        │
        ▼
after_insert / on_update: update_policy_acknowledgement_summary fires
  → Summary record updated with % completion
        │
        ▼
**Policy Compliance Register** report shows per-policy % acknowledged
        │
        ▼
Non-acknowledgers flagged → HR follows up
```

**Organizational Benefits:**
- Proves legally that employees were informed of policies — critical in labor disputes.
- Ministry of HR audits often request proof of policy communication; this system provides it instantly.

---

### 6.4 Training Record

Documents employee training activities — internal workshops, external courses, certifications.

**Key Fields:** Employee, Training type, Provider, Date, Duration (hours), Certificate obtained, Cost.

**Integration with Training Agreement:** If the company sponsors external training, a **Training Agreement** is created alongside the Training Record, specifying repayment terms if the employee resigns within a defined period.

**Scheduled Automation:** `send_training_disclosure_due_alerts` — alerts HR when training obligation disclosures are due per KSA training compliance requirements.

---

### 6.5 Training Agreement

The legal agreement between company and employee when the company funds external training.

**Key Fields:** Training details, Total cost, Bond period (months), Repayment schedule if resigned early.

**Integration:** If the employee terminates during the bond period, the repayment amount is automatically included as a deduction in **End of Service Benefit** calculation.

---

## 7. Compliance & Regulatory

### 7.1 Labor Inspection

Tracks official Ministry of HR labor inspection visits — preparation, findings, corrective actions, and fines.

#### Workflow

```
Inspection Scheduled / Surprise Visit Occurs
        │
        ▼
Labor Inspection Record Created
  Date, Inspector name, Inspection scope
        │
        ▼
Per Violation Found: Labor Inspection Violation record linked
  Category, Description, Fine amount, Correction deadline
        │
        ▼
HR Action Plan Created for each violation
        │
        ▼
Inspection Fine SLA: tracks correction deadline
  Daily alert fires if deadline approaching/passed
        │
        ▼
Violation resolved → documented in HR Compliance Action Log
        │
        ▼
Follow-up inspection record linked (if inspector returns)
```

#### Organizational Benefits

- Centralizes all inspection history — year-over-year trend analysis possible.
- Proactive fine SLA alerts prevent the cascading effect of ignored violations (fines increase with repeated violations in KSA).
- Action plans assign responsibility and create accountability.

---

### 7.2 Work Regulation

Saudi Labor Law requires companies with 10+ employees to have an officially registered internal Work Regulation (نظام العمل الداخلي) approved by the Ministry of HR.

**Key Fields:** Document version, Ministry approval date, Expiry date, Contents (structured sections), Acknowledgement status.

**Scheduled Automation:** `send_work_regulation_review_alerts` — alerts 60 days before the Work Regulation's renewal date.

**Compliance Hook:** `validate_compliance_doc` runs on every save — ensures required sections and approval fields are present before the document can be submitted.

---

### 7.3 Saudi Regulatory Task

A task management layer for tracking recurring Saudi HR compliance obligations (e.g., GOSI monthly submission, Nitaqat quarterly check, WPS monthly filing).

**Key Fields:** Task name, Frequency, Due date, Assigned to, Status, Evidence attachment.

Works alongside **Ministry Filing Tracker** for structured compliance calendar management.

---

### 7.4 Nitaqat Record

Nitaqat is KSA's Saudization quota program. Companies are classified into Platinum/Green/Yellow/Red bands based on the ratio of Saudi nationals to total employees.

#### Workflow

```
Monthly: HR calculates current Saudi/Total employee ratio
        │
        ▼
Nitaqat Record Created → Current band assessed
        │
        ▼
If Yellow/Red: Alert to HR + Management
        │
        ▼
Hiring Requisitions checked against Nitaqat requirements
  (New hires for certain roles must be Saudi nationals)
        │
        ▼
Quarterly Nitaqat Compliance Report generated for Absher/QIWA portal
```

**Organizational Benefits:**
- Yellow/Red Nitaqat bands block visa applications — proactive monitoring prevents disruption to expatriate workforce.
- Nitaqat band affects government service access — HR Suite makes band status visible to management in real time.

**Report:** **Nitaqat Compliance Report** — shows current band, headcount breakdown, Saudi ratio trend.

---

### 7.5 Work Injury & Safety

Documents workplace accidents and injuries per KSA Occupational Health & Safety requirements.

**Work Injury Key Fields:** Employee, Injury date, Nature of injury, Days of incapacity, Treatment cost, Investigation findings, Preventive measures.

**Safety Inspection and Risk Control:** Tracks workplace safety inspections, risk assessments, and control measures. Each **Safety Risk Control Item** records the specific hazard, risk level, and control action.

**Integration:** Serious injuries trigger notification to GOSI (who may apply the 2% workplace injury insurance). Costs link to ERPNext Accounting.

---

### 7.6 Work Permit / Iqama Management

Iqama is the residency permit for expatriate employees — mandatory for legal work in KSA.

#### Workflow

```
New Expat Employee Hired
        │
        ▼
Work Permit / Iqama record created
  Iqama number, Issue date, Expiry date, Profession on Iqama
        │
        ▼
Daily Scheduler: send_iqama_expiry_alerts
  90 days before expiry → Alert to HR
  30 days before expiry → Escalated Alert
  Weekly check for imminent expirations
        │
        ▼
HR initiates renewal via Absher (Saudi government portal)
Renewal date updated on record
        │
        ▼
Contract Expiry Report cross-checks Iqama validity vs. Employment Contract
```

**Report:** **Work Permit Expiry Report** — lists all expiring permits sorted by days remaining.

**Organizational Benefits:**
- Expired Iqama = immediate risk of fines (SAR 10,000+) and deportation. Automated alerts give 3+ months lead time.
- Centralized Iqama management replaces scattered Excel tracking.

---

### 7.7 Ministry Filing Tracker

Calendar-driven tracker for all mandatory Ministry of HR and GOSI filings.

**Examples of tracked filings:**
- GOSI monthly contribution (due by 15th of each month)
- Work Regulation renewal (annual)
- Nitaqat quarterly report
- Disabled employee quota report (annual)
- WPS monthly submission

**Automation:** `send_ministry_filing_due_alerts` — daily check, escalating alerts at 7, 3, and 1 day before each filing deadline.

---

### 7.8 Statutory HR Records Register

KSA Labor Law requires companies to maintain specific HR registers (attendance register, leave register, penalty register). This document tracks whether each mandated register is being maintained and is up to date.

---

### 7.9 Disability Employment Compliance

Saudi disability quota law requires companies with 25+ employees to employ at least 1% disabled persons.

**Key Fields:** Current disabled employee count, Total headcount, Quota %, Compliance status, Action plan.

**Automation:** `validate_compliance_doc` ensures the record is complete before saving.

---

### 7.10 Expat Work Authorization Control

Tracks authorizations required for specific roles that expatriates need (work permit profession alignment, restricted profession tracking per KSA Vision 2030 Saudization).

**Scheduled Automation:** `send_expat_authorization_due_alerts` — alerts when authorization renewals are due.

---

### 7.11 Special Employment Category Control

Manages employees in special regulatory categories: minors (under 18, restricted hours), domestic workers (different Labor Law), part-time workers, remote workers.

Each category has different legal obligations tracked here.

---

### 7.12 Working Time Compliance Check

Saudi Labor Law limits working hours to 8/day, 48/week (6 hours/day in Ramadan). This compliance check document records periodic audits of actual hours worked vs. legal limits.

---

### 7.13 Work Arrangement Control

Tracks flexible and non-standard work arrangements — remote work agreements, part-time schedules, compressed work weeks — ensuring each has documented approval and defined terms.

---

### 7.14 Holiday Leave Overlap Rule

Defines the company's rules for what happens when a public holiday falls during an employee's leave (common question in Saudi HR).

**KSA Default Rule:** Public holidays during annual leave are added back to the employee's leave balance.

This document allows HR to configure and document that rule per department or employee category, creating a consistent policy record.

---

### 7.15 Labor Dispute

When an employee escalates a grievance to the Ministry of HR Labor Courts.

#### Workflow

```
Employee Grievance unresolved
        │
        ▼
Employee files with Ministry of HR / HRDF / Labor Court
        │
        ▼
Labor Dispute Record Created
  Court reference, Hearing dates, Claims, Company position
        │
        ▼
Legal Representative Assigned
        │
        ▼
Hearing outcomes documented per session
        │
        ▼
Final Judgment → Comply / Appeal
        │
        ▼
If Compliance: Salary/EOSB adjustment processed
```

**Legal Reference Matrix:** A companion document that maps KSA Labor Law articles to company policies, allowing HR to quickly reference the applicable law for any dispute claim.

---

## 8. Recruitment

### 8.1 Hiring Requisition

Department heads submit a formal request to hire, which must be approved by HR and Finance before recruitment begins.

**Key Fields:** Department, Job title, Headcount requested, Budget line, Justification, Nitaqat check (Saudi national required?), Target start date.

**Integration:** Approved requisitions feed into **Candidate Profile** management.

---

### 8.2 Candidate Profile

Stores applicant details, interview feedback, offer details, and onboarding trigger.

**Workflow:**

```
Candidate Applied → Profile Created
        │
        ▼
Interview Stages (First / Technical / Final) documented
        │
        ▼
Offer extended → Offer details recorded
        │
        ▼
Offer Accepted → ERPNext Employee created
        │
        ▼
Employee Onboarding document auto-triggered
```

---

### 8.3 Recruitment Service Provider Compliance

Saudi companies frequently use recruitment agencies for expatriate hiring. This document tracks the compliance record of each recruitment service provider per Ministry of HR requirements.

**Key Fields:** Provider name, License number, Expiry date, Workers placed, Violations/Complaints record.

**Sub-documents:**
- **Recruitment Provider Branch Row** — branch offices of the provider
- **Recruitment Provider Violation Row** — documented violations
- **Recruitment Provider Complaint** — formal complaints raised

---

## 9. Reports

| Report | Description | Key Audience |
|---|---|---|
| Saudi Leave Balance Report | Real-time leave balances per employee with entitlement vs. taken | HR, Managers |
| GOSI Monthly Report | Per-employee GOSI contribution breakdown for portal upload | Payroll, Finance |
| WPS Submission Tracker | Monthly WPS filing status — on-time, pending, overdue | Payroll, Compliance |
| WPS Export Report | SIF file content for audit review | Finance, Audit |
| EOSB Calculation Report | EOSB amount per employee based on current service tenure | HR, Finance |
| Contract Expiry Report | Employment contracts expiring in the next 90/60/30 days | HR |
| Work Permit Expiry Report | Iqama/work permits expiring in the next 90/60/30 days | PRO, HR |
| Nitaqat Compliance Report | Current Saudization band + headcount ratio trend | HR, Management |
| Labor Inspection Tracker | Open violations + correction deadline status | Compliance, HR |
| Outstanding Employee Loans | Loan balances per employee | Finance |
| Loan Deduction Register | Monthly loan deduction history | Finance, Payroll |
| Monthly Loan Recovery Summary | Aggregate loan recovery per payroll cycle | Finance |
| Compliance Case Tracker | Open compliance action items + owners + deadlines | Compliance |
| Policy Compliance Register | Policy acknowledgement % per document | HR |
| Saudi Legal Review Queue | Documents requiring legal review | Legal, HR |
| Saudi Compliance Obligation Backlog | Overdue regulatory obligations | Compliance |
| Saudi Labor Coverage Matrix | Labor law coverage gaps analysis | Legal, HR |

---

## 10. ERPNext HRMS Integration Map

HR Suite is a **layered supplement** to ERPNext HRMS, not a replacement. The following table shows where each HR Suite document connects to standard ERPNext:

| HR Suite Document | Creates / Updates in ERPNext | Integration Mechanism |
|---|---|---|
| Saudi Annual Leave | Leave Application | Permission query override; balance sync |
| Saudi Sick Leave | Leave Application | Tiered pay via Salary Component |
| Maternity Paternity Leave | Leave Application | Leave Type mapping |
| Overtime Request | Journal Entry, Additional Salary | `on_submit` doc_event hook |
| Employee Penalty | Salary Slip deduction | Payroll deduction via Salary Adjustment |
| GOSI Contribution | Additional Salary (employee), Journal Entry (employer) | `on_submit` → `create_payroll_entries` |
| Saudi Monthly Payroll | Salary Slip, Payroll Entry | Bulk creation via Python API |
| Annual Leave Disbursement | Journal Entry | On submit |
| End of Service Benefit | Journal Entry | On submit |
| Employee Loan | Journal Entry | On disbursement |
| Employee Loan Installment | Additional Salary (deduction) | Monthly payroll pull |
| Salary Adjustment | Additional Salary | Linked to Salary Slip |
| Employee Onboarding | Employee (status update) | Task completion trigger |
| Termination Notice | Employee (status → Left) | `on_submit` doc_event |
| Staff Rating | (standalone, no ERPNext equivalent) | Custom |
| HR Letter | (standalone, uses Jinja from ERPNext data) | Jinja utilities |
| WPS Submission | (standalone, exports SIF) | Payroll Entry reference |

### ERPNext Documents Used (Not Replaced)

- **Employee** — Core HR record; HR Suite extends it via Custom Fields.
- **Leave Allocation** — ERPNext manages entitlement pools; HR Suite reads/decrements these.
- **Salary Structure / Salary Component** — Standard ERPNext; HR Suite generates Salary Slips using these.
- **Chart of Accounts** — All Journal Entries from HR Suite post to the standard ERPNext COA.
- **Cost Centre** — OT and payroll entries use ERPNext Cost Centres for departmental cost tracking.

---

## 11. System Roles & Permissions

HR Suite uses Frappe's role-based access with Saudi-specific row-level permission logic.

### Permission Query Conditions

The following doctypes use `permission_query_conditions` to automatically filter list views by role:

| Doctype | Employee sees | Manager sees | HR sees |
|---|---|---|---|
| Saudi Annual Leave | Own records only | Team records | All |
| Saudi Sick Leave | Own records only | Team records | All |
| Overtime Request | Own records only | Team records | All |
| Salary Adjustment | Own records only | Not exposed | All |
| Maternity Paternity Leave | Own records only | Team records | All |
| Special Leave | Own records only | Team records | All |

### Recommended Roles

| Role | Typical Assignment |
|---|---|
| HR Manager | Full access to all HR Suite doctypes |
| HR User | Create/edit leaves, penalties; view payroll |
| Leave Approver | Approve/reject leave requests for their team |
| Payroll Manager | Saudi Monthly Payroll, GOSI, WPS, EOSB |
| Compliance Officer | Labor inspection, regulatory tasks, Nitaqat |
| Employee Self Service | Own leave, own documents, own rating |

---

## 12. Scheduled Automations

All tasks are defined in `hooks.py` and managed by Frappe Scheduler.

### Daily Tasks (`scheduler_events.daily`)

| Task | Action |
|---|---|
| `send_iqama_expiry_alerts` | Alert HR for Iqama expiring in 90/30 days |
| `send_contract_expiry_alerts` | Alert HR for employment contracts expiring |
| `send_work_permit_expiry_alerts` | Alert PRO for work permit renewals due |
| `send_sick_leave_threshold_alerts` | Alert HR when employee approaches 30/90/120 sick day tiers |
| `send_probation_end_alerts` | Alert manager when probation period ends (confirm/extend/terminate) |
| `send_ministry_filing_due_alerts` | Alert compliance for upcoming ministry filing deadlines |
| `send_final_settlement_sla_alerts` | Alert finance if EOSB not paid within 5 days |
| `send_employee_document_custody_alerts` | Alert HR for document custody expiry |
| `send_inspection_fine_sla_alerts` | Alert compliance for approaching labor inspection violation deadlines |
| `send_wps_correction_due_alerts` | Alert payroll if WPS not submitted within 7 days |
| `send_work_regulation_review_alerts` | Alert HR for work regulation renewal dates |
| `send_expat_authorization_due_alerts` | Alert PRO for expat work authorization renewals |
| `send_training_disclosure_due_alerts` | Alert HR for training disclosure deadlines |

### Weekly Tasks (`scheduler_events.weekly`)

| Task | Action |
|---|---|
| `send_iqama_expiry_alerts` | Repeat of Iqama check for imminent expirations |

### Monthly Tasks (`scheduler_events.monthly`)

| Task | Action |
|---|---|
| `send_gosi_due_alerts` | Remind payroll to submit GOSI contribution (due 15th each month) |

---

*HR Suite — Saudi Arabia HR Management System | Developed by Enfono | siva@enfono.com*
