import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "installment_number", "label": _("Installment #"), "fieldtype": "Int", "width": 90},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "deduction_date", "label": _("Deduction Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "deducted_amount", "label": _("Deducted Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "payroll_reference", "label": _("Payroll"), "fieldtype": "Link", "options": "Saudi Monthly Payroll", "width": 150},
		{"fieldname": "deduction_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = ["child.deduction_status = 'Deducted"]
	values = {}
	if filters.get("employee"):
		conditions.append("loan.employee = %(employee)s")
		values["employee"] = filters["employee"]
	where = "WHERE " + " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT
			loan.name AS loan,
			loan.employee,
			loan.employee_name,
			child.installment_number,
			child.due_date,
			child.deduction_date,
			child.deducted_amount,
			child.payroll_reference,
			child.deduction_status
		FROM `tabEmployee Loan Installment` child
		INNER JOIN `tabEmployee Loan` loan ON loan.name = child.parent
		{where}
		ORDER BY child.deduction_date DESC, loan.employee_name ASC
		""",
		values,
		as_dict=True,
	)