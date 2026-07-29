### HR Suite — Multi-Country HR Management System

A comprehensive HR management app for Frappe/ERPNext v15, covering **Saudi Arabia, UAE, Bahrain, India, and Oman**. Leave management, payroll, statutory contributions, government portal integrations, disciplinary procedures, and the full employee lifecycle — automatically governed by the employee's company country.

Set `Company.country` in ERPNext and HR Suite applies the correct statutory rules. No per-country configuration needed.

| Country | Statutory Scheme | Settlement | WPS |
|---|---|---|---|
| Saudi Arabia | GOSI | EOSB (Art. 84) | Mudad / SARIE |
| UAE | GPSSA / DEWS | Gratuity (Art. 51) | SIF-AE |
| Bahrain | SIO | Indemnity (Art. 116) | WPS-BH |
| India | EPF + ESI + PT | Gratuity Act 1972 | — |
| Oman | PASI | Indemnity | WPS-OM |

---

### Saudi Government Portal Integrations

HR Suite connects directly to Saudi government HR portals — eliminating manual uploads and providing a real-time audit trail inside ERPNext.

| Portal | Authority | What it covers | Trigger |
|---|---|---|---|
| **Muqeem** | MOI | Iqama verification, exit/re-entry status, final exit | Employee form buttons + daily scheduler |
| **Qiwa** | HRSD | Wathiqa labor contract verification, Nitaqat band sync, labor notices | Employee form buttons + monthly scheduler |
| **GOSI API** | GOSI | Employee registration/exit, contribution submission, employer account | Employee form + GOSI Contribution form + daily scheduler |
| **Mudad / WPS** | MHRSD | SAMA SIF file generation from Salary Slips, WPS submission, compliance status | Payroll Entry form buttons + monthly scheduler |

All portal calls are logged to a unified **Government Portal Sync Log** with full JSON response storage. Enable each integration in **Hr Suite Settings** with the respective API credentials.

---

### Salary Component Override

Every numeric field on the Salary Structure Assignment form gets clock (history) and pen (edit) icon buttons:

- **Pen** → set a new value with an effective date; future-dated changes queue as Pending and apply automatically on the scheduled date
- **Clock** → full history of every change for that component on that employee, filterable by year

---

### Key Feature Areas

- **Leave Management** — country-aware entitlements, sick leave tiers, maternity/paternity, Hajj leave
- **Payroll** — monthly payroll with statutory deductions auto-injected; WPS via Mudad
- **Statutory Contributions** — GOSI (SA), GPSSA (AE), SIO (BH), PASI (OM), EPF+ESI+PT (IN)
- **End-of-Service Settlement** — country-specific formula engine (EOSB, UAE Gratuity, Gratuity Act, Bahrain/Oman indemnity)
- **Employment Contracts** — multi-type contracts with probation, work permit, and country tracking
- **Disciplinary Management** — penalties, investigations, warnings, appeals, absence cases
- **Compliance & Regulatory** — 25+ compliance DocTypes; Nitaqat, WPS, Iqama, ministry filings, labor inspection
- **Employee Lifecycle** — hire-to-exit: onboarding → contract → performance → termination → EOSB → exit clearance
- **Arabic Print Formats** — contracts, EOSB letter, termination notice — RTL Arabic layout

---

---

### HR Suite vs HRMS — What HR Suite Adds

HR Suite is built on top of Frappe HRMS and extends it. The table below shows what HR Suite contributes beyond what HRMS already provides natively.

#### Country-Aware Automation
HRMS handles standard HR. HR Suite wraps every action with country-resolution logic — deriving the employee's work country from `Employee.work_country` → active `Country Employment Contract` → `Company.country` → `Hr Suite Settings.default_work_country` — and applies the matching statutory rules automatically.

| Capability | HRMS (native) | HR Suite (added) |
|---|---|---|
| Employee master | ✓ | Adds `work_country`, statutory group buttons (GOSI / DEWS / EPF) |
| Leave Application | ✓ | Country Config entitlement validation; sick-pay tier warning |
| Leave Allocation | ✓ | Monthly auto-allocator (annual_days ÷ 12) via scheduler |
| Salary Structure Assignment | ✓ | Min-wage enforcement per Country Config |
| Payroll Entry | ✓ | Auto-creates GOSI / DEWS / EPF+ESI / Statutory Contribution on submit |
| Salary Slip | ✓ | Injects pending overrides, loan deductions, penalty deductions |
| Appraisal | ✓ | Adds compliance rating, promotion flag, salary adjustment flag |
| Job Offer | ✓ | Auto-creates Employee record from offer on submit |
| Employee Separation | ✓ | Resolves country, runs settlement formula, auto-creates EOSB |
| Exit Interview | ✓ | Adds rehire flag, exit reason, completion sync to Exit Clearance |

#### Features Exclusive to HR Suite

**Statutory & Contributions**
- `GOSI Contribution` — SA: tracks employee + employer GOSI amounts per payroll; posts accounting entries
- `DEWS Contribution` — AE: employer DEWS fund contributions for expats
- `EPF ESI Contribution` — IN: EPF (12%/12%) and ESI (0.75%/3.25%) per payroll run
- `Statutory Contribution` — BH / OM and other countries
- `Nitaqat Record` — SA Saudization quota tracking with Qiwa sync
- `WPS Submission` — Gulf WPS SIF file generation, Mudad API submission

**Contracts & Documents**
- `Country Employment Contract` — multi-country contracts with type (Definite/Indefinite/Project), probation, country override, expiry alerts
- `Work Permit / Iqama` — residency document tracking, 90/30-day expiry alerts, Muqeem sync
- `Employee Document` — general document custody log with custodian and expiry tracking
- `HR Letter` / `HR Letter Template` — official HR correspondence generation (Arabic + English)

**Exit & Settlement**
- `End of Service Benefit` — country-specific EOSB formula engine (SA Art. 84, AE Art. 51/132, BH Art. 116, IN Gratuity Act, OM Art. 39–40)
- `Exit Clearance` — checklist-based clearance blocking final settlement payment
- `Termination Notice` — employer-initiated termination with auto-create Exit Interview + Exit Clearance + Final Settlement SLA
- `Final Settlement SLA` — legal payment deadline tracker (5-day SLA for SA)
- `Annual Leave Disbursement` — leave encashment calculation at exit

**Performance & Compensation**
- `Salary Adjustment` — structured salary change requests with approval workflow
- `Promotion Transfer` — position movement with appraisal linkage
- `Staff Rating` — multi-rater scoring tool separate from formal appraisal
- `Salary Component Override` — one-time bonus/deduction queuing for next payroll
- `Training Agreement` — training bond tracking (pro-rated recovery on early exit)
- `Training Record` — training participation and evidence log

**Employee Relations**
- `Employee Penalty` — penalty issuance with automatic payroll deduction on next run
- `Employee Grievance` (HRMS DocType, extended by HR Suite with channel, severity, SLA dates and investigation notes)
- `Investigation Record` — internal investigation documentation
- `Employee Warning Notice` — formal warning issuance and acknowledgement
- `Absence Case` — unexcused absence tracking with case resolution
- `Work Injury` — workplace injury recording linked to medical examination

**Disciplinary**
- `Disciplinary Procedure` — full disciplinary process tracking aligned to labor law
- `Disciplinary Decision Log` — decisions, evidence, and execution status
- `Disciplinary Appeal` — employee appeal management against disciplinary decisions
- `Disciplinary Violation Catalog` — configurable violation types with penalty matrix
- `Disciplinary Decision Catalog` — configurable decision templates per violation

**Compliance & Regulatory (25+ DocTypes)**
- `Work Regulation` — labor law compliance control records
- `Statutory HR Records Register` — mandatory register tracking
- `Ministry Filing Tracker` — ministry filing deadlines and evidence
- `Disability Employment Compliance` — quota tracking and accommodation records
- `Work Arrangement Control` — remote work and flexible arrangement compliance
- `Working Time Compliance Check` — hours, rest periods, overtime verification
- `Inspection Fine SLA` — labor inspection fine tracking and appeal management
- `Special Employment Category Control` — minors, women, protected categories
- `Holiday Leave Overlap Rule` — leave-holiday overlap configuration
- `Expat Work Authorization Control` — expat authorization validity monitoring
- `Training Disclosure Register` — statutory training obligation tracking
- `Recruitment Service Provider Compliance` — agency contract compliance
- `Recruitment Provider Complaint` — agency complaint recording
- `Safety Inspection and Risk Control` — workplace safety tracking
- `Disability Accommodation Catalog` — accommodation type configuration
- `Disability Accommodation Row` — accommodation detail record

**Government Portal Integrations (SA)**
- Muqeem API — Iqama verification, exit/re-entry, final exit initiation
- Qiwa API — Wathiqa contract verification, Nitaqat band sync, labor notices
- GOSI API — employee registration/exit, contribution submission
- Mudad / WPS API — SIF file generation, submission, compliance status

**Governance & Setup**
- `Country Config` — per-country statutory rates, settlement formula, leave entitlements, min wage, WPS format
- `HR Policy Document` — policy version management and acknowledgement governance
- `Policy Acknowledgement` — employee acknowledgement records with audit trail
- `Legal Reference Matrix` — labor article ↔ HR control mapping per country
- `Regulatory Task` — statutory HR task tracking with due dates and evidence
- `HR Compliance Action Log` — central compliance action log

**Scheduled Automation (16 schedulers)**
- Daily: Iqama / Work Permit expiry alerts (90/30 days), Contract expiry alerts, Probation end reminders, Sick leave threshold alerts, Final Settlement SLA overdue escalation, Muqeem expiry sync, GOSI sync, Salary override application, Ministry filing alerts, Inspection fine alerts, WPS correction alerts, Work regulation review alerts, Expat authorization alerts, Training disclosure alerts
- Weekly: Iqama expiry repeat reminder
- Monthly: Leave allocation (annual÷12), GOSI due alert, Nitaqat Qiwa sync, Mudad WPS sync

---

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app hr_suite
bench --site [your-site] migrate
bench build --app hr_suite
```

### Documentation

| Resource | Description |
|---|---|
| [HR_SUITE_DOCUMENTATION.md](HR_SUITE_DOCUMENTATION.md) | Full feature reference (18 sections) |
| [HR_SUITE_WORKFLOWS.md](HR_SUITE_WORKFLOWS.md) | Workflows, approval engine, implementation checklist |
| [WORKFLOW_TESTING.md](WORKFLOW_TESTING.md) | 13 end-to-end test cases including portal integrations |
| [LIFECYCLE_WORKFLOW.md](LIFECYCLE_WORKFLOW.md) | Hiring → payroll → exit walkthrough with test entries and country compliance |
| [docs/](docs/) | Vercel-deployed visual manager reference |

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/hr_suite
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
