import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 160},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 140},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 120},
		{"fieldname": "loan_amount", "label": _("Loan Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "total_deducted", "label": _("Recovered"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "outstanding_balance", "label": _("Outstanding"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "next_due_date", "label": _("Next Due Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "next_installment_amount", "label": _("Next Installment"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = []
	values = {}
	if filters.get("company"):
		conditions.append("loan.company = %(company)s")
		values["company"] = filters["company"]
	where = "WHERE " + " AND ".join(conditions) if conditions else ""
	return frappe.db.sql(
		f"""
		SELECT
			loan.name AS loan,
			loan.employee,
			loan.employee_name,
			loan.company,
			loan.loan_amount,
			loan.total_deducted,
			loan.outstanding_balance,
			(
				SELECT child.due_date
				FROM `tabEmployee Loan Installment` child
				WHERE child.parent = loan.name AND child.deduction_status IN ('Pending', 'Deferred')
				ORDER BY child.due_date, child.idx
				LIMIT 1
			) AS next_due_date,
			(
				SELECT child.outstanding_amount
				FROM `tabEmployee Loan Installment` child
				WHERE child.parent = loan.name AND child.deduction_status IN ('Pending', 'Deferred')
				ORDER BY child.due_date, child.idx
				LIMIT 1
			) AS next_installment_amount,
			loan.status
		FROM `tabEmployee Loan` loan
		{where}
		ORDER BY loan.outstanding_balance DESC, loan.modified DESC
		""",
		values,
		as_dict=True,
	)