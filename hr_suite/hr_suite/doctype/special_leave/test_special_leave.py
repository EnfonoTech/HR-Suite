from datetime import date
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.doctype.special_leave import special_leave as special_leave_module


def _fake_getdate(value=None):
	if value is None:
		return date(2026, 3, 25)
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value))


class TestSpecialLeave(FrappeTestCase):
	@patch.object(special_leave_module, "getdate", side_effect=_fake_getdate)
	@patch.object(special_leave_module, "date_diff", side_effect=lambda end, start: (end - start).days)
	@patch.object(special_leave_module.frappe.db, "count", return_value=0)
	@patch.object(special_leave_module.frappe.db, "get_value", return_value="2025-06-01")
	def test_hajj_eligibility_requires_minimum_service(self, _get_value, _count, _date_diff, _getdate):
		result = special_leave_module.check_hajj_eligibility("EMP-0001")
		self.assertFalse(result["eligible"])
		self.assertFalse(result["minimum_service_met"])

	@patch.object(special_leave_module, "getdate", side_effect=_fake_getdate)
	@patch.object(special_leave_module, "date_diff", side_effect=lambda end, start: (end - start).days)
	@patch.object(special_leave_module.frappe.db, "count", return_value=1)
	@patch.object(special_leave_module.frappe.db, "get_value", return_value="2023-01-01")
	def test_hajj_eligibility_blocks_repeat_leave(self, _get_value, _count, _date_diff, _getdate):
		result = special_leave_module.check_hajj_eligibility("EMP-0001")
		self.assertFalse(result["eligible"])
		self.assertTrue(result["minimum_service_met"])
		self.assertEqual(result["prior_count"], 1)