"""
GOSI Monthly Report
"""
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 140},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 120},
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 100},
		{"fieldname": "year", "label": _("Year"), "fieldtype": "Int", "width": 80},
		{"fieldname": "contribution_base", "label": _("Base"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "employee_rate", "label": _("Emp. Rate %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "employer_rate", "label": _("Empr. Rate %"), "fieldtype": "Percent", "width": 140},
		{"fieldname": "employee_contribution", "label": _("Emp. Amount"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "employer_contribution", "label": _("Empr. Amount"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "total_contribution", "label": _("Total"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "payment_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("month"):
		conditions.append("month = %(month)s")
		values["month"] = filters["month"]
	if filters.get("year"):
		conditions.append("year = %(year)s")
		values["year"] = filters["year"]
	if filters.get("payment_status"):
		conditions.append("payment_status = %(payment_status)s")
		values["payment_status"] = filters["payment_status"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			employee,
			employee_name,
			nationality,
			month,
			year,
			contribution_base,
			employee_contribution_rate AS employee_rate,
			employer_contribution_rate AS employer_rate,
			employee_contribution,
			employer_contribution,
			total_contribution,
			payment_status
		FROM `tabGOSI Contribution`
		{where}
		ORDER BY year DESC, month, employee_name
		""",
		values,
		as_dict=True,
	)
