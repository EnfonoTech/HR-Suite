from unittest.mock import patch

import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase


class TestLiveApprovalFlow(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.submitter_email = "saudi.leave.submitter@example.com"
		self.manager_email = "saudi.leave.manager@example.com"
		self.hr_email = "saudi.leave.hr@example.com"
		self.finance_email = "saudi.leave.finance@example.com"
		self.attach_print_patcher = patch("frappe.attach_print", return_value={})
		self.sendmail_patcher = patch("frappe.sendmail")
		self.attach_print_patcher.start()
		self.sendmail_patcher.start()
		frappe.set_user("Administrator")

		self._ensure_user(self.manager_email, "Department Approver")
		self._ensure_user(self.hr_email, "HR Manager")
		self._ensure_user(self.finance_email, "Accounts Manager")
		self.company = frappe.get_all("Company", pluck="name", limit_page_length=1)[0]

		self.manager_employee = make_employee(self.manager_email, company=self.company)
		self.employee = make_employee(self.submitter_email, company=self.company)

		frappe.get_doc("User", self.submitter_email).add_roles("Employee Self Service")
		frappe.get_doc("User", self.manager_email).add_roles("Department Approver")
		frappe.get_doc("User", self.finance_email).add_roles("Accounts Manager")

		employee_doc = frappe.get_doc("Employee", self.employee)
		employee_doc.reports_to = self.manager_employee
		employee_doc.leave_approver = self.manager_email
		employee_doc.expense_approver = self.manager_email
		employee_doc.save()

	def tearDown(self):
		frappe.set_user("Administrator")
		self.attach_print_patcher.stop()
		self.sendmail_patcher.stop()
		frappe.db.rollback()
		super().tearDown()

	def test_annual_leave_workflow_runs_submitter_manager_hr_path(self):
		with patch(
			"hr_suite.hr_suite.doctype.saudi_annual_leave.saudi_annual_leave.get_annual_leave_balance",
			return_value={"balance": 21},
		):
			frappe.set_user(self.submitter_email)
			leave = frappe.get_doc(
				{
					"doctype": "Saudi Annual Leave",
					"employee": self.employee,
					"company": frappe.db.get_value("Employee", self.employee, "company"),
					"department": frappe.db.get_value("Employee", self.employee, "department"),
					"leave_start_date": "2026-05-10",
					"leave_end_date": "2026-05-12",
					"description": "Workflow path verification",
				}
			).insert()

			self.assertEqual(leave.workflow_state, "Draft")
			apply_workflow(leave, "Submit Request")
			leave.reload()
			self.assertEqual(leave.workflow_state, "Pending Manager Approval")

			frappe.set_user(self.manager_email)
			self.assertTrue(frappe.has_permission("Saudi Annual Leave", "read", doc=leave))
			apply_workflow(leave, "Manager Approve")
			leave.reload()
			self.assertEqual(leave.workflow_state, "Pending HR Approval")

			frappe.set_user(self.hr_email)
			self.assertTrue(frappe.has_permission("Saudi Annual Leave", "read", doc=leave))
			apply_workflow(leave, "HR Approve")
			leave.reload()
			self.assertEqual(leave.workflow_state, "Pending Finance Approval")

			frappe.set_user(self.finance_email)
			self.assertTrue(frappe.has_permission("Saudi Annual Leave", "read", doc=leave))
			apply_workflow(leave, "Final Approve")
			leave.reload()

		self.assertEqual(leave.workflow_state, "Approved")
		self.assertEqual(leave.docstatus, 1)
		self.assertEqual(leave.status, "Approved")
		self.assertEqual(leave.approved_by, self.finance_email)

	def _ensure_user(self, email, *roles):
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@", 1)[0],
					"new_password": "password",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)

		if roles:
			user.add_roles(*roles)

		return user