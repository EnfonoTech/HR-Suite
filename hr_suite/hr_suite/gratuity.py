"""End-of-service gratuity, driven by the Country Config policy tables.

One engine for every GCC country. What differs between them is DATA on Country Config --
accrual slabs, the resignation factors, the cap, the minimum service, the base wage, the
scheme cut-off -- not code. compute_gratuity() is pure (no database), so every rule is
unit-testable; calculate_for_employee() is the thin wrapper that gathers an employee's
dates, wage and unpaid leave and calls it.

Qualifying service = (days from joining to exit, up to the scheme cut-off where there is
one) minus unpaid leave and unpaid absence, divided by 365. Paid annual and sick leave
count as service and part years are pro-rated, as the policy spec requires.

Nothing here builds SQL from strings: the two queries use frappe.qb, and every f-string
or .format() below produces display text for the calculation notes only.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, cstr, date_diff, flt, getdate

from hr_suite.hr_suite.policy import get_country_policy
from hr_suite.hr_suite.utils import (
	country_name_to_code,
	get_employee_basic_salary_global,
	get_employee_salary_components,
	get_employee_work_country,
)

RESIGNATION = "Resignation"
TERMINATION = "Termination"
DISMISSAL = "Dismissal"
PARTIAL = "Partial Settlement"

# Kuwaiti dinar, Bahraini dinar and Omani rial are divided into 1000 fils/baisa.
THREE_DECIMAL_COUNTRIES = ("BH", "KW", "OM")

MONTHS = "Months of wage per year"
DAYS = "Days of wage per year"
WEEKS = "Weeks of wage per year"


def classify_exit(termination_reason: str) -> str:
	"""Map the many spellings of an exit reason onto Resignation / Termination / Dismissal / Partial."""
	text = cstr(termination_reason).strip().lower()
	if "partial" in text:
		return PARTIAL
	if "dismiss" in text:
		return DISMISSAL
	if "resign" in text:
		return RESIGNATION
	return TERMINATION


def _months_of_wage_per_year(unit: str, rate: float) -> float:
	"""Express a slab rate as months of wage per year of service. A month is 30 days, a week 7."""
	if unit == DAYS:
		return rate / 30.0
	if unit == WEEKS:
		return rate * 7.0 / 30.0
	return rate


def service_window_end(policy, joining, exit_date):
	"""Last date the employer-paid gratuity runs to, or None when there is no service in scope.

	Bahrain: employer gratuity covers service before 1 March 2024; from then on end-of-service
	is funded by SIO contributions. A joiner on or after the cut-off has nothing here.
	"""
	joining, exit_date = getdate(joining), getdate(exit_date)
	cutoff = getdate(policy.get("gratuity_scheme_end_date")) if policy.get("gratuity_scheme_end_date") else None
	if not cutoff:
		return exit_date
	if joining >= cutoff:
		return None
	return min(exit_date, cutoff)


def get_unpaid_days(employee: str, start, end) -> float:
	"""Unpaid leave plus unpaid absence between two dates (inclusive of both ends).

	Unpaid leave = approved Leave Applications whose Leave Type is leave-without-pay; a leave
	that straddles the window is clipped to it. Unpaid absence = submitted Absent attendance
	that no Leave Application already explains, so a day is never counted twice.
	"""
	if not employee or not start or not end or getdate(end) < getdate(start):
		return 0.0
	start, end = getdate(start), getdate(end)

	la = frappe.qb.DocType("Leave Application")
	lt = frappe.qb.DocType("Leave Type")
	leaves = (
		frappe.qb.from_(la)
		.join(lt)
		.on(la.leave_type == lt.name)
		.select(la.from_date, la.to_date, la.total_leave_days)
		.where(
			(la.employee == employee)
			& (la.docstatus == 1)
			& (la.status == "Approved")
			& (lt.is_lwp == 1)
			& (la.from_date <= end)
			& (la.to_date >= start)
		)
	).run(as_dict=True)

	unpaid = 0.0
	for leave in leaves:
		leave_from, leave_to = getdate(leave.from_date), getdate(leave.to_date)
		if leave_from >= start and leave_to <= end:
			unpaid += flt(leave.total_leave_days)  # whole leave inside the window: honours half days
		else:
			unpaid += date_diff(min(leave_to, end), max(leave_from, start)) + 1

	att = frappe.qb.DocType("Attendance")
	absent = (
		frappe.qb.from_(att)
		.select(Count(att.name).as_("days"))
		.where(
			(att.employee == employee)
			& (att.docstatus == 1)
			& (att.status == "Absent")
			& (att.attendance_date >= start)
			& (att.attendance_date <= end)
			& ((att.leave_application.isnull()) | (att.leave_application == ""))
		)
	).run(as_dict=True)
	unpaid += flt(absent[0].days) if absent else 0.0
	return unpaid


def compute_gratuity(
	policy,
	joining_date,
	exit_date,
	base: float,
	termination_reason: str,
	unpaid_days: float = 0,
	deductions: float = 0,
	is_national: bool = False,
	precision: int = None,
):
	"""Pure gratuity calculation from a Country Config policy. See the module docstring.

	`precision` defaults to the country's currency: 3 decimals for BH, KW and OM, else 2.
	"""
	if precision is None:
		precision = 3 if policy.get("country_code") in THREE_DECIMAL_COUNTRIES else 2
	joining, exit_date = getdate(joining_date), getdate(exit_date)
	if exit_date <= joining:
		frappe.throw(
			_(
				"Termination date must be after the joining date.<br>"
				"End of service date must be after the joining date."
			),
			title=_("Invalid Date"),
		)
	base = flt(base)
	if base <= 0:
		frappe.throw(_("Last basic salary must be greater than zero."), title=_("Missing Basic Salary"))
	deductions = flt(deductions)
	if deductions < 0:
		frappe.throw(_("EOSB deductions cannot be negative."), title=_("Invalid Deduction"))
	if not policy.get("gratuity_slabs"):
		frappe.throw(
			_("No gratuity slabs are configured on the Country Config for {0}.").format(
				policy.get("country_name") or policy.get("country_code")
			),
			title=_("Gratuity policy missing"),
		)

	exit_type = classify_exit(termination_reason)
	notes = []

	window_end = service_window_end(policy, joining, exit_date)
	calendar_days = date_diff(window_end, joining) if window_end else 0
	if window_end and window_end < exit_date:
		notes.append(
			_("Employer gratuity covers service up to {0}; later service is funded by contributions.").format(
				window_end
			)
		)
	if not window_end:
		notes.append(
			_("Joined on or after the scheme cut-off ({0}); no employer gratuity.").format(
				policy.get("gratuity_scheme_end_date")
			)
		)

	unpaid = min(flt(unpaid_days), calendar_days) if cint(policy.get("gratuity_unpaid_leave_deducted")) else 0.0
	qualifying_days = max(calendar_days - unpaid, 0)
	years = qualifying_days / 365.0

	breakdown = []
	gross_before_cap = 0.0
	blocked = ""

	if (
		is_national
		and policy.get("nationals_pension_scheme")
		and not cint(policy.get("gratuity_nationals_also_entitled"))
	):
		blocked = _("Nationals are covered by {0}; no employer gratuity.").format(policy.nationals_pension_scheme)
	elif years < flt(policy.get("gratuity_min_service_years")):
		blocked = _("Below the minimum service of {0} year(s).").format(policy.gratuity_min_service_years)

	if not blocked:
		for slab in sorted(policy.gratuity_slabs, key=lambda s: flt(s.get("from_years"))):
			lo, hi = flt(slab.get("from_years")), flt(slab.get("to_years"))
			upper = min(years, hi) if hi else years
			in_slab = max(upper - lo, 0.0)
			if in_slab <= 0:
				continue
			unit = slab.get("rate_unit") or MONTHS
			amount = flt(in_slab * _months_of_wage_per_year(unit, flt(slab.get("rate_value"))) * base, precision)
			gross_before_cap += amount
			breakdown.append(
				{
					"slab": f"{lo:g}-{hi:g}" if hi else f"{lo:g}+",
					"from_years": lo,
					"to_years": hi,
					"years_in_slab": flt(in_slab, 4),
					"rate": flt(slab.get("rate_value")),
					"rate_unit": unit,
					"amount": amount,
				}
			)
	else:
		notes.append(blocked)

	gross_before_cap = flt(gross_before_cap, precision)
	cap_amount = flt(flt(policy.get("gratuity_cap_months")) * base, precision)
	capped = bool(cap_amount and gross_before_cap > cap_amount)
	gross = cap_amount if capped else gross_before_cap
	if capped:
		notes.append(_("Capped at {0} months of wage.").format(policy.gratuity_cap_months))

	percent, label = 100.0, _("Full gratuity")
	if exit_type == RESIGNATION:
		for factor in sorted(policy.get("gratuity_resignation_factors") or [], key=lambda f: flt(f.get("from_years"))):
			lo, hi = flt(factor.get("from_years")), flt(factor.get("to_years"))
			if years >= lo and (not hi or years < hi):
				percent = flt(factor.get("payable_percent"))
				break
		label = _("Resignation after {0} yrs — {1}% of gratuity").format(f"{years:.1f}", f"{percent:g}")
	elif exit_type == DISMISSAL and cint(policy.get("gratuity_forfeited_on_dismissal")):
		percent, label = 0.0, _("Disciplinary dismissal — no gratuity")
	elif exit_type == PARTIAL:
		label = _("Partial settlement — gratuity accrued to date")

	net = flt(gross * percent / 100.0 - deductions, precision)
	if net < 0:
		frappe.throw(_("EOSB deductions exceed the payable amount."), title=_("Invalid Deduction"))

	first_slab = breakdown[0]["amount"] if breakdown else 0.0
	lines = [
		_("Qualifying service: {0} days ({1} calendar − {2} unpaid) = {3} years").format(
			f"{qualifying_days:g}", calendar_days, f"{unpaid:g}", f"{years:.2f}"
		),
		_("Wage base: {0}").format(f"{base:,.{precision}f}"),
	]
	for row in breakdown:
		unit_word = row["rate_unit"].split(" ")[0].lower()
		lines.append(
			f"{row['slab']} yrs: {row['years_in_slab']:.2f} × {row['rate']:g} {unit_word} = {row['amount']:,.{precision}f}"
		)
	lines += [f"{_('Gross')}: {gross:,.{precision}f}", f"{label} → {_('Net')}: {net:,.{precision}f}"] + notes

	return frappe._dict(
		formula="Slab-Policy",
		exit_type=exit_type,
		is_partial=int(exit_type == PARTIAL),
		calendar_days=calendar_days,
		unpaid_days=flt(unpaid, 2),
		qualifying_days=flt(qualifying_days, 2),
		years_of_service=flt(years, 2),
		base_amount=base,
		basic_salary=base,
		breakdown=breakdown,
		gross_before_cap=gross_before_cap,
		cap_amount=cap_amount,
		capped=int(capped),
		gross_entitlement=gross,
		factor=flt(percent / 100.0, 4),
		factor_label=label,
		deductions=deductions,
		net_entitlement=net,
		eosb_years_1_5=first_slab,
		eosb_years_above_5=flt(max(gross - first_slab, 0.0), precision),
		notes="\n".join(lines),
	)


def _wage_base(policy, employee: str) -> float:
	if policy.get("gratuity_base") == "Basic + Allowances":
		return flt(get_employee_salary_components(employee).get("total_salary"))
	return flt(get_employee_basic_salary_global(employee))


def _is_national(employee: str, country_code: str) -> bool:
	if not frappe.db.has_column("Employee", "nationality"):
		return False
	nationality = frappe.db.get_value("Employee", employee, "nationality")
	return bool(nationality) and country_name_to_code(cstr(nationality)) == country_code


def calculate_for_employee(employee: str, exit_date, termination_reason: str, deductions: float = 0, base_override=None):
	"""Gratuity for one employee, with their country policy, wage, nationality and unpaid leave."""
	country = get_employee_work_country(employee)
	policy = get_country_policy(country) if country else None
	if not policy:
		frappe.throw(
			_("No Country Config found for {0}; set up the country policy before calculating gratuity.").format(
				country or _("this employee's country")
			),
			title=_("Country policy missing"),
		)

	joining = frappe.db.get_value("Employee", employee, "date_of_joining")
	if not joining:
		frappe.throw(_("{0} has no Date of Joining.").format(employee))

	exit_date = getdate(exit_date)
	window_end = service_window_end(policy, joining, exit_date)
	unpaid = (
		get_unpaid_days(employee, joining, add_days(window_end, -1))
		if window_end and cint(policy.gratuity_unpaid_leave_deducted)
		else 0.0
	)
	base = flt(base_override) if flt(base_override) else _wage_base(policy, employee)

	result = compute_gratuity(
		policy,
		joining,
		exit_date,
		base,
		termination_reason,
		unpaid_days=unpaid,
		deductions=deductions,
		is_national=_is_national(employee, country),
		precision=3 if country in THREE_DECIMAL_COUNTRIES else 2,
	)
	result.country_code = country
	result.formula = policy.get("settlement_formula") or "Slab-Policy"
	return result
