from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.report.saudi_leave_balance_report.saudi_leave_balance_report import execute


class TestSaudiLeaveBalanceReport(FrappeTestCase):
	def test_report_opens_without_filters(self):
		columns, data = execute({})

		self.assertTrue(columns)
		self.assertIsInstance(data, list)
