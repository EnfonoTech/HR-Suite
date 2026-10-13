"""Leave Accrual Ledger Report: where every day of every balance came from, with the running balance.

One row per transaction, in date order per employee: the opening balance, each month's accrual,
leave taken, leave salary settled, adjustments, encashment. Leave taken and encashment are read
from the HRMS Leave Ledger Entry of the employee's annual leave type, so the leave running
balance here agrees with the Leave Balance report on any date.

The accruals themselves also top up an HRMS Leave Allocation, which is left out on purpose
(it would count every accrued day twice).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

TAKEN = "Leave Taken"
ENCASHED = "Leave Encashment"


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "name", "label": _("Entry"), "fieldtype": "Data", "width": 120},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "leave_type", "label": _("Leave Type"), "fieldtype": "Link", "options": "Leave Type", "width": 110},
		{"fieldname": "source", "label": _("Transaction"), "fieldtype": "Data", "width": 110},
		{"fieldname": "period_start", "label": _("Period Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "period_end", "label": _("Period End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_worked", "label": _("Days Worked"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "days_in", "label": _("Days In"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "days_out", "label": _("Days Out"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "leave_days", "label": _("Leave Days (Net)"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "leave_balance", "label": _("Leave Running"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "salary_days", "label": _("Salary Days"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "salary_balance", "label": _("Salary Running"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "reference_doctype", "label": _("Source Document Type"), "fieldtype": "Link", "options": "DocType", "width": 150},
		{"fieldname": "reference_name", "label": _("Source Document"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 170},
		{"fieldname": "reference", "label": _("Reference"), "fieldtype": "Data", "width": 170, "hidden": 1},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	ledger = frappe.qb.DocType("Leave Accrual Ledger")
	query = (
		frappe.qb.from_(ledger)
		.select(ledger.name, ledger.employee, ledger.employee_name, ledger.source, ledger.period_start, ledger.period_end,
			ledger.days_worked, ledger.leave_days, ledger.salary_days, ledger.reference_doctype, ledger.reference_name,
			ledger.remarks, ledger.creation)
	)
	for field in ("company", "employee"):
		if filters.get(field):
			query = query.where(ledger[field] == filters[field])
	if filters.get("source") and filters["source"] not in (TAKEN, ENCASHED):
		query = query.where(ledger.source == filters["source"])
	if filters.get("from_date"):
		query = query.where(ledger.period_end >= getdate(filters["from_date"]))
	if filters.get("to_date"):
		query = query.where(ledger.period_end <= getdate(filters["to_date"]))

	entries = [] if filters.get("source") in (TAKEN, ENCASHED) else query.run(as_dict=True)
	for entry in entries:
		entry["date"] = entry.period_end
		entry["leave_type"] = None

	if filters.get("source") in (None, "", TAKEN, ENCASHED):
		employees = {e.employee for e in entries} if filters.get("source") not in (TAKEN, ENCASHED) else None
		entries += _leave_taken(filters, employees)

	entries.sort(key=lambda e: (e.employee, getdate(e.date) if e.date else getdate("1900-01-01"), e.creation))

	running, rows, last = {"leave": 0.0, "salary": 0.0}, [], None
	for entry in entries:
		if entry.employee != last:
			running, last = {"leave": 0.0, "salary": 0.0}, entry.employee
		running["leave"] += flt(entry.leave_days)
		running["salary"] += flt(entry.salary_days)
		entry["days_in"] = flt(max(flt(entry.leave_days), 0), 2)
		entry["days_out"] = flt(abs(min(flt(entry.leave_days), 0)), 2)
		entry["leave_balance"] = flt(running["leave"], 2)
		entry["salary_balance"] = flt(running["salary"], 2)
		entry["reference"] = " ".join(filter(None, [entry.reference_doctype, entry.reference_name]))
		rows.append(entry)
	return rows


def _leave_taken(filters, employees):
	"""Leave taken and encashed, from the HRMS ledger, for the employees' annual leave type."""
	from hr_suite.hr_suite.policy import get_policy

	entry = frappe.qb.DocType("Leave Ledger Entry")
	query = (
		frappe.qb.from_(entry)
		.select(entry.name, entry.employee, entry.employee_name, entry.leave_type, entry.leaves, entry.from_date,
			entry.transaction_type, entry.transaction_name, entry.creation)
		.where((entry.docstatus == 1) & (entry.is_expired == 0) & (entry.is_carry_forward == 0))
		.where(entry.transaction_type.isin(["Leave Application", "Leave Encashment"]))
	)
	if filters.get("employee"):
		query = query.where(entry.employee == filters["employee"])
	elif employees is not None:
		if not employees:
			return []
		query = query.where(entry.employee.isin(list(employees)))
	if filters.get("source") == TAKEN:
		query = query.where(entry.transaction_type == "Leave Application")
	if filters.get("source") == ENCASHED:
		query = query.where(entry.transaction_type == "Leave Encashment")
	if filters.get("from_date"):
		query = query.where(entry.from_date >= getdate(filters["from_date"]))
	if filters.get("to_date"):
		query = query.where(entry.from_date <= getdate(filters["to_date"]))

	annual = {}
	out = []
	for row in query.run(as_dict=True):
		if row.employee not in annual:
			# Only an employee on the ledger engine has this report's balance to extend.
			on_ledger = frappe.db.exists("Leave Accrual Ledger", {"employee": row.employee})
			policy = get_policy(row.employee) if on_ledger else None
			annual[row.employee] = policy.get("annual_leave_type") if policy and policy.get("has_policy") else None
		if annual[row.employee] != row.leave_type:
			continue
		out.append(
			frappe._dict(
				name=row.name,
				employee=row.employee,
				employee_name=row.employee_name,
				leave_type=row.leave_type,
				source=TAKEN if row.transaction_type == "Leave Application" else ENCASHED,
				period_start=row.from_date,
				period_end=row.from_date,
				date=row.from_date,
				days_worked=0,
				leave_days=flt(row.leaves),
				salary_days=0,
				reference_doctype=row.transaction_type,
				reference_name=row.transaction_name,
				remarks="",
				creation=row.creation,
			)
		)
	return out
