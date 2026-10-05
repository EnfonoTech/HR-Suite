"""Leave Accrual Ledger Report: where every day of every balance came from, with the running balance."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "name", "label": _("Entry"), "fieldtype": "Link", "options": "Leave Accrual Ledger", "width": 120},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 100},
		{"fieldname": "period_start", "label": _("Period Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "period_end", "label": _("Period End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_worked", "label": _("Days Worked"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "leave_days", "label": _("Leave Days"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "salary_days", "label": _("Salary Days"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "leave_balance", "label": _("Leave Running"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "salary_balance", "label": _("Salary Running"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "reference", "label": _("Reference"), "fieldtype": "Data", "width": 170},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	ledger = frappe.qb.DocType("Leave Accrual Ledger")
	query = (
		frappe.qb.from_(ledger)
		.select(ledger.name, ledger.employee, ledger.employee_name, ledger.source, ledger.period_start, ledger.period_end,
			ledger.days_worked, ledger.leave_days, ledger.salary_days, ledger.reference_doctype, ledger.reference_name,
			ledger.remarks, ledger.creation)
		.orderby(ledger.employee).orderby(ledger.period_end).orderby(ledger.creation)
	)
	for field in ("company", "employee", "source"):
		if filters.get(field):
			query = query.where(ledger[field] == filters[field])
	if filters.get("from_date"):
		query = query.where(ledger.period_end >= getdate(filters["from_date"]))
	if filters.get("to_date"):
		query = query.where(ledger.period_end <= getdate(filters["to_date"]))

	running, rows, last = {"leave": 0.0, "salary": 0.0}, [], None
	for entry in query.run(as_dict=True):
		if entry.employee != last:
			running, last = {"leave": 0.0, "salary": 0.0}, entry.employee
		running["leave"] += flt(entry.leave_days)
		running["salary"] += flt(entry.salary_days)
		entry["leave_balance"] = flt(running["leave"], 2)
		entry["salary_balance"] = flt(running["salary"], 2)
		entry["reference"] = " ".join(filter(None, [entry.reference_doctype, entry.reference_name]))
		rows.append(entry)
	return rows
