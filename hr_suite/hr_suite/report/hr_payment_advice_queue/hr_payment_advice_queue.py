"""HR Payment Advice Queue: what is waiting on Finance, and what is still waiting on HR's approvers."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today

STAGES = {
	"Awaiting Payment": ("Approved", "Sent to Finance"),
	"Awaiting Approval": ("Pending Approval",),
	"Rejected": ("Rejected",),
	"All Open": ("Draft", "Pending Approval", "Approved", "Sent to Finance", "Rejected"),
}


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Advice"), "fieldtype": "Link", "options": "HR Payment Advice", "width": 150},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "age_days", "label": _("Days Waiting"), "fieldtype": "Int", "width": 100},
		{"fieldname": "payment_type", "label": _("Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 130},
		{"fieldname": "total_claimed", "label": _("Claimed"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_amount", "label": _("Sanctioned"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "approval_level", "label": _("Awaiting Level"), "fieldtype": "Int", "width": 100},
		{"fieldname": "awaiting", "label": _("Awaiting"), "fieldtype": "Link", "options": "User", "width": 160},
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 190},
	]


def get_data(filters):
	stage = filters.get("stage") or "Awaiting Payment"
	query_filters = {"status": ["in", list(STAGES.get(stage, STAGES["Awaiting Payment"]))], "docstatus": ["<", 2]}
	for key in ("company", "payment_type"):
		if filters.get(key):
			query_filters[key] = filters[key]

	rows = frappe.get_all(
		"HR Payment Advice",
		filters=query_filters,
		fields=[
			"name", "posting_date", "payment_type", "employee", "employee_name", "company", "total_claimed",
			"total_amount", "status", "approval_level", "approver_l1", "approver_l2", "source_doctype", "source_name",
		],
		order_by="posting_date asc, creation asc",
	)
	for row in rows:
		row["age_days"] = max(date_diff(today(), row.posting_date), 0)
		row["awaiting"] = (
			(row.approver_l2 if row.approval_level == 2 else row.approver_l1) if row.status == "Pending Approval" else None
		)
		row["source"] = " ".join(filter(None, [row.source_doctype, row.source_name]))
		row["total_claimed"] = flt(row["total_claimed"])
	return rows
