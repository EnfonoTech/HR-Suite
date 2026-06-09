"""
Work Permit Expiry Report
"""
import frappe
from frappe import _
from frappe.utils import today, add_days


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
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
	days = int(filters.get("alert_days") or 90)
	cutoff = add_days(today(), days)

	conditions = ["docstatus = 1"]
	values = {"cutoff": cutoff, "today": today()}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters["company"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			employee, employee_name, nationality,
			iqama_number, iqama_expiry_date, days_to_iqama_expiry, iqama_status,
			work_permit_number, work_permit_expiry_date, days_to_permit_expiry, work_permit_status
		FROM `tabWork Permit Iqama`
		{where}
		AND (
			iqama_expiry_date <= %(cutoff)s
			OR work_permit_expiry_date <= %(cutoff)s
		)
		ORDER BY iqama_expiry_date ASC
		""",
		values,
		as_dict=True,
	)
