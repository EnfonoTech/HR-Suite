from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite import utils


test_ignore = ["Journal Entry"]


class TestAnnualLeaveDisbursement(FrappeTestCase):
	def test_get_annual_leave_days_taken_reads_saudi_annual_leave(self):
		with patch.object(
			utils.frappe,
			"get_all",
			return_value=[
				frappe._dict(leave_start_date="2026-01-01", leave_end_date="2026-01-05", total_leave_days=5, half_day=0),
				frappe._dict(leave_start_date="2025-12-31", leave_end_date="2026-01-01", total_leave_days=2, half_day=0),
			],
		):
			total = utils.get_annual_leave_days_taken("EMP-0001", 2026)

		self.assertEqual(total, 6)