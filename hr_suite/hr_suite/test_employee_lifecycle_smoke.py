import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestEmployeeLifecycleSmoke(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.company = frappe.get_all("Company", pluck="name", limit_page_length=1)[0]
		suffix = frappe.generate_hash(length=8).lower()
		self.manager_email = f"saudi.lifecycle.manager.{suffix}@example.com"
		self.employee_email = f"saudi.lifecycle.employee.{suffix}@example.com"
		self.manager = make_employee(self.manager_email, company=self.company)
		self.employee = make_employee(self.employee_email, company=self.company)
		frappe.get_doc("User", self.manager_email).add_roles("Department Approver")
		frappe.get_doc("User", self.employee_email).add_roles("Employee Self Service")

		employee = frappe.get_doc("Employee", self.employee)
		employee.reports_to = self.manager
		if frappe.db.has_column("Employee", "leave_approver"):
			employee.leave_approver = self.manager_email
		if frappe.db.has_column("Employee", "expense_approver"):
			employee.expense_approver = self.manager_email
		employee.save(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_employee_lifecycle_contract_warning_leave_and_payroll(self):
		contract = frappe.get_doc(
			{
				"doctype": "Saudi Employment Contract",
				"employee": self.employee,
				"company": self.company,
				"contract_type": "Fixed Term",
				"contract_status": "Active",
				"start_date": "2026-01-01",
				"end_date": "2026-12-31",
				"basic_salary": 8000,
				"housing_allowance": 2000,
				"transport_allowance": 750,
				"other_allowances": 250,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(contract.total_salary, 11000)
		self.assertEqual(contract.probation_end_date, frappe.utils.add_days("2026-01-01", 90))

		warning = frappe.get_doc(
			{
				"doctype": "Employee Warning Notice",
				"employee": self.employee,
				"company": self.company,
				"warning_date": "2026-02-10",
				"warning_level": "First Written Warning",
				"issue_reason": "Repeated late arrival during probation review.",
				"corrective_action": "Manager follow-up and weekly attendance review.",
				"due_date": "2026-02-17",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(warning.status, "Issued")
		self.assertEqual(warning.employee, self.employee)

		with patch("frappe.workflow.doctype.workflow_action.workflow_action.enqueue"):
			leave = frappe.get_doc(
				{
					"doctype": "Saudi Annual Leave",
					"employee": self.employee,
					"company": self.company,
					"leave_start_date": "2026-03-01",
					"leave_end_date": "2026-03-03",
					"description": "Lifecycle manager permission check",
				}
			).insert(ignore_permissions=True)

		frappe.set_user(self.manager_email)
		self.assertTrue(frappe.has_permission("Saudi Annual Leave", "read", doc=leave))
		frappe.set_user("Administrator")

		payroll = frappe.get_doc(
			{
				"doctype": "Saudi Monthly Payroll",
				"company": self.company,
				"month": "March",
				"year": 2026,
				"posting_date": "2026-03-31",
				"employees": [
					{
						"employee": self.employee,
						"basic_salary": 8000,
						"housing_allowance": 2000,
						"transport_allowance": 750,
						"other_allowances": 250,
						"other_deductions": 150,
					}
				],
				"notes": "Lifecycle smoke payroll run.",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(payroll.total_employees, 1)
		self.assertEqual(payroll.total_gross, 11000)
		self.assertEqual(payroll.total_net_payable, 10850)

		payroll.flags.ignore_permissions = True
		payroll.submit()
		self.assertEqual(payroll.status, "Completed")
