"""Tests for monthly leave accrual and the year roll-forward.

These assert END STATE — what the ``Leave Type`` actually carries, what HRMS's own
engine computes from it, what a second run of the roll-forward creates — rather than
that a particular line ran. Statutory figures are never hardcoded: every expected
number is either read back out of ``Country Config`` or supplied by the test itself.

A site with no Country Config, no active country or no Leave Period skips the case
instead of failing it.
"""

import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, cstr, flt, get_last_day, getdate, today

from hr_suite.hr_suite.leave_setup import (
	ACCRUAL_FIELDS,
	ACCRUAL_FREQUENCIES,
	ACCRUAL_NONE,
	ALLOCATE_ON_DAY_OPTIONS,
	DEFAULT_ALLOCATE_ON_DAY,
	PAY_FULL,
	PAY_UNPAID,
	_accrual_fields,
	_declared_rows,
	_next_period_dates,
	_resolve_declared_values,
	_value_changed,
	check_double_allocation_risk,
	get_active_country_codes,
	get_earned_leave_types,
	roll_forward_leave_periods,
	sync_leave_types_from_country_config,
)


_ONE_DAY = datetime.timedelta(days=1)


def _row(**overrides):
	"""A normalised Country Config leave row, shaped exactly like ``_declared_rows``."""
	row = frappe._dict(
		{
			"country_code": "XX",
			"leave_type": "_Test Accrual Leave",
			"declared_name": "_Test Accrual Leave",
			"days_per_year": 30.0,
			"gender_specific": "All",
			"is_optional": 0,
			"once_in_employment": 0,
			"max_carry_forward_days": 0.0,
			"pay_treatment": PAY_FULL,
			"paid_fraction": 0.0,
			"accrual_frequency": "",
			"accrual_source": "",
			"accrual_on_day": "",
			"accrual_rounding": "",
			"carry_forward_expiry_days": 0,
		}
	)
	row.update(overrides)
	return row


class TestAccrualDeclaration(FrappeTestCase):
	"""Country Config -> the four HRMS earned-leave fields."""

	def test_nothing_declared_leaves_the_leave_type_alone(self):
		"""A blank is not a decision. Writing is_earned_leave = 0 over a type somebody
		configured by hand would quietly switch their accrual off."""
		self.assertEqual(_accrual_fields(_row()), {})

	def test_declared_none_grants_the_whole_entitlement(self):
		"""Sick and maternity are entitlements you either have or do not have."""
		self.assertEqual(_accrual_fields(_row(accrual_frequency=ACCRUAL_NONE)), {"is_earned_leave": 0})

	def test_a_frequency_switches_hrms_accrual_on(self):
		for frequency in ACCRUAL_FREQUENCIES:
			with self.subTest(frequency=frequency):
				fields = _accrual_fields(_row(accrual_frequency=frequency))
				self.assertEqual(fields["is_earned_leave"], 1)
				self.assertEqual(fields["earned_leave_frequency"], frequency)

	def test_an_unrecognised_frequency_writes_nothing(self):
		self.assertEqual(_accrual_fields(_row(accrual_frequency="Fortnightly")), {})

	def test_once_in_employment_is_never_accrued(self):
		"""Hajj leave is a once-in-a-career grant; a twelfth of it every month is nothing."""
		fields = _accrual_fields(_row(accrual_frequency="Monthly", once_in_employment=1))
		self.assertEqual(fields, {"is_earned_leave": 0})

	def test_unpaid_leave_is_never_accrued(self):
		fields = _accrual_fields(_row(accrual_frequency="Monthly", pay_treatment=PAY_UNPAID))
		self.assertEqual(fields, {"is_earned_leave": 0})

	def test_a_zero_day_entitlement_is_never_accrued(self):
		fields = _accrual_fields(_row(accrual_frequency="Monthly", days_per_year=0))
		self.assertEqual(fields, {"is_earned_leave": 0})

	def test_allocate_on_day_is_always_set_when_accrual_is_on(self):
		"""hrms.check_effective_date indexes its map by this value, so an empty one
		raises KeyError inside the daily job and stops accrual for the whole site."""
		fields = _accrual_fields(_row(accrual_frequency="Monthly"))
		self.assertEqual(fields["allocate_on_day"], DEFAULT_ALLOCATE_ON_DAY)

	def test_date_of_joining_survives_only_on_monthly(self):
		"""It is a key of the Monthly branch of that map and of no other branch."""
		monthly = _accrual_fields(_row(accrual_frequency="Monthly", accrual_on_day="Date of Joining"))
		self.assertEqual(monthly["allocate_on_day"], "Date of Joining")

		for frequency in ("Quarterly", "Half-Yearly", "Yearly"):
			with self.subTest(frequency=frequency):
				fields = _accrual_fields(
					_row(accrual_frequency=frequency, accrual_on_day="Date of Joining")
				)
				self.assertEqual(fields["allocate_on_day"], DEFAULT_ALLOCATE_ON_DAY)

	def test_rounding_is_passed_through_and_junk_is_dropped(self):
		self.assertEqual(_accrual_fields(_row(accrual_frequency="Monthly", accrual_rounding="0.5"))["rounding"], "0.5")
		self.assertNotIn("rounding", _accrual_fields(_row(accrual_frequency="Monthly", accrual_rounding="0.3")))


class TestAccrualAgainstTheRealEngine(FrappeTestCase):
	"""What hr_suite writes has to be something HRMS can actually consume."""

	def test_every_combination_we_can_write_is_indexable_by_the_scheduler(self):
		"""``check_effective_date`` is a literal dict lookup inside the DAILY job.
		A combination it cannot index takes down accrual for every leave type."""
		from hrms.hr.utils import check_effective_date

		run_date = getdate(today())
		for frequency in ACCRUAL_FREQUENCIES:
			for on_day in ALLOCATE_ON_DAY_OPTIONS + ("", "Whenever"):
				fields = _accrual_fields(
					_row(accrual_frequency=frequency, accrual_on_day=on_day)
				)
				with self.subTest(frequency=frequency, declared=on_day):
					# No assertion on the answer - only that it can be computed at all.
					check_effective_date(
						run_date, run_date, fields["earned_leave_frequency"], fields["allocate_on_day"]
					)

	def test_thirty_days_a_year_accrues_two_and_a_half_a_month(self):
		"""The whole point of the feature, computed by HRMS rather than restated here."""
		from hrms.hr.utils import get_monthly_earned_leave

		earned = get_monthly_earned_leave(
			getdate("2020-01-01"), 30, "Monthly", "", pro_rated=False
		)
		self.assertEqual(flt(earned), 2.5)


class TestResolvedLeaveTypeValues(FrappeTestCase):
	def test_accrual_reaches_the_values_written_to_the_leave_type(self):
		values = _resolve_declared_values(
			"_Test Accrual Leave",
			[_row(accrual_frequency="Monthly", accrual_rounding="0.5")],
			{"conflicts": []},
		)
		self.assertEqual(values["is_earned_leave"], 1)
		self.assertEqual(values["earned_leave_frequency"], "Monthly")
		self.assertEqual(values["rounding"], "0.5")

	def test_carry_forward_expiry_is_written_when_carry_forward_is_on(self):
		values = _resolve_declared_values(
			"_Test Accrual Leave",
			[_row(max_carry_forward_days=30.0, carry_forward_expiry_days=90)],
			{"conflicts": []},
		)
		self.assertEqual(values["is_carry_forward"], 1)
		self.assertEqual(values["expire_carry_forwarded_leaves_after_days"], 90)

	def test_expiry_is_not_written_without_carry_forward(self):
		values = _resolve_declared_values(
			"_Test Accrual Leave",
			[_row(max_carry_forward_days=0.0, carry_forward_expiry_days=90)],
			{"conflicts": []},
		)
		self.assertNotIn("expire_carry_forwarded_leaves_after_days", values)

	def test_a_zero_expiry_is_left_alone(self):
		"""An Int cannot distinguish "never expires" from "nobody configured it"."""
		values = _resolve_declared_values(
			"_Test Accrual Leave",
			[_row(max_carry_forward_days=30.0, carry_forward_expiry_days=0)],
			{"conflicts": []},
		)
		self.assertNotIn("expire_carry_forwarded_leaves_after_days", values)

	def test_two_countries_disagreeing_only_on_accrual_is_a_conflict(self):
		result = {"conflicts": []}
		values = _resolve_declared_values(
			"_Test Accrual Leave",
			[
				_row(country_code="BH", accrual_frequency="Monthly"),
				_row(country_code="SA", accrual_frequency=ACCRUAL_NONE),
			],
			result,
		)
		self.assertIsNone(values)
		self.assertEqual(len(result["conflicts"]), 1)


class TestSelectFieldsAreComparedAsText(FrappeTestCase):
	"""flt("Monthly") is 0.0 and so is flt("Yearly").

	Comparing the accrual Selects numerically made every change look like no change,
	so the Leave Type reported "unchanged" and was never switched over.
	"""

	def test_a_different_frequency_counts_as_changed(self):
		self.assertTrue(_value_changed("Yearly", "Monthly"))

	def test_the_same_frequency_counts_as_unchanged(self):
		self.assertFalse(_value_changed("Monthly", "Monthly"))

	def test_an_unset_select_counts_as_changed(self):
		self.assertTrue(_value_changed(None, "Monthly"))

	def test_numbers_are_still_compared_as_numbers(self):
		self.assertFalse(_value_changed("30", 30.0))
		self.assertTrue(_value_changed(30, 31))


class TestLeaveTypeCarriesTheFieldsWeWrite(FrappeTestCase):
	"""A rename upstream must fail here, not silently stop provisioning accrual."""

	def test_every_accrual_field_exists_on_leave_type(self):
		meta = frappe.get_meta("Leave Type")
		for field in ACCRUAL_FIELDS + ("expire_carry_forwarded_leaves_after_days",):
			with self.subTest(field=field):
				self.assertTrue(meta.has_field(field), f"Leave Type has no field {field}")

	def test_the_frequencies_we_write_are_options_hrms_accepts(self):
		options = set(
			cstr(frappe.get_meta("Leave Type").get_field("earned_leave_frequency").options).split("\n")
		)
		self.assertTrue(set(ACCRUAL_FREQUENCIES) <= options)

	def test_the_allocate_on_day_we_default_to_is_an_option(self):
		options = set(
			cstr(frappe.get_meta("Leave Type").get_field("allocate_on_day").options).split("\n")
		)
		self.assertIn(DEFAULT_ALLOCATE_ON_DAY, options)


class TestProvisionedAccrual(FrappeTestCase):
	"""Run the sync and read the Leave Types back."""

	def test_declared_accrual_reaches_the_leave_type(self):
		declared = []
		for code in get_active_country_codes():
			for row in _declared_rows(code):
				if row.accrual_frequency:
					declared.append(row)

		if not declared:
			self.skipTest("no country on this site declares a leave accrual frequency")

		result = sync_leave_types_from_country_config()
		unresolved = set(result["failed"]) | {
			cstr(c.get("leave_type")) for c in result["conflicts"] if isinstance(c, dict)
		}

		for row in declared:
			if row.leave_type in unresolved or not frappe.db.exists("Leave Type", row.leave_type):
				continue
			wanted = _accrual_fields(row)
			if not wanted:
				continue
			actual = frappe.db.get_value(
				"Leave Type", row.leave_type, ["is_earned_leave", "earned_leave_frequency"], as_dict=True
			)
			with self.subTest(country=row.country_code, leave_type=row.leave_type):
				self.assertEqual(cint(actual.is_earned_leave), cint(wanted["is_earned_leave"]))
				if wanted["is_earned_leave"]:
					self.assertEqual(
						cstr(actual.earned_leave_frequency), wanted["earned_leave_frequency"]
					)

	def test_an_accruing_type_is_capped_above_its_annual_entitlement(self):
		"""``allocate_earned_leaves`` stops the moment total_leaves_allocated reaches
		max_leaves_allowed, so a cap at or below the entitlement kills the accrual."""
		for code in get_active_country_codes():
			for row in _declared_rows(code):
				if not _accrual_fields(row).get("is_earned_leave"):
					continue
				if not frappe.db.exists("Leave Type", row.leave_type):
					continue
				cap = flt(frappe.db.get_value("Leave Type", row.leave_type, "max_leaves_allowed"))
				with self.subTest(country=code, leave_type=row.leave_type):
					self.assertGreaterEqual(cap, row.days_per_year)


class TestMonthWindowAllocationsAreRetired(FrappeTestCase):
	"""The old grant model created allocations that expired at month end."""

	def test_the_monthly_job_allocates_nothing(self):
		from hr_suite.hr_suite.tasks import allocate_monthly_leave

		before = frappe.db.count("Leave Allocation")
		allocate_monthly_leave()
		self.assertEqual(frappe.db.count("Leave Allocation"), before)

	def test_no_accruing_leave_type_holds_a_month_window_allocation(self):
		earned = [row.name for row in get_earned_leave_types()]
		if not earned:
			self.skipTest("no leave type on this site accrues yet")

		run_date = getdate(today())
		offenders = [
			alloc
			for alloc in frappe.get_all(
				"Leave Allocation",
				filters={
					"docstatus": 1,
					"leave_type": ["in", earned],
					"from_date": ["<=", run_date],
					"to_date": [">=", run_date],
				},
				fields=["name", "from_date", "to_date"],
			)
			if getdate(alloc.to_date) <= get_last_day(alloc.from_date)
		]
		self.assertEqual(
			offenders,
			[],
			"month-window allocations expire at month end and can never be carried forward",
		)


class TestDoubleAllocationGuard(FrappeTestCase):
	def test_the_report_has_the_documented_shape(self):
		report = check_double_allocation_risk()
		self.assertIn("ok", report)
		self.assertIn("findings", report)
		self.assertIn("earned_leave_types", report)
		self.assertEqual(report["ok"], not report["findings"])
		for finding in report["findings"]:
			self.assertIn("issue", finding)
			self.assertIn("detail", finding)

	def test_accruing_without_a_policy_figure_is_reported(self):
		"""The scheduler divides the Leave Policy's annual_allocation by the frequency,
		so a type nobody put in a policy accrues zero days for ever, silently."""
		leave_type = frappe.get_doc(
			{
				"doctype": "Leave Type",
				"leave_type_name": "_Test Orphaned Earned Leave",
				"is_earned_leave": 1,
				"earned_leave_frequency": "Monthly",
				"allocate_on_day": DEFAULT_ALLOCATE_ON_DAY,
				"max_leaves_allowed": 30,
			}
		).insert(ignore_permissions=True)

		report = check_double_allocation_risk()
		orphaned = [f for f in report["findings"] if f["issue"] == "accrues_without_a_policy_figure"]
		self.assertTrue(orphaned)
		self.assertIn(leave_type.name, orphaned[0]["leave_types"])


class TestYearRollForward(FrappeTestCase):
	def test_the_next_period_starts_the_day_the_current_one_ends(self):
		next_from, next_to = _next_period_dates("2026-01-01", "2026-12-31")
		self.assertEqual(cstr(next_from), "2027-01-01")
		self.assertEqual(cstr(next_to), "2027-12-31")

	def test_a_leap_day_does_not_make_the_periods_overlap(self):
		"""Adding a year to BOTH ends shifts the new period onto the old one and
		LeavePeriod.validate rejects it as an overlap."""
		next_from, next_to = _next_period_dates("2024-01-01", "2024-12-31")
		self.assertEqual(cstr(next_from), "2025-01-01")
		self.assertGreater(getdate(next_to), getdate(next_from))

		following_from, following_to = _next_period_dates(next_from, next_to)
		self.assertEqual(getdate(following_from), getdate(next_to) + _ONE_DAY)
		self.assertGreater(getdate(following_to), getdate(following_from))

	def test_running_it_twice_creates_nothing_new(self):
		if not frappe.db.count("Leave Period"):
			self.skipTest("no Leave Period on this site to roll forward")

		roll_forward_leave_periods(force=1)
		second = roll_forward_leave_periods(force=1)

		self.assertEqual(second["periods_created"], [])
		self.assertEqual(second["assigned"], [])

	def test_every_company_with_a_period_gets_the_next_one(self):
		if not frappe.db.count("Leave Period"):
			self.skipTest("no Leave Period on this site to roll forward")

		roll_forward_leave_periods(force=1)

		for company in frappe.get_all("Company", pluck="name"):
			latest = frappe.get_all(
				"Leave Period",
				filters={"company": company},
				fields=["from_date", "to_date"],
				order_by="to_date desc",
				limit=2,
			)
			if len(latest) < 2:
				continue
			with self.subTest(company=company):
				# The two most recent periods must meet without a gap, or a day of
				# service falls into no period at all and earns nothing.
				self.assertEqual(getdate(latest[0].from_date), getdate(latest[1].to_date) + _ONE_DAY)

