"""Monthly gratuity provision, per employee, and the finalisation at exit (SFT reply, section 10).

Every month each employee in service earns:  wage base / 30 x days per year / 12
where "days per year" comes from the Country Config gratuity slab for the service year the employee is in
(KSA: 15 days for the first five years, then 30), and the wage base is the Country Config gratuity base
(Basic, or Basic + Allowances), read from the Salary Structure Assignment. The full entitlement is accrued
during service; resignation and dismissal factors are applied only at exit, by the Gratuity Finalisation.

Accounting, one Journal Entry per company and month:
    Dr Gratuity Expense                              one line per employee
    Cr Gratuity Payable or Gratuity Provision        one line per employee, party = the employee
The credit account is Hr Suite Settings > Gratuity Monthly Credit, mapped per company in HR Account Mappings,
and must have Account Type = Payable so it can carry the employee.

Each month is recorded once per employee in the Gratuity Accrual ledger (with its Journal Entry), so the same
month is never provided twice; cancelling the Journal Entry removes its rows and the month can be posted again.
Amounts Finance booked by hand before the start date go in as one Opening row per employee, with no entry.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, flt, formatdate, get_first_day, get_last_day, getdate

from hr_suite.hr_suite.gratuity import MONTHS, _months_of_wage_per_year, _wage_base
from hr_suite.hr_suite.policy import get_country_policy
from hr_suite.hr_suite.utils import (
	ACCOUNT_PURPOSE_GRATUITY_EXPENSE,
	ACCOUNT_PURPOSE_GRATUITY_PAYABLE,
	ACCOUNT_PURPOSE_GRATUITY_PROVISION,
	get_employee_work_country,
	get_mapped_account,
	journal_entry_needs_approval,
)

LEDGER = "Gratuity Accrual"
SETTINGS = "Hr Suite Settings"
MONEY = 2
OPENING, MONTHLY, FINALISATION = "Opening", "Monthly", "Finalisation"


# ── settings and accounts ─────────────────────────────────────────────────────


def settings():
	start = frappe.db.get_single_value(SETTINGS, "gratuity_provision_start_date")
	# an empty Date on a Single can come back as 0001-01-01: that is "not set", not the year 1
	start = getdate(start) if start and getdate(start).year > 1900 else None
	return frappe._dict(
		start_date=start,
		credit_purpose=frappe.db.get_single_value(SETTINGS, "gratuity_monthly_credit") or ACCOUNT_PURPOSE_GRATUITY_PAYABLE,
		auto_post=cint(frappe.db.get_single_value(SETTINGS, "gratuity_auto_post")),
	)


def accounts(company, credit_purpose=None) -> frappe._dict:
	"""Expense, the monthly credit account and the payable for `company`; refuses what is not mapped or not Payable."""
	credit_purpose = credit_purpose or settings().credit_purpose
	out = frappe._dict(
		expense=get_mapped_account(company, ACCOUNT_PURPOSE_GRATUITY_EXPENSE, "Expense"),
		credit=get_mapped_account(company, credit_purpose, "Liability"),
		payable=get_mapped_account(company, ACCOUNT_PURPOSE_GRATUITY_PAYABLE, "Liability"),
		credit_purpose=credit_purpose,
	)
	needed = [(ACCOUNT_PURPOSE_GRATUITY_EXPENSE, out.expense), (credit_purpose, out.credit), (ACCOUNT_PURPOSE_GRATUITY_PAYABLE, out.payable)]
	missing = [purpose for purpose, account in needed if not account]
	if missing:
		frappe.throw(
			_("Map the gratuity accounts for {0} first: Hr Suite Settings > HR Account Mappings, purpose(s) {1}. "
			  "Nothing was posted.").format(company, ", ".join(_(p) for p in missing)),
			title=_("Gratuity Accounts Not Mapped"),
		)
	for purpose, account in needed[1:]:
		if frappe.get_cached_value("Account", account, "account_type") != "Payable":
			frappe.throw(
				_("{0} is mapped as {1} but its Account Type is not Payable, so it cannot carry the employee. Set "
				  "Account Type = Payable on it (Chart of Accounts). Nothing was posted.").format(account, _(purpose)),
				title=_("Gratuity Account Must Be Payable"),
			)
	return out


# ── the monthly figure ────────────────────────────────────────────────────────


def days_per_year(policy, service_years: float) -> float:
	"""Days of wage a year of service earns at this point of service, from the Country Config slabs."""
	per_month = flt(policy.get("gratuity_days_per_month")) or 30
	for slab in sorted(policy.get("gratuity_slabs") or [], key=lambda s: flt(s.get("from_years"))):
		lo, hi = flt(slab.get("from_years")), flt(slab.get("to_years"))
		if service_years >= lo and (not hi or service_years < hi):
			months = _months_of_wage_per_year(slab.get("rate_unit") or MONTHS, flt(slab.get("rate_value")), per_month)
			return flt(months * per_month, 4)
	return 0.0


def monthly_amount(policy, base: float, joining, period_start, period_end) -> frappe._dict:
	"""Provision for one employee for [period_start, period_end]: base / 30 x days per year / 12, pro rata for a
	part month (joining or leaving inside it)."""
	joining = getdate(joining)
	start, end = max(getdate(period_start), joining), getdate(period_end)
	month_days = date_diff(get_last_day(period_start), get_first_day(period_start)) + 1
	days_in = max(date_diff(end, start) + 1, 0)
	service_years = date_diff(end, joining) / 365.0
	per_year = days_per_year(policy, service_years)
	full = flt(base) / 30.0 * per_year / 12.0
	amount = flt(full * days_in / month_days, MONEY) if days_in < month_days else flt(full, MONEY)
	return frappe._dict(amount=amount, days_per_year=per_year, service_years=flt(service_years, 2), base=flt(base, MONEY))


def accrued_to_date(employee, on_date=None) -> float:
	filters = {"employee": employee}
	if on_date:
		filters["posting_date"] = ["<=", getdate(on_date)]
	return flt(sum(flt(a) for a in frappe.get_all(LEDGER, filters=filters, pluck="amount")), MONEY)


# ── posting a month ───────────────────────────────────────────────────────────


def _employees(company, start, end) -> list:
	return frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ["<=", end], "status": ["!=", "Inactive"]},
		or_filters=[["relieving_date", "is", "not set"], ["relieving_date", ">=", start]],
		fields=["name", "employee_name", "date_of_joining", "relieving_date"],
		order_by="name",
	)


@frappe.whitelist()
def preview(company: str, month_end: str) -> list:
	"""The Post Gratuity Provision dialog: what the month would post, per employee."""
	frappe.only_for(("HR Manager", "Accounts Manager", "System Manager"))
	return preview_month(company, month_end)


def preview_month(company, month_end) -> list:
	"""What posting the month would provide, per employee, without writing anything."""
	end = get_last_day(getdate(month_end))
	start = get_first_day(end)
	cfg = settings()
	rows = []
	for emp in _employees(company, start, end):
		from_date = max(start, getdate(emp.date_of_joining))
		if cfg.start_date and end < getdate(cfg.start_date):
			continue
		if cfg.start_date:
			from_date = max(from_date, getdate(cfg.start_date))
		to_date = min(end, getdate(emp.relieving_date)) if emp.relieving_date else end
		if to_date < from_date:
			continue
		row = frappe._dict(employee=emp.name, employee_name=emp.employee_name, period_start=from_date, period_end=to_date)
		if frappe.db.exists(LEDGER, {"employee": emp.name, "source": MONTHLY, "period_start": [">=", start], "period_end": ["<=", end]}):
			row.update(skip=_("already provided for this month"))
			rows.append(row)
			continue
		if frappe.db.exists("Gratuity Finalisation", {"employee": emp.name, "docstatus": 1}):
			row.update(skip=_("gratuity finalised"))
			rows.append(row)
			continue
		country = get_employee_work_country(emp.name)
		policy = get_country_policy(country) if country else None
		if not policy or not policy.get("gratuity_slabs"):
			row.update(skip=_("no gratuity slabs on the Country Config"))
			rows.append(row)
			continue
		base = _wage_base(policy, emp.name)
		if base <= 0:
			row.update(skip=_("no wage found on the salary assignment"))
			rows.append(row)
			continue
		figure = monthly_amount(policy, base, emp.date_of_joining, from_date, to_date)
		cap = flt(flt(policy.get("gratuity_cap_months")) * base, MONEY)
		if cap:
			figure.amount = flt(max(min(figure.amount, cap - accrued_to_date(emp.name)), 0), MONEY)
		row.update(figure)
		if row.amount <= 0:
			row.update(skip=_("nothing to provide"))
		rows.append(row)
	return rows


@frappe.whitelist()
def post_month(company: str, month_end: str) -> dict:
	"""Provide the month for every employee of `company`: one Journal Entry, one ledger row per employee."""
	frappe.only_for(("HR Manager", "Accounts Manager", "System Manager"))
	end = get_last_day(getdate(month_end))
	rows = [r for r in preview_month(company, end) if not r.get("skip")]
	if not rows:
		return {"journal_entry": None, "employees": 0, "amount": 0}
	acc = accounts(company)
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	lines = []
	for r in rows:
		debit = {"account": acc.expense, "debit_in_account_currency": r.amount, "user_remark": r.employee}
		if cost_center:
			debit["cost_center"] = cost_center
		lines.append(debit)
		lines.append({"account": acc.credit, "credit_in_account_currency": r.amount, "party_type": "Employee", "party": r.employee})
	total = flt(sum(r.amount for r in rows), MONEY)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": end,
			"user_remark": _("Gratuity provision {0} - {1} employee(s) - {2}").format(end.strftime("%B %Y"), len(rows), total),
			"accounts": lines,
		}
	)
	je.insert(ignore_permissions=True)
	if not journal_entry_needs_approval():
		je.submit()
	for r in rows:
		row = frappe.get_doc(
			{
				"doctype": LEDGER,
				"employee": r.employee,
				"source": MONTHLY,
				"posting_date": end,
				"period_start": r.period_start,
				"period_end": r.period_end,
				"amount": r.amount,
				"base_wage": r.base,
				"days_per_year": r.days_per_year,
				"service_years": r.service_years,
				"credit_account": acc.credit,
				"journal_entry": je.name,
			}
		)
		row.flags.from_hr_suite = True
		row.insert(ignore_permissions=True)
	return {"journal_entry": je.name, "employees": len(rows), "amount": total, "submitted": je.docstatus == 1}


def post_last_month():
	"""Scheduler, monthly: post last month for every company, only when Hr Suite Settings asks for it."""
	if not settings().auto_post:
		return
	month_end = get_last_day(add_months(getdate(), -1))
	for company in frappe.get_all("Company", pluck="name"):
		try:
			post_month(company, month_end)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), _("HR Suite: gratuity provision not posted for {0}").format(company))


def on_journal_entry_cancel(doc, method=None):
	"""A cancelled (or deleted) provision entry gives its months back, so they can be posted again."""
	if doc.doctype != "Journal Entry":
		return
	frappe.db.delete(LEDGER, {"journal_entry": doc.name, "source": MONTHLY})


# ── final payment goes through HR Payment Advice, never the payslip ──────────


def refuse_pay_via_salary_slip(doc, method=None):
	"""Gratuity is paid through the HR Payment Advice (section 10), so an HRMS Gratuity may not add it to a payslip."""
	if cint(doc.get("pay_via_salary_slip")):
		frappe.throw(
			_("Gratuity is paid through the Gratuity Finalisation and an HR Payment Advice, not on the salary slip. "
			  "Untick Pay via Salary Slip."),
			title=_("Gratuity Is Not Paid On The Payslip"),
		)
