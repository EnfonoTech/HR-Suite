"""Fill CTC on every employee with a submitted Salary Structure Assignment, once.

The salary mirror now writes CTC (the monthly package) whenever an assignment is submitted. Employees
assigned before that keep CTC 0 until their assignment changes, so this rebuilds their mirror once.
One employee whose structure cannot be evaluated is logged by the sync itself and never stops migrate.
"""

import frappe


def execute():
	from hr_suite.hr_suite.employee_salary import sync_employee_salary

	employees = frappe.get_all(
		"Salary Structure Assignment", filters={"docstatus": 1}, pluck="employee", distinct=True
	)
	for employee in employees:
		try:
			sync_employee_salary(employee)
		except Exception:
			frappe.log_error(title="HR Suite: CTC fill skipped for " + str(employee), message=frappe.get_traceback())
