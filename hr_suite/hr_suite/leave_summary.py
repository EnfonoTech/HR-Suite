"""The employee's leave position, shown on the Leave Application so HR can check it before deciding.

HRMS shows only the current allocation period. HR also needs the whole picture since joining: who
the employee is, how long they have served, what each leave type has given and taken, the past
applications, and the leave-salary days earned, settled and still due (SFT, 27 Oct 2026).

Read-only: nothing here writes. Nothing here builds SQL from strings.
"""

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from hr_suite.hr_suite.leave_accrual import get_salary_days_balance

HISTORY_ROWS = 15


@frappe.whitelist()
def get_leave_summary(employee: str, as_on: str | None = None) -> dict:
	"""Employee details, leave taken and balance per type since joining, recent history and leave-salary days."""
	if not isinstance(employee, str) or not employee:
		frappe.throw(_("Employee is required"))
	frappe.has_permission("Employee", "read", doc=employee, throw=True)
	frappe.has_permission("Leave Application", "read", throw=True)

	as_on = getdate(as_on or nowdate())
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "designation", "department", "company", "date_of_joining", "status"],
		as_dict=True,
	)
	if not emp:
		frappe.throw(_("Employee {0} not found").format(employee))

	return {
		"employee": emp,
		"service": _service(emp.date_of_joining, as_on),
		"leave_types": _by_leave_type(employee, emp.date_of_joining, as_on),
		"history": _history(employee),
		"leave_salary": _leave_salary(employee),
	}


def _service(joined, as_on) -> dict:
	"""Service from joining to as_on, as years, months and days, and total days."""
	if not joined:
		return {}
	span = relativedelta(as_on, getdate(joined))
	return {
		"years": span.years,
		"months": span.months,
		"days": span.days,
		"total_days": date_diff(as_on, getdate(joined)) + 1,
	}


def _by_leave_type(employee, joined, as_on) -> list:
	"""Per leave type since joining: allocated, taken, pending approval, and the balance today."""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	since = getdate(joined) if joined else getdate("1900-01-01")
	allocated = frappe.get_all(
		"Leave Allocation",
		filters={"employee": employee, "docstatus": 1, "to_date": [">=", since]},
		fields=["leave_type", "sum(new_leaves_allocated) as days"],
		group_by="leave_type",
	)
	taken = frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "docstatus": 1, "status": "Approved", "to_date": [">=", since]},
		fields=["leave_type", "sum(total_leave_days) as days"],
		group_by="leave_type",
	)
	pending = frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "docstatus": 0, "status": "Open"},
		fields=["leave_type", "sum(total_leave_days) as days"],
		group_by="leave_type",
	)
	rows = {}
	for key, source in (("allocated", allocated), ("taken", taken), ("pending", pending)):
		for r in source:
			rows.setdefault(r.leave_type, {"leave_type": r.leave_type, "allocated": 0.0, "taken": 0.0, "pending": 0.0})
			rows[r.leave_type][key] = flt(r.days, 2)

	for leave_type, row in rows.items():
		try:
			row["balance"] = flt(get_leave_balance_on(employee, leave_type, as_on), 2)
		except Exception:
			row["balance"] = None  # no allocation period covers today: shown as a dash, never a guess
	return sorted(rows.values(), key=lambda r: r["leave_type"])


def _history(employee) -> list:
	return frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "docstatus": ["<", 2]},
		fields=["name", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
		order_by="from_date desc",
		limit=HISTORY_ROWS,
	)


def _leave_salary(employee) -> dict:
	"""Leave-salary days earned since joining, used by settlements, and the balance; and the settlements."""
	rows = frappe.get_all("Leave Accrual Ledger", filters={"employee": employee}, fields=["source", "salary_days"])
	earned = sum(flt(r.salary_days) for r in rows if r.source != "Settlement")
	settled = -sum(flt(r.salary_days) for r in rows if r.source == "Settlement")
	settlements = frappe.get_all(
		"Leave Salary Settlement",
		filters={"employee": employee, "docstatus": 1},
		fields=[
			"name", "settlement_type", "leave_from_date", "leave_to_date", "salary_days_paid",
			"leave_salary_amount", "ticket_amount", "total_payable", "status", "rejoin_date",
		],
		order_by="leave_from_date desc",
	)
	return {
		"earned_days": flt(earned, 2),
		"settled_days": flt(settled, 2),
		"balance_days": get_salary_days_balance(employee),
		"settlements": settlements,
	}
