# HR Suite — Multi-Country HR Management System
## Comprehensive Feature Documentation

**Version:** 2.0 | **Platform:** Frappe/ERPNext v15 | **Jurisdictions:** Saudi Arabia · UAE · Bahrain · India · Oman

---

## Table of Contents

1. [How Country Detection Works](#1-how-country-detection-works)
2. [Country Configuration](#2-country-configuration)
3. [Leave Management](#3-leave-management)
4. [Time & Attendance](#4-time--attendance)
5. [Payroll & Compensation](#5-payroll--compensation)
6. [Statutory Contributions](#6-statutory-contributions)
7. [End-of-Service Settlement](#7-end-of-service-settlement)
8. [Employment Contracts](#8-employment-contracts)
9. [Disciplinary Management](#9-disciplinary-management)
10. [Employee Lifecycle](#10-employee-lifecycle)
11. [HR Documents & Communications](#11-hr-documents--communications)
12. [Compliance & Regulatory](#12-compliance--regulatory)
13. [Frappe HRMS Integration](#13-frappe-hrms-integration)
14. [Saudi-Specific Modules](#14-saudi-specific-modules)
15. [Saudi Government Portal Integrations](#15-saudi-government-portal-integrations)
16. [Salary Component Override](#16-salary-component-override)
17. [India-Specific Modules](#17-india-specific-modules)
18. [UAE-Specific Modules](#18-uae-specific-modules)

---

## 1. How Country Detection Works

HR Suite automatically applies the correct jurisdiction rules — leave entitlements, statutory rates, settlement formula, WPS format, permit labels — based on where each employee works, **not** a global system setting.

### Resolution Order

```
1. Employee.work_country  (explicit HR override — highest priority)
        ↓ if blank
2. Active Country Employment Contract.work_country
        ↓ if none
3. Employee.company → Company.country → ISO-2 code
   "Saudi Arabia" → SA | "United Arab Emirates" → AE
   "Bahrain"      → BH | "India"                → IN | "Oman" → OM
        ↓ if company country not in supported list
4. Hr Suite Settings → Default Work Country  (admin fallback)
        ↓ if blank
   ""  (no statutory behaviour applied)
```

### Example — Single-Country Company

> Your company is registered in Frappe with `Country = India`. Every employee in that company automatically gets EPF+ESI deductions, Gratuity Act settlement, Indian leave types (Earned/Casual/Privilege/Sick), and state-wise Professional Tax slabs. No extra configuration needed beyond the standard Company setup.

### Example — Multi-Country Group

> Enfono Group has three Frappe companies: `Enfono KSA (Saudi Arabia)`, `Enfono UAE (United Arab Emirates)`, and `Enfono India (India)`. Each employee is linked to the company in their work location. HR Suite reads the company's country and applies the right statutory rules automatically. An employee on international assignment can have `work_country` set explicitly on their Employee record to override.

### Supported Jurisdictions

| Code | Country | Statutory Scheme | Settlement Formula | WPS |
|---|---|---|---|---|
| SA | Saudi Arabia | GOSI | EOSB (Art. 84) | SARIE |
| AE | United Arab Emirates | GPSSA / DEWS | UAE Gratuity (Art. 51) | SIF-AE |
| BH | Bahrain | SIO | Indemnity (Art. 116–117) | WPS-BH |
| IN | India | EPF + ESI + PT | Gratuity Act 1972 | N/A |
| OM | Oman | PASI | Indemnity (Oman Labour Law) | WPS-OM |

---

## 2. Country Configuration

**DocType:** `Country Config`

One record per country, seeded automatically on install. HR admins can edit rates when regulations change — changes take effect on the next payroll or settlement calculation.

### What each Country Config record controls

| Section | Fields |
|---|---|
| General | country_code, country_name, currency, is_active |
| Statutory | scheme, contribution_basis, ceiling, national/expat employee & employer rates |
| Settlement | formula, basis, years threshold, days/year below/above threshold, eligibility minimum, ceiling |
| Leave | child table: leave type name, days/year, gender, carry-forward, once-in-employment flag |
| Permits | primary permit label (Iqama/Emirates ID/CPR/ORC), expiry alert days, national ID label |
| Nationalization | scheme name (Nitaqat / Emiratisation / Bahrainisation / Omanisation) |
| WPS | mandatory flag, file format |
| Notice & Probation | default notice days for monthly/others staff, max probation days |

### Leave Types Seeded Per Country

**Saudi Arabia:** Annual Leave (21d/30d threshold at 5yr), Sick Leave (120d), Maternity (70d), Paternity (3d), Hajj (15d — once in employment), Iddah (130d — female only)

**UAE:** Annual Leave (30d), Sick Leave (90d), Maternity (60d), Paternity (5d), Bereavement (5d), Study Leave (10d — optional)

**Bahrain:** Annual Leave (30d), Sick Leave (55d), Maternity (60d), Paternity (1d), Hajj (14d — once in employment)

**India:** Earned Leave (15d, 30d carry-forward), Casual Leave (12d), Sick Leave (12d), Maternity (182d), Paternity (15d), Privilege Leave (15d, 45d carry-forward), Compensatory Off (optional)

**Oman:** Annual Leave (30d), Sick Leave (182d), Maternity (50d), Paternity (3d), Hajj (15d — once in employment), Study Leave (15d — optional)

---

## 3. Leave Management

### 3.1 Annual Leave

**DocType:** `Annual Leave`

Tracks annual leave requests. Days entitlement comes from the employee's Country Config.

- SA: 21d (< 5 yrs service) / 30d (≥ 5 yrs) per Article 109
- AE: 30 calendar days per UAE Labour Law
- BH/OM: 30 days
- IN: 15 Earned Leave days; carry-forward up to 30 days

Approval workflow: Employee → Manager → HR → Approved/Rejected

### 3.2 Sick Leave

**DocType:** `Sick Leave`

Country-aware sick leave with tiered pay rates:

| Country | Full Pay | Partial Pay | Unpaid |
|---|---|---|---|
| SA | 30 days (100%) | 60 days (75%) | 30 days |
| AE | 15 days | 30 days (50%) | 30 days |
| BH | 15 days | 20 days (50%) | 20 days |
| IN | 12 days | — | — |
| OM | 15 days | 20 days (50%) | remainder |

### 3.3 Special Leave / Maternity / Paternity

**DocTypes:** `Special Leave`, `Maternity Paternity Leave`

Gender-specific leaves (maternity, iddah) are shown only for eligible employees. All leave types from Country Config are available for allocation.

---

## 4. Time & Attendance

### 4.1 Overtime Request

**DocType:** `Overtime Request`

Records and approves overtime. On submit, creates a Journal Entry to post overtime liability. Rates configurable per country.

### 4.2 HR Shift Type / HR Shift Assignment

**DocTypes:** `HR Shift Type`, `HR Shift Assignment`

Named shifts (Day Shift, Night Shift, Rotating) with grace periods. Assigns employees to shifts. Attendance policy enforces late entry / early exit rules per shift.

---

## 5. Payroll & Compensation

### 5.1 Monthly Payroll

**DocType:** `Monthly Payroll`

Processes payroll per company with:
- Statutory deductions (GOSI for SA, EPF/ESI for IN — auto-injected)
- Sick leave pay deductions
- Loan EMI deductions
- Overtime additions
- Salary adjustments

Integrates with Frappe HRMS Salary Slip — deductions injected via `before_submit` hook.

### 5.2 Salary Adjustment

**DocType:** `Salary Adjustment`

One-time or recurring salary changes (increment, deduction, bonus). Requires HR Manager approval.

### 5.3 WPS Submission

**DocType:** `WPS Submission`

Wages Protection System file generation. Format auto-selected by employee's country:

| Country | Format | Mandatory |
|---|---|---|
| Saudi Arabia | SARIE | Yes |
| UAE | SIF-AE | Yes |
| Bahrain | WPS-BH | Yes |
| Oman | WPS-OM | Yes |
| India | N/A | No |

### 5.4 Employee Loan

**DocType:** `Employee Loan`

Tracks loans with an instalment schedule. Instalments deducted automatically during Monthly Payroll.

---

## 6. Statutory Contributions

### 6.1 Statutory Contribution — GCC Countries

**DocType:** `Statutory Contribution`

Covers GOSI (SA), GPSSA (AE), SIO (BH), PASI (OM) in a single unified DocType.

| Country | Scheme | National Emp | National Er | Expat Emp | Expat Er | Ceiling |
|---|---|---|---|---|---|---|
| SA | GOSI | 10% | 12% | 0% | 2% | SAR 45,000 |
| AE | GPSSA | 5% | 12.5% | 0% | 0% | — |
| BH | SIO | 7% | 12% | 1% | 3% | BHD 4,000 |
| OM | PASI | 7% | 10.5% | 0% | 0% | OMR 5,000 |

On submit → Journal Entry created (Expense Dr / Statutory Payable Cr). GL accounts searched by keyword from Chart of Accounts.

Bulk generation: `Statutory Contribution → Generate for Month` creates records for all employees in a company.

### 6.2 EPF ESI Contribution — India

**DocType:** `EPF ESI Contribution`

| Component | Rate | Basis | Notes |
|---|---|---|---|
| Employee EPF | 12% | EPF wage | EPF wage = basic, capped ₹15,000 |
| Employer PF | 3.67% | EPF wage | Credited to PF account |
| Employer EPS | 8.33% | EPF wage | Employee Pension Scheme |
| EDLI / Admin | 0.5% | EPF wage | Employer only |
| Employee ESI | 0.75% | Gross | Only if gross ≤ ₹21,000 |
| Employer ESI | 3.25% | Gross | Only if gross ≤ ₹21,000 |

UAN and ESIC numbers stored per record. Voluntary PF over ceiling supported.

### 6.3 DEWS Contribution — UAE (DIFC)

**DocType:** `DEWS Contribution`

DIFC Employee Workplace Savings. Employer contributes **5.83%** of gross monthly salary (21 days ÷ 12 months). Cumulative balance tracked per employee per record.

### 6.4 Professional Tax — India

**DocType:** `Professional Tax`

State-wise PT slabs supported for: Karnataka, Maharashtra, West Bengal, Tamil Nadu, Telangana, Andhra Pradesh, Kerala, Gujarat, Goa, Madhya Pradesh, Odisha.

PT amount calculated automatically from `(state, gross_salary)` → slab lookup.

---

## 7. End-of-Service Settlement

**DocType:** `End of Service Benefit`

Settlement calculated automatically based on the employee's country:

### Saudi Arabia — EOSB (Article 84)

- Rate: ½ month/yr (years 1–5), 1 month/yr (years 5+)
- Resignation < 2 yrs: no entitlement
- Resignation 2–10 yrs: 1/3 of calculated amount
- Resignation > 10 yrs: 2/3 of calculated amount
- Termination by employer / contract expiry / death: full amount

### UAE — Gratuity (Article 51 / 132, 2021 Labour Law)

- Years 1–5: 21 calendar days basic per year
- Years 5+: 30 calendar days basic per year + 21d/yr for first 5 years
- Cap: 2 years' total salary
- Resignation scaling: none (< 1yr), 1/3 (1–3yr), 2/3 (3–5yr), full (5+yr)

### India — Gratuity Act 1972

- Formula: (15 ÷ 26) × last basic salary × completed years
- Minimum 5 years continuous service required
- Statutory ceiling: ₹20,00,000

### Bahrain — Indemnity (Article 116–117)

- Years 1–3: ½ month basic per year
- Years 3+: 1 month basic per year
- Resignation: 50% of calculated indemnity

### Oman — Indemnity

- Years 1–3: 15 days basic per year (daily rate = basic ÷ 30)
- Years 3+: 1 month basic per year
- Resignation: 50% of calculated indemnity

---

## 8. Employment Contracts

### 8.1 Country Employment Contract (Global — Primary)

**DocType:** `Country Employment Contract`

The primary contract DocType for all countries. Naming series: `EMP-CON-.YYYY.-.####`

Key fields: employee, company, `work_country`, contract_type (Permanent/Fixed-Term/Part-Time/Seasonal/Casual), contract_status, start/end dates, probation dates, basic salary, housing/transport/other allowances, total salary, currency, permit type/number/expiry, passport number, visa type.

On submit:
- Deactivates prior active contracts for the same employee
- Syncs `work_country` to the Employee record (triggers country-aware rules everywhere)

### 8.2 Country Employment Contract (SA legacy)

**DocType:** `Country Employment Contract`

Saudi-specific contract with Iqama/visa fields. Existing records remain valid. New contracts should use `Country Employment Contract`.

---

## 9. Disciplinary Management

| DocType | Purpose |
|---|---|
| Employee Penalty | Financial penalty; JE created on submit |
| Disciplinary Procedure | Formal case with violation catalog link |
| Investigation Record | Internal investigation tied to a case |
| Employee Warning Notice | Written warning with acknowledgement |
| Disciplinary Appeal | Employee appeal of a decision |
| Absence Case | Unexplained absence tracking and escalation |

### Violation Categories

Pre-loaded: **Attendance · Work Organization · Safety · Conduct · Integrity**

Each category maps to standard violation descriptions and penalty tiers.

---

## 10. Employee Lifecycle

### Hire-to-Exit Flow

```
Job Opening → Job Applicant → Job Offer
        ↓  on_submit  (HRMS hook auto-triggers)
    Employee created
    work_country set from Company.country
        ↓  after_insert
    Leave allocations seeded from Country Config
    (Annual Leave, Sick Leave, Maternity, etc.)
        ↓
    Country Employment Contract
    Probation period tracked → alert on end date
        ↓
    Performance Review → Staff Rating
    (synced from HRMS Appraisal on submit)
        ↓
    Termination Notice submitted
    Final Settlement calculated by country formula
        ↓  Employee.status = "Left"
    Exit Clearance auto-created
    Final Settlement SLA reminder (30 days)
```

### Key DocTypes

| DocType | Purpose |
|---|---|
| Employee Onboarding | HRMS DocType — onboarding activities per template; auto-created from Candidate Profile |
| Promotion & Transfer | Promotion/transfer with salary adjustment |
| Performance Review | Periodic performance evaluation |
| Staff Rating | Rating record; synced from HRMS Appraisal |
| Employee Grievance | HRMS DocType — HR Suite adds the grievance-handling fields and approval workflow |
| Exit Interview | Structured exit questionnaire |
| Exit Clearance | Department-by-department clearance checklist |
| Termination Notice | Notice with reason; triggers settlement calculation |

---

## 11. HR Documents & Communications

| DocType | Purpose |
|---|---|
| HR Letter | Generated from Jinja2 template (offer, confirmation, experience) |
| HR Letter Template | Reusable template with employee field placeholders |
| HR Policy Document | Policy storage with effective date and version |
| Policy Acknowledgement | E-acknowledgement with timestamp log |
| Training Record | Training attendance and completion tracking |
| Training Agreement | Employer-funded training bond |

---

## 12. Compliance & Regulatory

| DocType | Countries | Purpose |
|---|---|---|
| Work Regulation | All | Labor law compliance checklist |
| Regulatory Task | All | Statutory task with due date and owner |
| Ministry Filing Tracker | All | Government filing deadline tracking |
| Statutory HR Records Register | All | Mandatory register maintenance log |
| Labor Inspection | All | Inspection visits, violations, responses |
| Inspection Fine SLA | All | Fine payment within statutory deadline |
| Disability Employment Compliance | All | PWD quota and accommodation tracking |
| Expat Work Authorization Control | All | Work permit authorization status |
| Special Employment Category Control | All | Minors, students, domestic workers |
| Working Time Compliance Check | All | Hours and overtime legal limits |
| Holiday Leave Overlap Rule | All | Holiday-to-leave conversion rules |
| Final Settlement SLA | All | 30-day settlement deadline reminder |
| Legal Reference Matrix | All | Law article → HR action mapping |
| Nitaqat Record | SA only | Saudi Saudization quota band |
| Work Permit / Iqama | SA only | Saudi Iqama tracking |
| GOSI Contribution | SA only | Legacy SA social insurance record |

---

## 13. Frappe HRMS Integration

HR Suite hooks into Frappe HRMS standard events automatically via `doc_events` in `hooks.py`:

| HRMS Event | HR Suite Action | Key Logic |
|---|---|---|
| `Job Offer → on_submit` | Creates Employee | `work_country` from Job Opening `custom_work_country` → branch keyword → Company.country |
| `Employee → after_insert` | Seeds leave allocations | Calls `seed_country_leave_types()` with Country Config |
| `Employee → on_update` (status=Left) | Triggers exit workflow | Auto-creates Exit Clearance + Final Settlement SLA |
| `Salary Slip → before_submit` | Injects statutory deductions | GOSI (SA), GPSSA/SIO/PASI (AE/BH/OM), EPF+ESI (IN) via Country Config rates |
| `Appraisal → on_submit` | Creates Staff Rating | Maps `total_score` to Staff Rating for EOSB multiplier |
| `Leave Application → validate` | Country leave validation | Warns if leave type not in Country Config; warns on sick-pay tier exhaustion |
| `Leave Allocation → on_submit` | Entitlement check | Compares allocated days against Country Config leave entitlement — warns on mismatch |
| `Salary Structure Assignment → on_submit` | Minimum wage check | Blocks submission if base salary < `minimum_wage` in Country Config |
| `Payroll Entry → on_submit` | Statutory contribution stub | Auto-creates GOSI Contribution (SA), EPF/ESI Contribution (IN), or Statutory Contribution (AE/BH/OM) |
| `Employee Separation → on_submit` | EOSB auto-calculation | Reads `reason_for_leaving` + `relieving_date` from Employee; runs `calculate_settlement()` for the country; creates End of Service Benefit record |

Salary Components (GOSI, EPF, ESI, SIO, PASI) are created automatically in Frappe HRMS if not present.

### Country Resolution Chain

Every hook resolves the employee's country via a 4-step chain (highest priority first):

1. `Employee.work_country` custom field (explicit HR override)
2. Active `Country Employment Contract.work_country`
3. `Employee.company → Company.country` (mapped to ISO-2 code)
4. `Hr Suite Settings.default_work_country` (global fallback)

This means setting `Company.country = "Saudi Arabia"` is enough for SA compliance — no per-employee configuration needed.

### Salary Slip Deduction Injection

When a Salary Slip is submitted, HR Suite injects the correct statutory deduction component automatically:

| Country | Scheme | Employee Rate | Employer Rate | Ceiling |
|---|---|---|---|---|
| SA | GOSI | 10% (national) / 0% (expat) | 12% / 2% | Per Country Config |
| AE | GPSSA or DEWS | Per Country Config | Per Country Config | Per Country Config |
| BH | SIO | Per Country Config | Per Country Config | Per Country Config |
| OM | PASI | Per Country Config | Per Country Config | Per Country Config |
| IN | EPF + ESI | 12% + 0.75% | 12% + 3.25% | ₹15,000 / ₹21,000 |

Rates are read from Country Config — change the config to change all future slips.

---

## 14. Saudi-Specific Modules

These modules are **Saudi Arabia only** — they represent genuinely Saudi concepts not applicable to other jurisdictions:

- **GOSI Contribution** — per-month SA social insurance record with direct API submission via GOSI integration
- **Nitaqat Record** — Saudization quota band classification (Platinum/Green/Yellow/Red) with live Qiwa sync
- **Work Permit / Iqama** — Iqama number, issue/expiry dates, renewal cost, status; daily expiry alerts; Muqeem verification
- **WPS via Mudad** — SAMA SIF salary file auto-generated from Salary Slips; submitted directly to Mudad portal
- **Country Employment Contract** — SA contract with Iqama/visa section (legacy; use Country Employment Contract for new records)
- **Arabic Print Formats** — Employment contracts (standard/part-time/seasonal/temporary), EOSB letter, termination notice — all in Arabic with RTL layout

---

---

## 15. Saudi Government Portal Integrations

All four portals share a unified **Government Portal Sync Log** (DocType) — every API call is recorded with portal name, operation, employee reference, status (Success / Failed / Partial), and the full JSON response. This gives a complete audit trail without leaving the HR system.

**Prerequisites:** Enable each integration in **Hr Suite Settings → (portal) section** and provide the API credentials. Buttons on forms only appear when the integration is enabled.

---

### 15.1 Muqeem — Ministry of Interior (Iqama / Residency)

**Integration file:** `integrations/muqeem.py`

Muqeem is the Saudi MOI platform for Iqama (residency permit) management. HR Suite connects via Bearer token authentication (establishment credentials exchange).

| Operation | Trigger | What it does |
|---|---|---|
| Verify Iqama | Employee form → **Muqeem → Verify Iqama** | Calls Muqeem API with Iqama number; updates Work Permit/Iqama record (expiry date, status, profession) |
| Exit Re-entry Status | Employee form → **Muqeem → Exit Re-entry Status** | Fetches active exit/re-entry visa; updates exit_reentry_visa_number + expiry on Work Permit record |
| Initiate Final Exit | Work Permit/Iqama form → **Muqeem → Initiate Final Exit** | Prompts for exit date + confirmation; posts final exit request to Muqeem |
| Sync Expiring Iqamas | **Daily scheduler** | Queries all Work Permit records expiring within 90 days; re-verifies each via Muqeem API |

**Credentials needed (Hr Suite Settings → Muqeem section):**
- Establishment ID (رقم المنشأة)
- Username
- Password (stored encrypted)
- API Base URL (default: `https://api.muqeem.sa/v1`)

---

### 15.2 Qiwa — Ministry of HR & Social Development

**Integration file:** `integrations/qiwa.py`

Qiwa is the HRSD platform for labor contracts (Wathiqa), Nitaqat (Saudization) compliance, and labor notices. Authentication uses OAuth2 client credentials; the access token is cached in Redis to avoid repeated auth calls.

| Operation | Trigger | What it does |
|---|---|---|
| Verify Wathiqa Contract | Employee form → **Qiwa → Verify Wathiqa Contract** | Calls Qiwa labor-contracts/verify for employee's Iqama; returns contract status, dates, salary |
| Labor Notices | Employee form → **Qiwa → Labor Notices** | Fetches open labor complaints/notices for the employee |
| Sync Nitaqat | Nitaqat Record form → **Qiwa → Sync from Qiwa** | Calls Qiwa Nitaqat status; updates band color + Saudization % on the Nitaqat Record; shows band in alert |
| Monthly Nitaqat Sync | **Monthly scheduler** | Loops all Saudi companies; refreshes each company's Nitaqat band from Qiwa |

**Credentials needed (Hr Suite Settings → Qiwa section):**
- Establishment ID
- Client ID (OAuth2)
- Client Secret (OAuth2, stored encrypted)
- API Base URL (default: `https://api.qiwa.info/v1`)

---

### 15.3 GOSI API — General Organization for Social Insurance

**Integration file:** `integrations/gosi_api.py`

Connects directly to the GOSI employer API to automate the monthly contribution cycle and employee registration/exit — eliminating manual portal uploads.

| Operation | Trigger | What it does |
|---|---|---|
| Register with GOSI | Employee form → **GOSI → Register with GOSI** | Posts employee (Saudi ID, DOJ, basic salary, job title) to GOSI members/register |
| GOSI Member Status | Employee form → **GOSI → GOSI Member Status** | Checks membership, contribution class, last contribution month |
| Deregister from GOSI | Employee form → **GOSI → Deregister from GOSI** | Dialog asks exit date + reason; posts deregistration — use on termination |
| Submit to GOSI | GOSI Contribution form → **GOSI Portal → Submit to GOSI** | Submits a single approved GOSI Contribution record; on success: sets payment_status = Paid, stores reference number |
| Check Member Status | GOSI Contribution form → **GOSI Portal → Check Member Status** | Shows membership status inline on the contribution record |
| Batch Submit | Via API: `submit_monthly_batch(company, month, year)` | Submits all Pending submitted contributions for a period in one batch call |
| Get Certificate | Via API: `get_contribution_certificate()` | Fetches GOSI clearance certificate URL |
| Employer Account | Daily scheduler via `sync_monthly_gosi` | Refreshes employer account status (balance, compliance) |

**Credentials needed (Hr Suite Settings → GOSI — API Integration section):**
- GOSI Establishment ID
- API Key / Bearer Token (stored encrypted)
- API Base URL (default: `https://api.gosi.gov.sa/v1`)

**Monthly GOSI workflow for HR Manager:**
1. Run payroll → Salary Slips submitted
2. Open each `GOSI Contribution` record (or use bulk generate) → Submit
3. Click **GOSI Portal → Submit to GOSI** on each submitted record
4. Reference number auto-stored; payment_status → Paid
5. Check `Government Portal Sync Log` filtered by GOSI for full audit trail

---

### 15.4 Mudad — Wage Protection System (WPS)

**Integration file:** `integrations/mudad.py`

Mudad is the Saudi WPS portal operated by Ministry of HR. HR Suite auto-builds the SAMA SIF (Salary Information File) from submitted Salary Slips and submits it to Mudad — replacing the manual spreadsheet-to-portal upload.

| Operation | Trigger | What it does |
|---|---|---|
| Preview WPS File | Payroll Entry (submitted) → **WPS/Mudad → Preview WPS File** | Builds SIF rows from Salary Slips — shows employee, IBAN, net salary table before sending |
| Submit WPS to Mudad | Payroll Entry → **WPS/Mudad → Submit WPS to Mudad** | Generates SIF + POSTs to Mudad `wps/submit`; returns reference number and status |
| Check WPS Status | Payroll Entry → **WPS/Mudad → Check WPS Status** | Queries Mudad for compliance status of the period (compliant / violation reason) |
| Sync Log | Payroll Entry → **WPS/Mudad → Sync Log** | Opens Government Portal Sync Log filtered by Mudad |
| Monthly sync | Monthly scheduler via `sync_wps_monthly` | Refreshes establishment WPS compliance history |

**Credentials needed (Hr Suite Settings → Mudad — Wage Protection System section):**
- Establishment ID / CR Number
- Employer Bank IBAN (appears in SIF as disbursement account)
- Employer Bank Code (SAMA routing code, e.g. 1060 for Al Rajhi)
- API Key / Bearer Token (stored encrypted)
- API Base URL (default: `https://api.mudad.com.sa/v1`)

**Monthly WPS workflow for Payroll Manager:**
1. Run `Payroll Entry` → submit all Salary Slips for the period
2. Open the submitted Payroll Entry
3. Click **WPS/Mudad → Preview WPS File** — review employee count and total net salary
4. Click **WPS/Mudad → Submit WPS to Mudad** → confirm → reference number returned
5. Click **WPS/Mudad → Check WPS Status** → verify `is_compliant = Yes`
6. Check `Government Portal Sync Log` (portal = Mudad) for the full API response

---

### 15.5 Government Portal Sync Log

**DocType:** `Government Portal Sync Log`

Every API call to Muqeem, Qiwa, GOSI, or Mudad is automatically recorded here. HR managers use this as the single audit trail for all government portal activity.

| Field | Purpose |
|---|---|
| Portal | Muqeem / Qiwa / GOSI / Mudad |
| Operation | Specific action (e.g. "Iqama Verify", "WPS Submit") |
| Employee | Linked employee (if applicable) |
| Reference No. | Iqama number, contract ID, period, establishment ID |
| Status | Success / Failed / Partial |
| Synced On | Timestamp |
| Response Data | Full JSON response from government API (for debugging) |

Filter examples:
- `Portal = GOSI, Employee = EMP-001` → all GOSI actions for one employee
- `Portal = Mudad, Status = Failed` → failed WPS submissions requiring retry
- `Portal = Muqeem, Operation = Iqama Verify` → all Iqama verifications this month

---

## 16. Salary Component Override

**DocType:** `Salary Component Override`  
**Integration:** Clock (🕐) and pen (✏) icons injected into every Currency/Float field on the Salary Structure Assignment form.

### How it works

On any Salary Structure Assignment form, every numeric field (basic salary, allowances, deductions) gets two icon buttons:

- **Clock icon** → opens a history dialog showing all past overrides for that component on that employee. A year dropdown filters the list.
- **Pen icon** → opens an edit dialog: shows the component name, current value (read-only), a date picker for "Effective From", a new value input, and a Notes field. On "Save & Submit":
  - If the effective date is today or earlier → the Salary Structure Assignment field is updated immediately; status = Applied
  - If the effective date is in the future → record saved with status = Pending; the daily scheduler (`apply_pending_salary_overrides`) applies it automatically on the effective date
  - Any prior open/pending overrides for the same component are marked Superseded with an end date

### Audit trail

Every override is a `Salary Component Override` record with:
- Employee, SSA link, component name, old value, new value
- Effective From / Effective Until dates
- Status (Pending → Applied → Superseded)
- Modified By user, Applied On timestamp, Notes

This gives payroll managers a complete history of every salary component change for any employee, queryable by year.

---

## 17. India-Specific Modules

- **EPF ESI Contribution** — Monthly EPF (12%+12% split) and ESI (0.75%+3.25%) with UAN/ESIC numbers per employee
- **Professional Tax** — 11-state PT slab engine; auto-calculates from gross salary
- **Gratuity** — Computed under Payment of Gratuity Act 1972 (15/26 × basic × years, ₹20L cap, 5yr minimum service)

---

## 18. UAE-Specific Modules

- **DEWS Contribution** — DIFC Employee Workplace Savings at 5.83% employer; cumulative balance per employee
- **GPSSA** — General Pension scheme for UAE nationals; rates in Country Config
- **UAE Gratuity** — 21/30 days/year formula with 2-year salary cap and resignation scaling
- **SIF-AE** — UAE WPS file format for Abu Dhabi and Dubai Wages Protection System

---

## Appendix: Custom Fields on Employee

| Fieldname | Label | Purpose |
|---|---|---|
| `work_country` | Work Country | ISO-2 override; if blank, derived from Company.country |
| `hr_suite_gosi_salary` | Statutory Contribution Base | Salary used for statutory calculation (GOSI/GPSSA/SIO/PASI/EPF) |
| `hr_suite_employee_type` | Employee Type | National / Expatriate — determines contribution rate tier |
| `hr_suite_documents` | Documents | Child table for employee documents (Iqama, passport, health card, etc.) |

---

*HR Suite — developed by Enfono. Contact: siva@enfono.com*
