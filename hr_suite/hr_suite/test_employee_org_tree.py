from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite import api as api_module


def _employee(**kwargs):
	defaults = {
		"designation": None,
		"department": None,
		"branch": "HQ",
		"company": "ACME",
		"reports_to": None,
		"user_id": None,
		"leave_approver": None,
		"expense_approver": None,
	}
	defaults.update(kwargs)
	return SimpleNamespace(**defaults)


class TestEmployeeOrgTree(FrappeTestCase):
	def test_get_employee_org_hierarchy_summary_counts_scope(self):
		rows = [
			_employee(name="EMP-CEO", employee_name="Aisha", department="Management"),
			_employee(
				name="EMP-HR-1",
				employee_name="Huda",
				department="HR",
				reports_to="EMP-CEO",
				leave_approver="huda@example.com",
			),
			_employee(name="EMP-HR-2", employee_name="Ali", department="HR", reports_to="EMP-HR-1"),
			_employee(
				name="EMP-FIN-1",
				employee_name="Mona",
				department="Finance",
				reports_to="EMP-CEO",
				expense_approver="mona@example.com",
			),
		]

		with patch.object(api_module, "_get_org_tree_scope_rows", return_value=rows), patch.object(
			api_module, "_has_org_tree_global_access", return_value=True
		):
			summary = api_module.get_employee_org_hierarchy_summary(company="ACME")

		self.assertEqual(summary["root_label"], "ACME")
		self.assertEqual(summary["employee_count"], 4)
		self.assertEqual(summary["department_count"], 3)
		self.assertEqual(summary["manager_count"], 2)
		self.assertEqual(summary["approver_count"], 2)

	def test_get_employee_org_tree_nodes_returns_department_roots(self):
		rows = [
			_employee(name="EMP-HR-1", employee_name="Huda", department="HR"),
			_employee(name="EMP-FIN-1", employee_name="Mona", department="Finance"),
		]

		with patch.object(api_module, "_get_org_tree_scope_rows", return_value=rows):
			nodes = api_module.get_employee_org_tree_nodes(parent=api_module.ORG_TREE_ROOT_VALUE, is_root=1)

		self.assertEqual([node["department_label"] for node in nodes], ["Finance", "HR"])

	def test_get_employee_org_tree_nodes_returns_department_employee_roots(self):
		rows = [
			_employee(name="EMP-HR-1", employee_name="Huda", department="HR"),
			_employee(name="EMP-HR-2", employee_name="Ali", department="HR", reports_to="EMP-HR-1"),
			_employee(name="EMP-HR-3", employee_name="Nora", department="HR", reports_to="EMP-CEO"),
		]

		with patch.object(api_module, "_get_org_tree_scope_rows", return_value=rows):
			nodes = api_module.get_employee_org_tree_nodes(parent="department::HR")

		self.assertEqual([node["employee"] for node in nodes], ["EMP-HR-1", "EMP-HR-3"])

	def test_get_employee_org_tree_nodes_returns_in_department_direct_reports(self):
		rows = [
			_employee(name="EMP-HR-1", employee_name="Huda", department="HR"),
			_employee(name="EMP-HR-2", employee_name="Ali", department="HR", reports_to="EMP-HR-1"),
			_employee(name="EMP-FIN-1", employee_name="Mona", department="Finance", reports_to="EMP-HR-1"),
		]

		with patch.object(api_module, "_get_org_tree_scope_rows", return_value=rows):
			nodes = api_module.get_employee_org_tree_nodes(parent="employee::EMP-HR-1")

		self.assertEqual([node["employee"] for node in nodes], ["EMP-HR-2"])