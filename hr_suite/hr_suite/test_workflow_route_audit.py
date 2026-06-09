from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite import api as api_module


class TestWorkflowRouteAudit(FrappeTestCase):
	def test_get_workflow_route_audit_extracts_annual_leave_route(self):
		with patch.object(api_module.frappe, "session", SimpleNamespace(user="Administrator")), patch.object(
			api_module.frappe.db, "exists", return_value=False
		):
			audit = api_module.get_workflow_route_audit(workflow_key="annual_leave")

		self.assertEqual(len(audit), 1)
		self.assertEqual(
			[step["allowed_role"] for step in audit[0]["approval_route"][:-1]],
			["Employee Self Service", "Department Approver", "HR Manager", "Accounts Manager"],
		)
		self.assertEqual(audit[0]["approval_route"][-1]["state"], "Approved")

	def test_get_workflow_route_audit_extracts_salary_adjustment_route(self):
		with patch.object(api_module.frappe, "session", SimpleNamespace(user="Administrator")), patch.object(
			api_module.frappe.db, "exists", return_value=False
		):
			audit = api_module.get_workflow_route_audit(workflow_key="salary_adjustment")

		self.assertEqual(
			[step["allowed_role"] for step in audit[0]["approval_route"][:-1]],
			["HR User", "Department Approver", "HR Manager"],
		)

	def test_get_workflow_route_audit_extracts_termination_route(self):
		with patch.object(api_module.frappe, "session", SimpleNamespace(user="Administrator")), patch.object(
			api_module.frappe.db, "exists", return_value=False
		):
			audit = api_module.get_workflow_route_audit(workflow_key="termination")

		self.assertEqual(
			[step["allowed_role"] for step in audit[0]["approval_route"][:-1]],
			["HR User", "HR Manager", "HR Manager"],
		)
		self.assertTrue(any(step["action"] == "Return" for step in audit[0]["alternate_transitions"]))