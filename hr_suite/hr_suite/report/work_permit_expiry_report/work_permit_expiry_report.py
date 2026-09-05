"""
Work Permit Expiry Report

Iqama / work-permit records expiring inside the alert window. The "days left"
columns are recomputed at run time — the stored values on the document are only
refreshed when the document is saved, so reading them back reports stale counts.
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, today


DEFAULT_ALERT_DAYS = 90


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Record"), "fieldtype": "Link", "options": "Work Permit Iqama", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 120},
		{"fieldname": "iqama_number", "label": _("Iqama No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "iqama_expiry_date", "label": _("Iqama Expiry"), "fieldtype": "Date", "width": 130},
		{"fieldname": "days_to_iqama_expiry", "label": _("Days Left"), "fieldtype": "Int", "width": 110},
		{"fieldname": "iqama_status", "label": _("Iqama Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "work_permit_number", "label": _("Permit No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "work_permit_expiry_date", "label": _("Permit Expiry"), "fieldtype": "Date", "width": 140},
		{"fieldname": "days_to_permit_expiry", "label": _("Permit Days"), "fieldtype": "Int", "width": 120},
		{"fieldname": "work_permit_status", "label": _("Permit Status"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	# Report filters arrive over HTTP as strings; int() raises ValueError on anything
	# non-numeric and took the whole report down with a traceback. cint() coerces.
	days = cint(filters.get("alert_days"))
	if days <= 0:
		days = DEFAULT_ALERT_DAYS
	cutoff = add_days(today(), days)

	conditions = ["docstatus = 1"]
	values = {"cutoff": cutoff}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("employee"):
		conditions.append("employee = %(employee)s")
		values["employee"] = filters["employee"]

	conditions.append(
		"(iqama_expiry_date <= %(cutoff)s OR work_permit_expiry_date <= %(cutoff)s)"
	)

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			name, employee, employee_name, nationality,
			iqama_number, iqama_expiry_date, iqama_status,
			work_permit_number, work_permit_expiry_date, work_permit_status
		FROM `tabWork Permit Iqama`
		{where}
		ORDER BY iqama_expiry_date ASC
		""",
		values,
		as_dict=True,
	)

	as_on = today()
	for row in rows:
		row["days_to_iqama_expiry"] = (
			date_diff(row["iqama_expiry_date"], as_on) if row.get("iqama_expiry_date") else None
		)
		row["days_to_permit_expiry"] = (
			date_diff(row["work_permit_expiry_date"], as_on) if row.get("work_permit_expiry_date") else None
		)

	return rows
