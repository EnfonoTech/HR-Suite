"""Phase 1 — GCC country policy: seed data, validation and per-employee resolution."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.policy import (
	apply_overrides,
	get_country_policy,
	get_policy,
	months_of_service,
	resolve_annual_band,
)
from hr_suite.hr_suite.policy_defaults import POLICY_DEFAULTS
from hr_suite.hr_suite.policy_validation import validate_policy

SA_BANDS = [
	{"service_from_months": 0, "leave_days_per_year": 21, "salary_days_per_year": 21},
	{"service_from_months": 60, "leave_days_per_year": 30, "salary_days_per_year": 30},
]


def _cfg(**kw):
	doc = frappe.new_doc("Country Config")
	doc.country_code = "ZZ"
	for key, value in kw.items():
		if isinstance(value, list):
			for row in value:
				doc.append(key, row)
		else:
			doc.set(key, value)
	return doc


class TestServiceAndBands(FrappeTestCase):
	def test_months_of_service_counts_completed_months(self):
		self.assertEqual(months_of_service("2026-01-15", "2026-02-14"), 0)
		self.assertEqual(months_of_service("2026-01-15", "2026-02-15"), 1)
		self.assertEqual(months_of_service("2021-03-09", "2026-03-09"), 60)
		self.assertEqual(months_of_service("2026-06-01", "2026-05-01"), 0)
		self.assertEqual(months_of_service(None, "2026-05-01"), 0)

	def test_ksa_steps_up_to_30_days_at_five_years(self):
		self.assertEqual(resolve_annual_band(SA_BANDS, 59)["leave_days_per_year"], 21)
		self.assertEqual(resolve_annual_band(SA_BANDS, 60)["leave_days_per_year"], 30)

	def test_nothing_accrues_before_the_first_band(self):
		uae = POLICY_DEFAULTS["AE"]["annual_leave_bands"]
		self.assertIsNone(resolve_annual_band(uae, 5))
		self.assertEqual(resolve_annual_band(uae, 6)["leave_days_per_year"], 24)  # 2 a month
		self.assertEqual(resolve_annual_band(uae, 12)["leave_days_per_year"], 30)  # 2.5 a month


class TestOverrides(FrappeTestCase):
	def test_ksa_company_option_30_leave_21_salary(self):
		band = SA_BANDS[0]
		annual = apply_overrides(
			None, band, {"override_leave_days_per_year": 30, "override_salary_days_per_year": 21}
		)
		self.assertEqual(annual.leave_days_per_month, 2.5)
		self.assertEqual(annual.salary_days_per_month, 1.75)
		self.assertEqual(annual.overrides_used, ["leave days per year", "salary days per year"])

	def test_no_override_follows_the_band(self):
		annual = apply_overrides(None, SA_BANDS[1], {})
		self.assertEqual((annual.leave_days_per_year, annual.salary_days_per_year), (30, 30))
		self.assertEqual(annual.leave_cycle_years, 1)
		self.assertEqual(annual.overrides_used, [])

	def test_two_year_cycle_and_ticket(self):
		annual = apply_overrides(
			None, SA_BANDS[0],
			{"override_leave_cycle_years": "2", "override_ticket_entitled": 1, "override_ticket_amount": 1500},
		)
		self.assertEqual(annual.leave_cycle_years, 2)
		self.assertEqual(annual.ticket_amount, 1500)

	def test_no_band_means_no_entitlement(self):
		annual = apply_overrides(None, None, {})
		self.assertEqual(annual.leave_days_per_month, 0)


class TestSeedAgainstSpec(FrappeTestCase):
	"""The seeded Country Config must say what the functional spec says."""

	def test_all_six_gcc_countries_exist(self):
		for code in ("SA", "BH", "OM", "AE", "QA", "KW"):
			self.assertTrue(get_country_policy(code), f"no Country Config for {code}")

	def test_sick_tiers_add_up_to_the_annual_days(self):
		for code in POLICY_DEFAULTS:
			policy = get_country_policy(code)
			self.assertEqual(
				sum(t["tier_days"] for t in policy.sick_leave_tiers),
				policy.sick_leave_days_per_year,
				code,
			)

	def test_spec_sick_tiers(self):
		def tiers(code):
			return [(t["tier_days"], int(t["pay_percent"])) for t in get_country_policy(code).sick_leave_tiers]

		self.assertEqual(tiers("SA"), [(30, 100), (60, 75), (30, 0)])
		self.assertEqual(tiers("BH"), [(15, 100), (20, 50), (20, 0)])
		self.assertEqual(tiers("OM"), [(21, 100), (14, 75), (35, 50), (112, 35)])
		self.assertEqual(tiers("AE"), [(15, 100), (30, 50), (45, 0)])
		self.assertEqual(tiers("QA"), [(14, 100), (28, 50), (42, 0)])
		self.assertEqual(tiers("KW"), [(15, 100), (10, 75), (10, 50), (10, 25), (30, 0)])

	def test_spec_caps_and_eligibility(self):
		self.assertEqual(get_country_policy("AE").gratuity_cap_months, 24)
		self.assertEqual(get_country_policy("KW").gratuity_cap_months, 18)
		self.assertEqual(get_country_policy("BH").annual_leave_eligible_after_months, 12)
		self.assertEqual(get_country_policy("KW").annual_leave_eligible_after_months, 9)
		self.assertEqual(get_country_policy("SA").leave_salary_min_earned_days, 30)
		self.assertEqual(get_country_policy("SA").leave_salary_min_service_days, 365)

	def test_every_slab_set_is_valid(self):
		for code in POLICY_DEFAULTS:
			doc = frappe.get_doc("Country Config", code)
			validate_policy(doc)  # must not throw


class TestValidation(FrappeTestCase):
	def test_sick_tiers_must_match_days(self):
		doc = _cfg(
			sick_leave_days_per_year=100,
			sick_leave_tiers=[{"tier_days": 30, "pay_percent": 100}, {"tier_days": 60, "pay_percent": 50}],
		)
		self.assertRaises(frappe.ValidationError, validate_policy, doc)

	def test_duplicate_band_start_refused(self):
		doc = _cfg(annual_leave_bands=[
			{"service_from_months": 0, "leave_days_per_year": 21, "salary_days_per_year": 21},
			{"service_from_months": 0, "leave_days_per_year": 30, "salary_days_per_year": 30},
		])
		self.assertRaises(frappe.ValidationError, validate_policy, doc)

	def test_overlapping_gratuity_slabs_refused(self):
		doc = _cfg(gratuity_slabs=[
			{"from_years": 0, "to_years": 5, "rate_unit": "Months of wage per year", "rate_value": 0.5},
			{"from_years": 4, "to_years": 0, "rate_unit": "Months of wage per year", "rate_value": 1},
		])
		self.assertRaises(frappe.ValidationError, validate_policy, doc)

	def test_open_ended_slab_must_be_last(self):
		doc = _cfg(gratuity_slabs=[
			{"from_years": 0, "to_years": 0, "rate_unit": "Months of wage per year", "rate_value": 0.5},
			{"from_years": 5, "to_years": 0, "rate_unit": "Months of wage per year", "rate_value": 1},
		])
		self.assertRaises(frappe.ValidationError, validate_policy, doc)

	def test_percent_out_of_range_refused(self):
		doc = _cfg(gratuity_resignation_factors=[{"from_years": 0, "to_years": 0, "payable_percent": 150}])
		self.assertRaises(frappe.ValidationError, validate_policy, doc)

	def test_new_config_without_night_rate_is_cleared_not_refused(self):
		"""Regression: a fresh Country Config with no night rate used to refuse to save,
		because Frappe stamps an unset Time field with the current time. That stopped
		Saudi Arabia and India from seeding on a new install."""
		doc = _cfg(country_name="Zed", overtime_night_rate=0)
		doc.overtime_night_start = "10:28:20"
		doc.overtime_night_end = "10:28:21"
		doc._validate_overtime()
		self.assertFalse(doc.overtime_night_start)
		self.assertFalse(doc.overtime_night_end)


class TestResolution(FrappeTestCase):
	def _joined(self, date):
		"""Make Employee.date_of_joining read as `date`; every other lookup stays real."""
		real = frappe.db.get_value

		def fake(doctype, *args, **kwargs):
			if doctype == "Employee":
				return date
			return real(doctype, *args, **kwargs)

		return patch("hr_suite.hr_suite.policy.frappe.db.get_value", side_effect=fake)

	def test_unknown_country_has_no_policy(self):
		with patch("hr_suite.hr_suite.policy.get_employee_work_country", return_value="ZZ"), self._joined(
			"2024-01-01"
		):
			policy = get_policy("EMP-X")
		self.assertEqual(policy.has_policy, 0)

	def test_ksa_employee_resolves_band_and_barrier(self):
		with patch("hr_suite.hr_suite.policy.get_employee_work_country", return_value="SA"), patch(
			"hr_suite.hr_suite.policy._employee_overrides", return_value={}
		), self._joined("2021-01-01"):
			policy = get_policy("EMP-X", on_date="2026-10-05")
		self.assertEqual(policy.has_policy, 1)
		self.assertEqual(policy.service_months, 69)
		self.assertEqual(policy.annual.leave_days_per_year, 30)  # past the 5-year step
		self.assertEqual(policy.annual.leave_days_per_month, 2.5)
		self.assertEqual(policy.leave_salary_min_earned_days, 30)
		self.assertEqual(policy.leave_can_be_taken, 1)

	def test_override_wins_over_the_band(self):
		overrides = {"override_leave_days_per_year": 30, "override_salary_days_per_year": 21}
		with patch("hr_suite.hr_suite.policy.get_employee_work_country", return_value="SA"), patch(
			"hr_suite.hr_suite.policy._employee_overrides", return_value=overrides
		), self._joined("2025-06-01"):
			policy = get_policy("EMP-X", on_date="2026-10-05")
		self.assertEqual(policy.annual.leave_days_per_month, 2.5)
		self.assertEqual(policy.annual.salary_days_per_month, 1.75)
