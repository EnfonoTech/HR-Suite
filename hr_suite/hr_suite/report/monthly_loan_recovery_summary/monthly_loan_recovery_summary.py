import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "recovery_month", "label": _("Recovery Month"), "fieldtype": "Data", "width": 140},
		{"fieldname": "employee_count", "label": _("Employees"), "fieldtype": "Int", "width": 110},
		{"fieldname": "loan_count", "label": _("Loans"), "fieldtype": "Int", "width": 100},
		{"fieldname": "recovered_amount", "label": _("Recovered Amount"), "fieldtype": "Currency", "width": 160},
	]


def get_data(filters):
	conditions = ["child.deduction_status = %(deduction_status)s"]
	values = {"deduction_status": "Deducted"}
	if filters.get("from_date"):
		conditions.append("child.deduction_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("child.deduction_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	where = "WHERE " + " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT
			DATE_FORMAT(child.deduction_date, '%%Y-%%m') AS recovery_month,
			COUNT(DISTINCT loan.employee) AS employee_count,
			COUNT(DISTINCT loan.name) AS loan_count,
			SUM(child.deducted_amount) AS recovered_amount
		FROM `tabEmployee Loan Installment` child
		INNER JOIN `tabEmployee Loan` loan ON loan.name = child.parent
		{where}
		GROUP BY DATE_FORMAT(child.deduction_date, '%%Y-%%m')
		ORDER BY recovery_month DESC
		""",
		values,
		as_dict=True,
	)