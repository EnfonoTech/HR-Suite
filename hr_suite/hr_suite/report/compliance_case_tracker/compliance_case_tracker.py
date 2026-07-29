import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "absence_case", "label": _("Absence Case"), "fieldtype": "Link", "options": "Absence Case", "width": 170},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
		{"fieldname": "absence_type", "label": _("Absence Type"), "fieldtype": "Data", "width": 170},
		{"fieldname": "absence_status", "label": _("Absence Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "absence_days", "label": _("Days"), "fieldtype": "Int", "width": 80},
		{"fieldname": "investigation_record", "label": _("Investigation"), "fieldtype": "Link", "options": "Investigation Record", "width": 170},
		{"fieldname": "investigation_status", "label": _("Investigation Status"), "fieldtype": "Data", "width": 170},
		{"fieldname": "grievance", "label": _("Grievance"), "fieldtype": "Link", "options": "Employee Grievance", "width": 160},
		{"fieldname": "grievance_status", "label": _("Grievance Status"), "fieldtype": "Data", "width": 160},
		{"fieldname": "action_log", "label": _("Compliance Action"), "fieldtype": "Link", "options": "HR Compliance Action Log", "width": 180},
		{"fieldname": "action_status", "label": _("Action Status"), "fieldtype": "Data", "width": 150},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("ac.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("ac.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("status"):
		conditions.append("ac.status = %(status)s")
		values["status"] = filters["status"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			ac.name AS absence_case,
			ac.employee,
			ac.employee_name,
			ac.company,
			ac.absence_type,
			ac.status AS absence_status,
			ac.absence_days,
			ir.name AS investigation_record,
			ir.status AS investigation_status,
			eg.name AS grievance,
			eg.status AS grievance_status,
			cal.name AS action_log,
			cal.status AS action_status
		FROM `tabAbsence Case` ac
		LEFT JOIN `tabInvestigation Record` ir
			ON ir.reference_doctype = 'Absence Case' AND ir.reference_name = ac.name
		LEFT JOIN `tabEmployee Grievance` eg
			ON eg.raised_by = ac.employee AND eg.grievance_type = 'Attendance'
		LEFT JOIN `tabHR Compliance Action Log` cal
			ON cal.reference_doctype = 'Absence Case' AND cal.reference_name = ac.name
		{where}
		ORDER BY ac.modified DESC
		""",
		values,
		as_dict=True,
	)