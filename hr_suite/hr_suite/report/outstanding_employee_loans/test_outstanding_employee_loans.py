from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.report.outstanding_employee_loans import outstanding_employee_loans as report_module


class TestOutstandingEmployeeLoans(FrappeTestCase):
	def test_get_data_returns_sql_rows(self):
		rows = [{"loan": "LOAN-1", "outstanding_balance": 500}]
		with patch.object(report_module.frappe.db, "sql", return_value=rows):
			self.assertEqual(report_module.get_data({}), rows)