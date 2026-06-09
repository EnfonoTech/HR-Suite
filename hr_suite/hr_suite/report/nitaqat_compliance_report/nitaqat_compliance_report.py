"""
Nitaqat Compliance Report
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
		{"fieldname": "name", "label": _("Record"), "fieldtype": "Link", "options": "Nitaqat Record", "width": 140},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150},
		{"fieldname": "period_date", "label": _("Period"), "fieldtype": "Date", "width": 110},
		{"fieldname": "activity_sector", "label": _("Sector"), "fieldtype": "Data", "width": 150},
		{"fieldname": "total_employees", "label": _("Total"), "fieldtype": "Int", "width": 100},
		{"fieldname": "saudi_employees", "label": _("Saudi"), "fieldtype": "Int", "width": 100},
		{"fieldname": "non_saudi_employees", "label": _("Non-Saudi"), "fieldtype": "Int", "width": 120},
		{"fieldname": "saudization_percentage", "label": _("Saudization %"), "fieldtype": "Percent", "width": 140},
		{"fieldname": "required_saudization_percentage", "label": _("Required %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "nitaqat_category", "label": _("Category"), "fieldtype": "Data", "width": 160},
		{"fieldname": "compliance_status", "label": _("Compliance"), "fieldtype": "Data", "width": 150},
		{"fieldname": "gap_to_next_band", "label": _("Gap %"), "fieldtype": "Float", "precision": 2, "width": 100},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("from_date"):
		conditions.append("period_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("period_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	if filters.get("compliance_status"):
		conditions.append("compliance_status = %(compliance_status)s")
		values["compliance_status"] = filters["compliance_status"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			name, company, period_date, activity_sector,
			total_employees, saudi_employees, non_saudi_employees,
			saudization_percentage, required_saudization_percentage,
			nitaqat_category, compliance_status, gap_to_next_band
		FROM `tabNitaqat Record`
		{where}
		ORDER BY period_date DESC, company
		""",
		values,
		as_dict=True,
	)
