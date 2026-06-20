from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite import permissions as permissions_module


class TestAnnualLeaveFinancePermission(FrappeTestCase):
	def test_accounts_manager_can_access_finance_stage_annual_leave(self):
		doc = SimpleNamespace(employee="EMP-0001", workflow_state="Pending Finance Approval")

		with patch.object(permissions_module.frappe, "session", SimpleNamespace(user="finance@example.com")), patch.object(
			permissions_module.frappe, "get_roles", return_value=["Accounts Manager"]
		), patch.object(permissions_module.frappe.db, "get_value", return_value={}):
			self.assertTrue(permissions_module.has_annual_leave_permission(doc, user="finance@example.com"))

	def test_accounts_manager_cannot_access_draft_annual_leave(self):
		doc = SimpleNamespace(employee="EMP-0001", workflow_state="Draft")

		with patch.object(permissions_module.frappe, "session", SimpleNamespace(user="finance@example.com")), patch.object(
			permissions_module.frappe, "get_roles", return_value=["Accounts Manager"]
		), patch.object(permissions_module.frappe.db, "get_value", return_value={}):
			self.assertFalse(permissions_module.has_annual_leave_permission(doc, user="finance@example.com"))

	def test_accounts_manager_query_is_limited_to_finance_states(self):
		with patch.object(permissions_module.frappe, "session", SimpleNamespace(user="finance@example.com")), patch.object(
			permissions_module.frappe, "get_roles", return_value=["Accounts Manager"]
		), patch.object(permissions_module.frappe.db, "get_value", return_value=None), patch.object(
			permissions_module.frappe.db, "escape", side_effect=lambda value: f"'{value}'"
		):
			query = permissions_module.get_annual_leave_query(user="finance@example.com")

		self.assertIn("Pending Finance Approval", query)
		self.assertIn("Approved", query)
		self.assertNotIn("Pending HR Approval", query)