"""Leave and Salary Days Balance: both balances of every employee, side by side.

Leave days live in HRMS (what Leave Application and payroll read). Leave-salary days live in
the Leave Accrual Ledger: earned by the monthly accrual and the opening balance, spent by
Leave Salary Settlements. The report also says whether the employee has cleared the barrier
(earned days and service from joining) that decides if leave salary can be paid today.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from frappe.query_builder.functions import Sum
from pypika.terms import Case

from hr_suite.hr_suite.policy import LEDGER_ENGINE, get_policy


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 130},
		{"fieldname": "country", "label": _("Country"), "fieldtype": "Data", "width": 70},
		{"fieldname": "engine", "label": _("Accrual Engine"), "fieldtype": "Data", "width": 120},
		{"fieldname": "service_months", "label": _("Service (Months)"), "fieldtype": "Int", "width": 100},
		{"fieldname": "band", "label": _("Band"), "fieldtype": "Data", "width": 120},
		{"fieldname": "leave_days_per_year", "label": _("Leave Days / Yr"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "salary_days_per_year", "label": _("Salary Days / Yr"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "leave_balance", "label": _("Leave Balance"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "salary_days_earned", "label": _("Salary Days Earned"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "salary_days_spent", "label": _("Salary Days Settled"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "salary_days_balance", "label": _("Salary Days Balance"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "barrier_met", "label": _("Leave Salary Payable"), "fieldtype": "Data", "width": 130},
		{"fieldname": "shortfall", "label": _("Shortfall"), "fieldtype": "Data", "width": 220},
	]


def _salary_day_totals(employees, as_on):
	"""(earned, settled) per employee: positive ledger salary days and the negative ones, one grouped query."""
	ledger = frappe.qb.DocType("Leave Accrual Ledger")
	earned = Case().when(ledger.salary_days > 0, ledger.salary_days).else_(0)
	spent = Case().when(ledger.salary_days < 0, -ledger.salary_days).else_(0)
	rows = (
		frappe.qb.from_(ledger)
		.select(ledger.employee, Sum(earned).as_("earned"),
			Sum(spent).as_("spent"))
		.where((ledger.employee.isin(employees)) & (ledger.period_end <= getdate(as_on)))
		.groupby(ledger.employee)
	).run(as_dict=True)
	return {r.employee: r for r in rows}


def get_data(filters):
	as_on = getdate(filters.get("as_on") or today())
	employee = frappe.qb.DocType("Employee")
	query = (
		frappe.qb.from_(employee)
		.select(employee.name, employee.employee_name, employee.department)
		.where(employee.status == "Active")
		.orderby(employee.employee_name)
	)
	for field in ("company", "department"):
		if filters.get(field):
			query = query.where(employee[field] == filters[field])
	if filters.get("employee"):
		query = query.where(employee.name == filters["employee"])
	employees = query.run(as_dict=True)
	if not employees:
		return []

	totals = _salary_day_totals([e.name for e in employees], as_on)
	rows = []
	for emp in employees:
		policy = get_policy(emp.name, on_date=as_on)
		ledger = policy.get("has_policy") and policy.leave_accrual_engine == LEDGER_ENGINE
		if filters.get("ledger_only") and not ledger:
			continue

		row = {"employee": emp.name, "employee_name": emp.employee_name, "department": emp.department,
			"country": policy.get("country_code"), "service_months": policy.get("service_months"),
			"engine": _("HR Suite Ledger") if ledger else _("HRMS Earned Leave") if policy.get("has_policy") else _("No policy")}
		if not policy.get("has_policy"):
			rows.append(row)
			continue

		annual = policy.get("annual") or frappe._dict()
		row.update(
			band=(policy.get("annual_band") or {}).get("label"),
			leave_days_per_year=flt(annual.get("leave_days_per_year")),
			salary_days_per_year=flt(annual.get("salary_days_per_year")),
			leave_balance=_leave_balance(emp.name, policy.annual_leave_type, as_on),
		)
		if ledger:
			total = totals.get(emp.name) or frappe._dict(earned=0, spent=0)
			earned, spent = flt(total.earned, 2), flt(total.spent, 2)
			balance = flt(earned - spent, 2)
			service_days = date_diff(as_on, getdate(policy.date_of_joining)) if policy.get("date_of_joining") else 0
			short = []
			if balance < flt(policy.leave_salary_min_earned_days):
				short.append(_("{0} of {1} earned days").format(balance, flt(policy.leave_salary_min_earned_days)))
			if service_days < policy.leave_salary_min_service_days:
				short.append(_("{0} of {1} service days").format(service_days, policy.leave_salary_min_service_days))
			row.update(salary_days_earned=earned, salary_days_spent=spent, salary_days_balance=balance,
				barrier_met=_("Yes") if not short else _("No"), shortfall=", ".join(short))
		rows.append(row)
	return rows


def _leave_balance(employee, leave_type, as_on):
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	try:
		return flt(get_leave_balance_on(employee, leave_type, as_on), 2)
	except Exception:
		return 0.0
