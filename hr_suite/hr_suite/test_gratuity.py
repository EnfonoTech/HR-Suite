"""Phase 2 - slab-driven gratuity, checked country by country against the policy spec.

Expected figures are worked by hand in the comments, never read back from the engine.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days

from hr_suite.hr_suite.gratuity import classify_exit, compute_gratuity
from hr_suite.hr_suite.policy import get_country_policy
from hr_suite.hr_suite.utils import calculate_eosb_components

JOINED = "2021-01-01"


def run(code, years, base, reason="Termination by Employer", joined=JOINED, **kw):
	"""Gratuity for `years` of service (365-day years) in country `code`."""
	exit_date = add_days(joined, int(round(years * 365)))
	return compute_gratuity(get_country_policy(code), joined, exit_date, base, reason, **kw)


class TestExitClassification(FrappeTestCase):
	def test_spellings(self):
		for text in ("Resignation", "Resignation by Employee", "resigned"):
			self.assertEqual(classify_exit(text), "Resignation")
		for text in ("Dismissal", "Disciplinary Dismissal (Article 80)"):
			self.assertEqual(classify_exit(text), "Dismissal")
		self.assertEqual(classify_exit("Partial Settlement"), "Partial Settlement")
		for text in ("Termination by Employer", "End of Contract", "Death", "Retirement", ""):
			self.assertEqual(classify_exit(text), "Termination")


class TestKSA(FrappeTestCase):
	def test_half_month_for_the_first_five_years(self):
		# 3 yrs x 0.5 month x 10,000
		self.assertEqual(run("SA", 3, 10000).gross_entitlement, 15000)

	def test_full_month_after_five_years(self):
		# 5 x 0.5 x 10,000 = 25,000 ; 3 x 1 x 10,000 = 30,000
		result = run("SA", 8, 10000)
		self.assertEqual(result.gross_entitlement, 55000)
		self.assertEqual([b["amount"] for b in result.breakdown], [25000, 30000])

	def test_resignation_bands(self):
		self.assertEqual(run("SA", 1.5, 10000, "Resignation").net_entitlement, 0)  # under 2 yrs
		self.assertEqual(run("SA", 3, 10000, "Resignation").net_entitlement, 5000)  # 15,000 x one third
		self.assertEqual(run("SA", 8, 10000, "Resignation").net_entitlement, 36666.67)  # 55,000 x two thirds
		self.assertEqual(run("SA", 12, 10000, "Resignation").net_entitlement, 95000)  # 9.5 months, full

	def test_dismissal_forfeits(self):
		self.assertEqual(run("SA", 8, 10000, "Dismissal").net_entitlement, 0)

	def test_unpaid_leave_is_taken_out_of_service(self):
		# 3 yrs less 365 unpaid days = 2 yrs x 0.5 x 10,000
		result = run("SA", 3, 10000, unpaid_days=365)
		self.assertEqual(result.qualifying_days, 730)
		self.assertEqual(result.gross_entitlement, 10000)

	def test_nationals_are_also_entitled(self):
		self.assertEqual(run("SA", 3, 10000, is_national=True).gross_entitlement, 15000)


class TestUAE(FrappeTestCase):
	def test_21_then_30_days(self):
		# daily 200: 5 x 21 x 200 = 21,000 ; 1 x 30 x 200 = 6,000
		self.assertEqual(run("AE", 6, 6000).gross_entitlement, 27000)

	def test_resignation_is_full(self):
		self.assertEqual(run("AE", 6, 6000, "Resignation").net_entitlement, 27000)

	def test_minimum_one_year(self):
		self.assertEqual(run("AE", 0.5, 6000).gross_entitlement, 0)

	def test_two_year_cap(self):
		# 21,000 + 25 x 30 x 200 = 171,000, capped at 24 months x 6,000
		result = run("AE", 30, 6000)
		self.assertEqual(result.gross_before_cap, 171000)
		self.assertEqual(result.gross_entitlement, 144000)
		self.assertTrue(result.capped)


class TestBahrain(FrappeTestCase):
	def test_service_stops_at_the_march_2024_cutoff(self):
		result = compute_gratuity(get_country_policy("BH"), "2020-01-01", "2026-01-01", 500, "Termination")
		days = 1521  # 2020-01-01 -> 2024-03-01: 1461 to 2024-01-01, +31 +29
		self.assertEqual(result.calendar_days, days)
		expected = round(3 * 0.5 * 500 + (days / 365.0 - 3) * 1 * 500, 3)
		self.assertAlmostEqual(result.gross_entitlement, expected, places=3)

	def test_joined_after_the_cutoff_has_no_employer_gratuity(self):
		result = compute_gratuity(get_country_policy("BH"), "2025-01-01", "2026-06-01", 500, "Termination")
		self.assertEqual(result.gross_entitlement, 0)

	def test_nationals_are_under_sio(self):
		self.assertEqual(run("BH", 3, 500, is_national=True).gross_entitlement, 0)


class TestOman(FrappeTestCase):
	def test_one_month_per_year_and_full_on_resignation(self):
		self.assertEqual(run("OM", 5, 400, "Resignation").net_entitlement, 2000)


class TestQatar(FrappeTestCase):
	def test_three_weeks_per_year(self):
		# 3 weeks = 21 days = 0.7 month ; 2 yrs x 0.7 x 5,000
		self.assertEqual(run("QA", 2, 5000).gross_entitlement, 7000)

	def test_minimum_one_year(self):
		self.assertEqual(run("QA", 0.8, 5000).gross_entitlement, 0)


class TestKuwait(FrappeTestCase):
	def test_fifteen_days_then_a_month_and_three_decimal_currency(self):
		# 5 x 15/30 x 400 = 1,000 ; 2 x 1 x 400 = 800
		result = run("KW", 7, 400, precision=3)
		self.assertEqual(result.gross_entitlement, 1800)

	def test_resignation_after_seven_years_is_two_thirds(self):
		self.assertEqual(run("KW", 7, 400, "Resignation", precision=3).net_entitlement, 1200)

	def test_cap_is_eighteen_months(self):
		result = run("KW", 40, 400, precision=3)
		self.assertEqual(result.gross_entitlement, 7200)


class TestPartialSettlement(FrappeTestCase):
	def test_pays_accrued_gratuity_in_full_and_is_flagged(self):
		result = run("SA", 3, 10000, "Partial Settlement")
		self.assertEqual(result.net_entitlement, 15000)
		self.assertEqual(result.is_partial, 1)


class TestGuards(FrappeTestCase):
	def test_exit_must_be_after_joining(self):
		self.assertRaises(
			frappe.ValidationError, compute_gratuity, get_country_policy("SA"), "2026-04-02", "2026-04-01", 5000, "Resignation"
		)

	def test_deductions_cannot_exceed_the_payable_amount(self):
		self.assertRaises(frappe.ValidationError, run, "SA", 3, 10000, "Termination", deductions=999999)

	def test_wage_must_be_positive(self):
		self.assertRaises(frappe.ValidationError, run, "SA", 3, 0)

	def test_a_country_with_no_slabs_is_refused_not_defaulted_to_saudi(self):
		policy = get_country_policy("SA")
		policy = frappe._dict(policy, gratuity_slabs=[])
		self.assertRaises(
			frappe.ValidationError, compute_gratuity, policy, JOINED, "2026-01-01", 5000, "Termination"
		)


class TestLegacyWrapper(FrappeTestCase):
	def test_preview_figures_use_the_country_policy(self):
		# 16 years' resignation is past the 10-year line, so the spec pays in full
		result = calculate_eosb_components("2010-01-01", "2026-04-02", 6000, "Resignation")
		self.assertEqual(result["resignation_factor"], 1.0)
		self.assertGreater(result["net_eosb"], 0)
		self.assertTrue(result["gratuity_breakdown"])

	def test_other_countries_through_the_wrapper(self):
		qa = calculate_eosb_components("2021-01-01", add_days("2021-01-01", 730), 5000, "Termination", country="QA")
		self.assertEqual(qa["eosb_gross"], 7000)


class TestDaysPerMonth(FrappeTestCase):
	"""Country Config > Days per Month (Gratuity) turns a days-a-year slab into months. Default 30."""

	def test_days_and_weeks_follow_the_setting(self):
		from hr_suite.hr_suite.gratuity import DAYS, WEEKS, _months_of_wage_per_year

		self.assertAlmostEqual(_months_of_wage_per_year(DAYS, 21), 0.7)  # 21 / 30
		self.assertAlmostEqual(_months_of_wage_per_year(DAYS, 21, 0), 0.7)  # unset falls back to 30
		self.assertAlmostEqual(_months_of_wage_per_year(DAYS, 21, 28), 0.75)  # 21 / 28
		self.assertAlmostEqual(_months_of_wage_per_year(WEEKS, 3, 28), 0.75)  # 3 x 7 / 28

	def test_the_policy_carries_the_setting_and_defaults_to_30(self):
		policy = get_country_policy("AE")
		if not policy:
			self.skipTest("No Country Config for AE")
		self.assertEqual(policy.gratuity_days_per_month, 30)

	def test_the_slab_amount_uses_the_policy_value(self):
		policy = get_country_policy("AE")
		if not policy:
			self.skipTest("No Country Config for AE")
		policy = frappe._dict(policy, gratuity_days_per_month=28)
		result = compute_gratuity(policy, JOINED, add_days(JOINED, 3 * 365), 10000, "Termination by Employer")
		self.assertEqual(result.gross_entitlement, 22500)  # 3 yrs x 21/28 x 10,000
