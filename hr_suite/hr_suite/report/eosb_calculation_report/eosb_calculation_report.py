"""
EOSB Calculation Report
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
		{"fieldname": "name", "label": _("Document"), "fieldtype": "Link", "options": "End of Service Benefit", "width": 160},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "joining_date", "label": _("Joining Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "termination_date", "label": _("Termination"), "fieldtype": "Date", "width": 120},
		{"fieldname": "years_of_service", "label": _("Years"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "termination_reason", "label": _("Reason"), "fieldtype": "Data", "width": 200},
		{"fieldname": "last_basic_salary", "label": _("Basic Salary"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "eosb_gross", "label": _("Gross EOSB"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "resignation_factor", "label": _("Factor"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "net_eosb", "label": _("Net EOSB"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "payment_status", "label": _("Payment"), "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("from_date"):
		conditions.append("termination_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("termination_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			name, employee, employee_name, joining_date, termination_date,
			years_of_service, termination_reason, last_basic_salary,
			eosb_gross, resignation_factor, net_eosb, payment_status
		FROM `tabEnd of Service Benefit`
		{where}
		ORDER BY termination_date DESC
		""",
		values,
		as_dict=True,
	)
