from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.report.saudi_labor_coverage_matrix import saudi_labor_coverage_matrix as coverage_module


class TestSaudiLaborCoverageMatrix(FrappeTestCase):
	def test_validate_special_leave_coverage_returns_implemented_for_expected_options(self):
		item = {"checks": [{"kind": "doctype", "name": "Special Leave"}]}
		options = (
			"Hajj Leave"
			"Bereavement Leave"
			"Marriage Leave"
		)
		with patch.object(coverage_module, "run_check", return_value=True), patch.object(
			coverage_module.frappe.db, "get_value", return_value=options
		):
			self.assertEqual(coverage_module.validate_special_leave_coverage(item), coverage_module.IMPLEMENTED)

	def test_validate_gosi_coverage_returns_implemented_with_scheduler_and_status_alert(self):
		item = {"checks": [{"kind": "doctype", "name": "GOSI Contribution"}]}
		with patch.object(coverage_module, "run_check", return_value=True), patch.object(
			coverage_module, "scheduler_method_exists", return_value=True
		), patch.object(coverage_module.frappe.db, "exists", return_value=True):
			self.assertEqual(coverage_module.validate_gosi_coverage(item), coverage_module.IMPLEMENTED)

	def test_validate_gosi_coverage_returns_partial_without_scheduler(self):
		item = {"checks": [{"kind": "doctype", "name": "GOSI Contribution"}]}
		with patch.object(coverage_module, "run_check", return_value=True), patch.object(
			coverage_module, "scheduler_method_exists", return_value=False
		), patch.object(coverage_module.frappe.db, "exists", return_value=False), patch.object(
			coverage_module.frappe.db,
			"get_value",
			return_value={"event": "Change", "value_changed": "payment_status"},
		):
			self.assertEqual(coverage_module.validate_gosi_coverage(item), coverage_module.PARTIAL)