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
