from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.doctype.saudi_annual_leave.saudi_annual_leave import SaudiAnnualLeave


class TestSaudiAnnualLeave(FrappeTestCase):
	def test_validate_rejects_cross_year_request(self):
		doc = frappe.get_doc({
			"doctype": "Saudi Annual Leave",
			"employee": "HR-EMP-00001",
			"leave_start_date": "2026-12-31",
			"leave_end_date": "2027-01-02",
		})

		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_validate_rejects_leave_before_joining_date(self):
		doc = frappe.get_doc({
			"doctype": "Saudi Annual Leave",
			"employee": "HR-EMP-00001",
			"leave_start_date": "2026-01-01",
			"leave_end_date": "2026-01-03",
		})

		with patch.object(
			SaudiAnnualLeave, "_set_status"
		), patch.object(
			SaudiAnnualLeave, "_calculate_days", wraps=doc._calculate_days
		), patch(
			"hr_suite.hr_suite.doctype.saudi_annual_leave.saudi_annual_leave.get_annual_leave_balance",
			return_value={"balance": 21},
		), patch.object(
			frappe.db, "get_value", return_value="2026-02-01"
		):
			with self.assertRaises(frappe.ValidationError):
				doc._calculate_days()
				doc._calculate_balance()