"""Tests for hr_suite.hr_suite.leave_setup.

These assert the SHAPE of the provisioning, never a statutory number of their
own: every expected figure is read back out of ``Country Config``, which is the
only source of employment law this app is allowed to rely on. A test that
hardcoded "30 days annual leave" would just be a second place to get the law
wrong.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from hr_suite.hr_suite.leave_setup import (
	PAY_FULL,
	PAY_PARTIAL,
	PAY_UNPAID,
	_declared_rows,
	_match_holiday_list,
	_pay_treatment_fields,
	_policy_details,
	get_active_country_codes,
	get_policy_titles,
	resolve_leave_policy,
)


class TestLeaveSetupPayTreatment(FrappeTestCase):
	"""The tiering mechanism: Country Config row -> HRMS Leave Type flags."""

	def test_full_pay_is_neither_lwp_nor_ppl(self):
		fields = _pay_treatment_fields(frappe._dict({"pay_treatment": PAY_FULL, "paid_fraction": 0}))
		self.assertEqual(fields, {"is_lwp": 0, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0})

	def test_missing_pay_treatment_defaults_to_full_pay(self):
		"""Rows that predate the field must keep meaning exactly what they meant."""
		fields = _pay_treatment_fields(frappe._dict({"pay_treatment": "", "paid_fraction": 0}))
		self.assertEqual(fields["is_lwp"], 0)
		self.assertEqual(fields["is_ppl"], 0)

	def test_partially_paid_sets_ppl_and_fraction(self):
		fields = _pay_treatment_fields(
			frappe._dict({"pay_treatment": PAY_PARTIAL, "paid_fraction": 0.5})
		)
		self.assertEqual(fields["is_ppl"], 1)
		self.assertEqual(fields["is_lwp"], 0)
		self.assertEqual(flt(fields["fraction_of_daily_salary_per_leave"]), 0.5)

	def test_partially_paid_without_a_usable_fraction_is_rejected(self):
		for bad in (0, 1, -0.2, 1.5):
			with self.subTest(fraction=bad):
				self.assertIsNone(
					_pay_treatment_fields(
						frappe._dict({"pay_treatment": PAY_PARTIAL, "paid_fraction": bad})
					)
				)

	def test_unpaid_sets_lwp(self):
		fields = _pay_treatment_fields(frappe._dict({"pay_treatment": PAY_UNPAID, "paid_fraction": 0}))
		self.assertEqual(fields["is_lwp"], 1)
		self.assertEqual(fields["is_ppl"], 0)

	def test_lwp_and_ppl_are_never_both_set(self):
		"""HRMS LeaveType.validate_leave_types throws if both are on."""
		for treatment in (PAY_FULL, PAY_PARTIAL, PAY_UNPAID):
			fields = _pay_treatment_fields(
				frappe._dict({"pay_treatment": treatment, "paid_fraction": 0.5})
			)
			if fields is None:
				continue
			with self.subTest(treatment=treatment):
				self.assertFalse(fields["is_lwp"] and fields["is_ppl"])


class TestHolidayListMatching(FrappeTestCase):
	def test_two_shared_identifying_words_are_required(self):
		lists = [
			{"name": "Steel Force 2026", "from_date": "2026-01-01", "to_date": "2026-12-31"},
			{"name": "Salary Slip Test Holiday List", "from_date": "2026-01-01", "to_date": "2026-12-31"},
		]
		lists = [frappe._dict(row) for row in lists]

		self.assertEqual(_match_holiday_list("Steel Force Trading WLL", lists), "Steel Force 2026")
		# "Test" alone is not an identity - a company must not inherit a stray list.
		self.assertEqual(_match_holiday_list("Test Company", lists), "")
		self.assertEqual(_match_holiday_list("Company SF", lists), "")

	def test_prefers_the_list_covering_today(self):
		"""Dates are built relative to today so the test does not rot next year."""
		this_year = frappe._dict(
			{
				"name": "Steel Force Current",
				"from_date": add_days(today(), -30),
				"to_date": add_days(today(), 30),
			}
		)
		last_year = frappe._dict(
			{
				"name": "Steel Force Expired",
				"from_date": add_days(today(), -400),
				"to_date": add_days(today(), -35),
			}
		)
		self.assertEqual(
			_match_holiday_list("Steel Force Trading WLL", [last_year, this_year]),
			"Steel Force Current",
		)


class TestLeaveProvisioning(FrappeTestCase):
	"""Post-provisioning shape checks. after_migrate has already run these."""

	def test_every_company_has_a_leave_period_for_every_fiscal_year(self):
		fiscal_years = frappe.get_all(
			"Fiscal Year", filters={"disabled": 0}, fields=["year_start_date", "year_end_date"]
		)
		companies = frappe.get_all("Company", pluck="name")
		for company in companies:
			for fy in fiscal_years:
				with self.subTest(company=company, fy=fy.year_start_date):
					self.assertTrue(
						frappe.db.exists(
							"Leave Period",
							{
								"company": company,
								"from_date": fy.year_start_date,
								"to_date": fy.year_end_date,
							},
						),
						f"No Leave Period for {company} / {fy.year_start_date}",
					)

	def test_declared_leave_types_exist_and_are_not_duplicated(self):
		for code in get_active_country_codes():
			for row in _declared_rows(code):
				with self.subTest(country=code, leave_type=row.leave_type):
					self.assertTrue(
						frappe.db.exists("Leave Type", row.leave_type),
						f"Leave Type {row.leave_type} was not provisioned",
					)
					# The country code must never appear as a suffixed duplicate
					# beside the stock record.
					self.assertFalse(
						frappe.db.exists("Leave Type", f"{row.leave_type} {code}"),
						f"Duplicate Leave Type created for {row.leave_type}",
					)

	def test_leave_type_caps_match_the_declared_entitlement(self):
		for code in get_active_country_codes():
			rows = _declared_rows(code)
			names = [r.leave_type for r in rows]
			if len(names) != len(set(names)):
				continue  # ambiguous config, provisioning deliberately writes nothing
			for row in rows:
				if row.days_per_year <= 0:
					continue
				cap = flt(frappe.db.get_value("Leave Type", row.leave_type, "max_leaves_allowed"))
				with self.subTest(leave_type=row.leave_type):
					# A cap below the entitlement would make Leave Policy reject
					# the allocation the config itself declares.
					self.assertGreaterEqual(cap, row.days_per_year)

	def test_policy_allocations_come_straight_from_country_config(self):
		for code in get_active_country_codes():
			policy = resolve_leave_policy(code, "Male")
			if not policy:
				continue
			allocated = {
				r.leave_type: flt(r.annual_allocation)
				for r in frappe.get_all(
					"Leave Policy Detail",
					filters={"parent": policy, "parenttype": "Leave Policy"},
					fields=["leave_type", "annual_allocation"],
				)
			}
			expected = {
				d["leave_type"]: flt(d["annual_allocation"]) for d in _policy_details(code, "Male")
			}
			self.assertEqual(allocated, expected)

	def test_once_in_employment_leave_is_kept_out_of_the_annual_policy(self):
		"""Hajj-style leave must not be re-granted every year by a policy."""
		for code in get_active_country_codes():
			once_only = {r.leave_type for r in _declared_rows(code) if r.once_in_employment}
			if not once_only:
				continue
			for gender in ("All", "Male", "Female"):
				in_policy = {d["leave_type"] for d in _policy_details(code, gender)}
				with self.subTest(country=code, gender=gender):
					self.assertFalse(once_only & in_policy)

	def test_gender_specific_leave_only_reaches_the_matching_policy(self):
		for code in get_active_country_codes():
			for row in _declared_rows(code):
				if row.gender_specific == "All" or row.once_in_employment:
					continue
				wanted = row.gender_specific.replace(" Only", "")
				other = "Female" if wanted == "Male" else "Male"
				with self.subTest(leave_type=row.leave_type):
					self.assertIn(
						row.leave_type, {d["leave_type"] for d in _policy_details(code, wanted)}
					)
					self.assertNotIn(
						row.leave_type, {d["leave_type"] for d in _policy_details(code, other)}
					)
					self.assertNotIn(
						row.leave_type, {d["leave_type"] for d in _policy_details(code, "All")}
					)

	def test_policy_titles_are_stable(self):
		"""Idempotency depends on the title, which is the only stable key -
		Leave Policy autonames to HR-LPOL-YYYY-#####."""
		for code in get_active_country_codes():
			titles = get_policy_titles(code)
			self.assertEqual(len(set(titles.values())), 3)


class TestLeaveTypeCapAccommodatesCarryForward(FrappeTestCase):
	"""``max_leaves_allowed`` is read by TWO core rules that pull in opposite directions.

	``Leave Policy.validate`` refuses an annual_allocation above it, and
	``LeaveAllocation.limit_carry_forward_based_on_max_allowed_leaves`` silently clamps
	new + carried down to it. A cap of exactly ``days_per_year`` therefore satisfies the
	first rule and destroys the carry-forward the config declares, with no error anywhere.
	"""

	def test_cap_covers_entitlement_plus_declared_carry_forward(self):
		for code in get_active_country_codes():
			rows = _declared_rows(code)
			names = [r.leave_type for r in rows]
			if len(names) != len(set(names)):
				continue  # ambiguous config: provisioning deliberately writes nothing
			for row in rows:
				if row.days_per_year <= 0:
					continue
				cap = flt(frappe.db.get_value("Leave Type", row.leave_type, "max_leaves_allowed"))
				with self.subTest(country=code, leave_type=row.leave_type):
					self.assertGreaterEqual(
						cap,
						flt(row.days_per_year) + flt(row.max_carry_forward_days),
						"max_leaves_allowed on {0} clamps away the {1} carry-forward days "
						"Country Config declares".format(row.leave_type, row.max_carry_forward_days),
					)

	def test_resolved_values_add_the_carry_forward_to_the_cap(self):
		from hr_suite.hr_suite.leave_setup import _resolve_declared_values

		row = frappe._dict({
			"country_code": "XX",
			"leave_type": "_Test Cap Leave",
			"days_per_year": 30.0,
			"max_carry_forward_days": 30.0,
			"is_optional": 0,
			"pay_treatment": PAY_FULL,
			"paid_fraction": 0.0,
		})
		values = _resolve_declared_values(
			"_Test Cap Leave", [row], {"conflicts": []}
		)
		self.assertEqual(values["max_leaves_allowed"], 60.0)
		self.assertEqual(values["maximum_carry_forwarded_leaves"], 30.0)
		self.assertEqual(values["is_carry_forward"], 1)


class TestSickLeavePayIsDeclaredNotInvented(FrappeTestCase):
	"""``get_sick_leave_pay`` must agree with what the Salary Slip actually pays.

	Before this it read three fields that do not exist on ``Country Leave Type Row`` and
	fell through to hardcoded 30 / 60 / 75% for every country, telling Bahrain HR that a
	35th sick day was at "Partial Pay 75% per Bahrain labor law" while the payslip paid
	it in full.
	"""

	def _bahrain_employee(self):
		from hr_suite.hr_suite.utils import get_employee_work_country

		for name in frappe.get_all("Employee", filters={"status": "Active"}, pluck="name"):
			if get_employee_work_country(name) == "BH":
				return name
		return None

	def test_declared_full_pay_band_is_paid_in_full(self):
		from hr_suite.hr_suite.utils import get_sick_leave_pay

		employee = self._bahrain_employee()
		if not employee:
			self.skipTest("no Bahrain employee on this site")

		declared = sum(
			flt(r.days_per_year)
			for r in _declared_rows("BH")
			if "sick" in r.leave_type.lower()
		)
		self.assertGreater(declared, 0)

		info = get_sick_leave_pay(employee, int(declared))
		self.assertEqual(info["rate"], 1.0)
		self.assertTrue(info["is_declared"])

	def test_beyond_the_declared_entitlement_is_reported_as_undeclared(self):
		from hr_suite.hr_suite.utils import get_sick_leave_pay

		employee = self._bahrain_employee()
		if not employee:
			self.skipTest("no Bahrain employee on this site")

		declared = sum(
			flt(r.days_per_year)
			for r in _declared_rows("BH")
			if "sick" in r.leave_type.lower()
		)
		info = get_sick_leave_pay(employee, int(declared) + 1)
		# No band is declared out here, so the app must not assert a reduced rate.
		self.assertFalse(info["is_declared"])
		self.assertEqual(info["rate"], 1.0)
		self.assertEqual(flt(info["declared_days"]), declared)

	def test_a_declared_partial_band_is_honoured(self):
		"""The tiering mechanism, driven end to end from Country Config."""
		from hr_suite.hr_suite.utils import _declared_sick_pay

		info = _declared_sick_pay(
			frappe._dict({"pay_treatment": PAY_PARTIAL, "paid_fraction": 0.5}), "BH", 55.0
		)
		self.assertEqual(info["rate"], 0.5)
		self.assertTrue(info["is_declared"])

		unpaid = _declared_sick_pay(
			frappe._dict({"pay_treatment": PAY_UNPAID, "paid_fraction": 0}), "BH", 55.0
		)
		self.assertEqual(unpaid["rate"], 0.0)
		self.assertTrue(unpaid["is_declared"])

	def test_partial_band_without_a_fraction_declares_nothing(self):
		from hr_suite.hr_suite.utils import _declared_sick_pay

		info = _declared_sick_pay(
			frappe._dict({"pay_treatment": PAY_PARTIAL, "paid_fraction": 0}), "BH", 55.0
		)
		self.assertFalse(info["is_declared"])
		self.assertEqual(info["rate"], 1.0)
