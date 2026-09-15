"""Overtime is priced by Country Config, not by a constant in the code.

Every expected figure below is read back out of Country Config, the same way the
leave tests are written. A test that hard-codes 1.25 for Bahrain would pass on a
site whose HR manager has legitimately agreed a better rate, and would then be
testing the test rather than the app.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from hr_suite.hr_suite.utils import (
	DEFAULT_OVERTIME_HOURS_PER_MONTH,
	DEFAULT_OVERTIME_RATE,
	_time_to_minutes,
	_windows_overlap,
	resolve_overtime_terms,
)


class TestOvertimeRateWindows(FrappeTestCase):
	"""The night-window arithmetic, which has to survive crossing midnight."""

	def test_time_reads_both_shapes(self):
		import datetime

		self.assertEqual(_time_to_minutes("19:00:00"), 19 * 60)
		self.assertEqual(_time_to_minutes("07:30"), 7 * 60 + 30)
		self.assertEqual(_time_to_minutes(datetime.timedelta(hours=22)), 22 * 60)
		self.assertIsNone(_time_to_minutes(""))
		self.assertIsNone(_time_to_minutes(None))

	def test_night_window_crossing_midnight(self):
		night_start, night_end = 19 * 60, 7 * 60  # Bahrain: 19:00 -> 07:00

		# An evening shift that runs into the window
		self.assertTrue(_windows_overlap(17 * 60, 21 * 60, night_start, night_end))
		# A shift wholly inside the small hours
		self.assertTrue(_windows_overlap(1 * 60, 5 * 60, night_start, night_end))
		# A shift that itself crosses midnight
		self.assertTrue(_windows_overlap(22 * 60, 2 * 60, night_start, night_end))
		# A plain daytime shift
		self.assertFalse(_windows_overlap(9 * 60, 17 * 60, night_start, night_end))

	def test_missing_times_never_claim_a_night_shift(self):
		self.assertFalse(_windows_overlap(None, None, 19 * 60, 7 * 60))


class TestOvertimeTermsFollowCountryConfig(FrappeTestCase):
	"""resolve_overtime_terms() returns what Country Config says, for every country."""

	def test_every_seeded_country_prices_its_own_overtime(self):
		configs = frappe.get_all(
			"Country Config",
			fields=[
				"name", "country_code", "overtime_weekday_rate",
				"overtime_rest_day_rate", "overtime_holiday_rate",
				"overtime_hours_per_month",
			],
		)
		if not configs:
			self.skipTest("No Country Config rows on this site")

		unconfigured = [c.country_code for c in configs if not flt(c.overtime_weekday_rate)]
		self.assertFalse(
			unconfigured,
			f"Country Config rows with no overtime weekday rate: {unconfigured}. "
			"The backfill patch should have filled these.",
		)

		for cfg in configs:
			with self.subTest(country=cfg.country_code):
				self.assertGreater(flt(cfg.overtime_hours_per_month), 0)
				# A rest day and a public holiday are never cheaper than a working day.
				self.assertGreaterEqual(
					flt(cfg.overtime_rest_day_rate), flt(cfg.overtime_weekday_rate)
				)
				self.assertGreaterEqual(
					flt(cfg.overtime_holiday_rate), flt(cfg.overtime_weekday_rate)
				)

	def test_terms_for_an_unknown_employee_fall_back_rather_than_fail(self):
		terms = resolve_overtime_terms("", None)
		self.assertEqual(terms["rate"], DEFAULT_OVERTIME_RATE)
		self.assertEqual(terms["hours_per_month"], DEFAULT_OVERTIME_HOURS_PER_MONTH)
		self.assertEqual(terms["day_type"], "Working Day")
		self.assertFalse(terms["is_configured"])

	def test_a_real_employee_resolves_against_their_work_country(self):
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			self.skipTest("No active employee on this site")

		from hr_suite.hr_suite.utils import get_employee_work_country

		country = get_employee_work_country(employee)
		config = frappe.db.get_value(
			"Country Config", {"country_code": country},
			["overtime_weekday_rate", "overtime_hours_per_month"], as_dict=True,
		)
		terms = resolve_overtime_terms(employee, frappe.utils.today())

		self.assertIn(terms["day_type"], ("Working Day", "Weekly Rest Day", "Public Holiday"))
		self.assertGreater(terms["rate"], 0)
		if config and terms["day_type"] == "Working Day" and flt(config.overtime_weekday_rate):
			self.assertEqual(terms["rate"], flt(config.overtime_weekday_rate, 2))
			self.assertEqual(terms["hours_per_month"], flt(config.overtime_hours_per_month, 2))
