### HR Suite — Saudi Arabia HR Management System

A comprehensive HR management app for Frappe/ERPNext v15, built for the Kingdom of Saudi Arabia. Covers leave management, payroll, disciplinary procedures, employee lifecycle, GOSI, WPS, Nitaqat compliance, and more — fully aligned with KSA Labor Law.

**📖 Documentation (HR Manager Guide):** https://hr-suite-docs.vercel.app

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app hr_suite
```

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
