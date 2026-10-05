"""Leave Salary Settlements Due: annual leave about to start (or running) with nothing settled, and
settlements that still owe salary days.

Two kinds of row, told apart in the Reason column:

  * No settlement - an approved annual leave on a ledger-engine country that has no submitted
    Leave Salary Settlement yet.
  * Salary days still due - a settlement paid only part of the leave (below the barrier, or
    short of earned days); the rest is released by a further settlement once it is earned.

Each row says what the employee has earned today and whether the barrier is cleared, so HR can
see at a glance which ones can be paid now.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, today

from hr_suite.hr_suite.leave_accrual import get_salary_days_balance
from hr_suite.hr_suite.policy import LEDGER_ENGINE, get_policy


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "leave_application", "label": _("Leave Application"), "fieldtype": "Link", "options": "Leave Application", "width": 150},
		{"fieldname": "from_date", "label": _("Leave From"), "fieldtype": "Date", "width": 100},
		{"fieldname": "to_date", "label": _("Leave To"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_start", "label": _("Starts In (Days)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "leave_days", "label": _("Leave Days"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "salary_days_due", "label": _("Salary Days Due"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "earned_balance", "label": _("Earned Today"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "payable_now", "label": _("Payable Now (Days)"), "fieldtype": "Float", "precision": 2, "width": 130},
		{"fieldname": "barrier", "label": _("Barrier"), "fieldtype": "Data", "width": 200},
		{"fieldname": "settlement", "label": _("Settlement"), "fieldtype": "Link", "options": "Leave Salary Settlement", "width": 150},
	]


def _barrier(policy, employee, balance):
	joining = getdate(policy.date_of_joining) if policy.get("date_of_joining") else None
	service = date_diff(today(), joining) if joining else 0
	short = []
	if balance < flt(policy.leave_salary_min_earned_days):
		short.append(_("{0}/{1} earned days").format(flt(balance, 2), flt(policy.leave_salary_min_earned_days)))
	if service < policy.leave_salary_min_service_days:
		short.append(_("{0}/{1} service days").format(service, policy.leave_salary_min_service_days))
	return (not short), (_("Met") if not short else _("Short: ") + ", ".join(short))


def _paid_by_application():
	rows = frappe.get_all(
		"Leave Salary Settlement",
		filters={"docstatus": 1},
		fields=["name", "leave_application", "salary_days_paid", "creation"],
		order_by="creation asc",
	)
	paid, latest = {}, {}
	for row in rows:
		paid[row.leave_application] = paid.get(row.leave_application, 0.0) + flt(row.salary_days_paid)
		latest[row.leave_application] = row.name
	return paid, latest


def get_data(filters):
	within = int(filters.get("within_days") or 45)
	horizon = add_days(today(), within)

	la = frappe.qb.DocType("Leave Application")
	query = (
		frappe.qb.from_(la)
		.select(la.name, la.employee, la.employee_name, la.leave_type, la.from_date, la.to_date, la.total_leave_days)
		.where((la.docstatus == 1) & (la.status == "Approved") & (la.to_date >= getdate(today())) & (la.from_date <= getdate(horizon)))
		.orderby(la.from_date)
	)
	for field in ("company", "employee"):
		if filters.get(field):
			query = query.where(la[field] == filters[field])

	paid, latest = _paid_by_application()
	rows = []
	for leave in query.run(as_dict=True):
		policy = get_policy(leave.employee, on_date=leave.from_date)
		if not policy.get("has_policy") or policy.leave_accrual_engine != LEDGER_ENGINE:
			continue
		if leave.leave_type != policy.annual_leave_type:
			continue

		already = paid.get(leave.name, 0.0)
		due = max(flt(leave.total_leave_days) - already, 0.0)
		settled = leave.name in latest
		if settled and due <= 0:
			continue

		balance = get_salary_days_balance(leave.employee)
		ok, barrier = _barrier(policy, leave.employee, balance)
		rows.append(
			{
				"reason": _("Salary days still due") if settled else _("No settlement"),
				"employee": leave.employee, "employee_name": leave.employee_name, "leave_application": leave.name,
				"from_date": leave.from_date, "to_date": leave.to_date,
				"days_to_start": date_diff(leave.from_date, today()),
				"leave_days": flt(leave.total_leave_days, 2), "salary_days_due": flt(due, 2),
				"earned_balance": flt(balance, 2), "payable_now": flt(min(due, max(balance, 0.0)), 2) if ok else 0.0,
				"barrier": barrier, "settlement": latest.get(leave.name),
			}
		)
	return rows
