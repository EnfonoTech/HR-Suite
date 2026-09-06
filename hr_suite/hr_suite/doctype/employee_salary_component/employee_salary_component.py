# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmployeeSalaryComponent(Document):
	"""Read-only mirror of one salary component on the Employee record.

	Rows are rebuilt from the employee's current Salary Structure Assignment by
	`hr_suite.hr_suite.employee_salary.sync_employee_salary`. Nothing edits them
	by hand, which is why every field is read-only.
	"""

	pass
