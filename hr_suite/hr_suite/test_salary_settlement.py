# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Salary Settlement pays what a month has earned so far, and payroll takes it back.

Every assertion below reads a figure back off a saved document rather than checking
that some function was called. The two that matter most are invariants, not numbers:

  * a settlement covering a WHOLE calendar month must come to exactly what the salary
    structure pays for that month — whatever Payroll Settings says about holidays, and
    whatever holiday list the employee is on. Any wrong divisor breaks this;
  * two settlements that split one month between them must, for the components payroll
    prorates, add up to the whole-month settlement. A divisor that is right on average
    and wrong per-month passes the first test and fails this one.

Nothing here hard-codes a salary, a working-day count or a component name: those are
site data, and a test that supplies its own would be testing itself. Each case skips
cleanly when the site carries no employee it can settle.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, cint, flt, get_first_day, get_last_day, getdate

from hr_suite.hr_suite.doctype.payroll_preview.payroll_preview import (
	DEDUCTION,
	EARNING,
	INFORMATION,
)
from hr_suite.hr_suite.doctype.salary_settlement.salary_settlement import (
	SETTLEMENT_RECOVERY_COMPONENT,
)


def find_settleable_employee():
	"""An employee this site can actually settle, or None.

	Needs a submitted Salary Structure Assignment AND a populated salary mirror — the
	controller can rebuild an empty mirror by asking HRMS for a throwaway slip, but a
	test that triggers that is testing employee_salary.py, not this document.
	"""
	assignments = frappe.get_all(
		"Salary Structure Assignment",
		filters={"docstatus": 1},
		fields=["employee", "company", "base", "from_date"],
		order_by="from_date desc",
		limit=200,
	)
	for assignment in assignments:
		if not frappe.db.exists("Employee", assignment.employee):
			continue

		earnings = frappe.get_all(
			"Employee Salary Component",
			filters={
				"parenttype": "Employee",
				"parent": assignment.employee,
				"component_type": EARNING,
			},
			fields=["salary_component", "amount", "depends_on_payment_days"],
		)
		if not any(flt(row.amount) > 0 for row in earnings):
			continue

		month = whole_month_inside_employment(assignment)
		if not month:
			continue

		assignment.earnings = earnings
		assignment.month_start, assignment.month_end = month
		return assignment

	return None


def whole_month_inside_employment(assignment):
	"""(month_start, month_end) for a month the employee worked end to end, or None."""
	employee = (
		frappe.db.get_value(
			"Employee", assignment.employee, ["date_of_joining", "relieving_date"], as_dict=True
		)
		or frappe._dict()
	)

	earliest = getdate(assignment.from_date)
	if employee.date_of_joining and getdate(employee.date_of_joining) > earliest:
		earliest = getdate(employee.date_of_joining)

	month_start = get_first_day(add_months(earliest, 1))
	month_end = get_last_day(month_start)

	if employee.relieving_date and getdate(employee.relieving_date) < month_end:
		return None

	return month_start, month_end


def draft_settlement(assignment, period_from, period_to, settlement_date, reason="Going on Leave"):
	doc = frappe.get_doc({
		"doctype": "Salary Settlement",
		"employee": assignment.employee,
		"company": assignment.company,
		"reason": reason,
		"settlement_date": settlement_date,
		"period_from": period_from,
		"period_to": period_to,
	})
	doc.insert(ignore_permissions=True)
	return doc


def force_disbursement(assignment, leave_from, leave_to):
	"""A minimal Annual Leave Disbursement row, forced to docstatus 1 — enough for
	Salary Settlement's own ``_disbursed_leave_dates`` to find it by employee and
	date range, without going through the disbursement's OWN balance and Country
	Config checks. Those are annual_leave_disbursement.py's business rules, not
	the ones under test here — the same reasoning
	test_an_overlapping_submitted_settlement_is_refused already applies to a
	Salary Settlement fixture below.

	None if this site has no Leave Type at all to point the row at.
	"""
	leave_type = frappe.db.get_value("Leave Type", {}, "name")
	if not leave_type:
		return None

	ald = frappe.get_doc({
		"doctype": "Annual Leave Disbursement",
		"employee": assignment.employee,
		"company": assignment.company,
		"leave_type": leave_type,
		"leave_from_date": leave_from,
		"leave_to_date": leave_to,
	})
	ald.flags.ignore_validate = True
	ald.flags.ignore_mandatory = True
	ald.insert(ignore_permissions=True)
	frappe.db.set_value("Annual Leave Disbursement", ald.name, "docstatus", 1)
	return ald.name


def prorated_earnings(doc, prorated_components) -> float:
	"""Only the components the Salary Slip scales by payment days."""
	return flt(
		sum(
			flt(line.payable_amount)
			for line in doc.lines
			if line.entry_type == EARNING and line.salary_component in prorated_components
		),
		6,
	)



class SavepointTestCase(FrappeTestCase):
	"""A test case that undoes its OWN documents, test by test.

	``FrappeTestCase`` registers its rollback with ``addClassCleanup``, so everything a
	test writes stays visible to the tests that follow it in the same class — and these
	suites run against a REAL site, where a submitted document left behind by one test
	makes the next one refuse ("this period has already been disbursed"), and an
	interrupted run leaves it on the site for good. A savepoint per test is the cheap
	fix: class-level fixtures built in ``setUpClass`` survive, the test's own writes do
	not.
	"""

	def setUp(self):
		super().setUp()
		self._savepoint = "hr_suite_{0}".format(type(self).__name__.lower())
		frappe.db.savepoint(self._savepoint)

	def tearDown(self):
		frappe.db.rollback(save_point=self._savepoint)
		super().tearDown()

class TestSalarySettlementContract(FrappeTestCase):
	"""What the DocType promises, checked without needing a single employee."""

	def test_it_is_submittable_and_series_named(self):
		meta = frappe.get_meta("Salary Settlement")
		self.assertTrue(meta.is_submittable)
		self.assertIn("SETL-", meta.get_field("naming_series").options)

	def test_every_post_submit_field_allows_it(self):
		"""The controller writes these after docstatus 1.

		Without allow_on_submit Frappe throws UpdateAfterSubmitError the moment somebody
		records the payment advice, and the settlement can never be marked paid.
		"""
		meta = frappe.get_meta("Salary Settlement")
		for fieldname in (
			"status",
			"journal_entry",
			"recovery_booked",
			"annual_leave_disbursement",
			"payment_advice_type",
			"payment_advice",
			"remarks",
		):
			with self.subTest(field=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field, f"{fieldname} is missing from Salary Settlement")
				self.assertTrue(
					cint(field.allow_on_submit),
					f"{fieldname} is written after submit but has no allow_on_submit",
				)

	def test_lines_reuse_the_payroll_preview_row(self):
		"""The shared child table is what keeps the two screens agreeing by construction."""
		field = frappe.get_meta("Salary Settlement").get_field("lines")
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Payroll Preview Allocation")

	def test_recovery_component_is_not_scaled_by_payment_days(self):
		"""The advance was a fixed sum. A recovery that shrinks with the month gives less
		back than was handed over, and the difference is never collected again."""
		if not frappe.db.exists("Salary Component", SETTLEMENT_RECOVERY_COMPONENT):
			self.skipTest("Settlement recovery component not created on this site yet")

		component = frappe.db.get_value(
			"Salary Component",
			SETTLEMENT_RECOVERY_COMPONENT,
			["type", "depends_on_payment_days"],
			as_dict=True,
		)
		self.assertEqual(component.type, "Deduction")
		self.assertFalse(cint(component.depends_on_payment_days))


class TestSalarySettlementProration(SavepointTestCase):
	"""The divisor, checked against payroll's own by invariant rather than by formula."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.assignment = find_settleable_employee()

	def setUp(self):
		super().setUp()
		if not self.assignment:
			self.skipTest("No employee on this site has a submitted Salary Structure Assignment "
			              "and a populated salary mirror")

	def test_a_whole_month_settles_to_the_whole_structure(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		doc = draft_settlement(self.assignment, month_start, month_end, month_end)

		expected = flt(
			sum(flt(row.amount) for row in self.assignment.earnings),
			doc.precision("net_payable"),
		)
		self.assertAlmostEqual(
			flt(doc.earned_amount),
			expected,
			places=2,
			msg="A settlement covering the entire month must equal the month's own salary",
		)

	def test_the_halves_of_a_month_add_up_to_the_month(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		midpoint = add_days(month_start, 14)
		if getdate(midpoint) >= getdate(month_end):
			self.skipTest("Month too short to split")

		prorated = {
			row.salary_component
			for row in self.assignment.earnings
			if cint(row.depends_on_payment_days)
		}
		if not prorated:
			self.skipTest("This employee has no component that depends on payment days")

		whole = draft_settlement(self.assignment, month_start, month_end, month_end)
		first = draft_settlement(self.assignment, month_start, midpoint, midpoint)
		second = draft_settlement(
			self.assignment, add_days(midpoint, 1), month_end, month_end
		)

		self.assertAlmostEqual(
			prorated_earnings(first, prorated) + prorated_earnings(second, prorated),
			prorated_earnings(whole, prorated),
			places=2,
			msg="Two halves of a month must pro-rate to the same money as the whole month",
		)

	def test_a_partial_month_pays_less_than_the_whole(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		midpoint = add_days(month_start, 14)
		if getdate(midpoint) >= getdate(month_end):
			self.skipTest("Month too short to split")

		if not any(cint(row.depends_on_payment_days) for row in self.assignment.earnings):
			self.skipTest("This employee has no component that depends on payment days")

		whole = draft_settlement(self.assignment, month_start, month_end, month_end)
		half = draft_settlement(self.assignment, month_start, midpoint, midpoint)

		self.assertLess(flt(half.earned_amount), flt(whole.earned_amount))
		self.assertGreater(flt(half.earned_amount), 0)
		self.assertGreater(flt(half.earned_days), 0)
		self.assertLess(flt(half.earned_days), flt(whole.earned_days))


class TestSalarySettlementLeaveOverlap(SavepointTestCase):
	"""A day already paid as leave salary is never also paid as ordinary salary."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.assignment = find_settleable_employee()

	def setUp(self):
		super().setUp()
		if not self.assignment:
			self.skipTest("No employee on this site can be settled")

	def test_disbursed_days_drop_out_of_earned_days(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		overlap_from = add_days(month_start, 4)
		overlap_to = add_days(month_start, 9)

		without = draft_settlement(self.assignment, month_start, month_end, month_end)

		ald_name = force_disbursement(self.assignment, overlap_from, overlap_to)
		if not ald_name:
			self.skipTest("No Leave Type exists on this site to build a throwaway disbursement")

		with_overlap = draft_settlement(self.assignment, month_start, month_end, month_end)

		delta = flt(without.earned_days) - flt(with_overlap.earned_days)
		self.assertGreater(
			delta, 0,
			msg="A disbursement overlapping the settlement window must reduce earned days",
		)
		self.assertLessEqual(
			delta, 6.0,
			msg="A 6-day disbursement cannot exclude more than 6 days, holidays already netted out",
		)
		self.assertIn(
			ald_name, with_overlap.proration_basis,
			msg="The basis line must name the disbursement it excluded, not just a smaller number",
		)

	def test_absorbed_disbursement_cancels_its_own_recovery_row(self):
		"""annual_leave_disbursement.cancel_recovery_not_yet_taken, called from
		_cancel_absorbed_disbursement_recovery, without dragging a real settlement
		submit (Journal Entry, payroll payable account) into this test."""
		ald_name = force_disbursement(
			self.assignment,
			self.assignment.month_start,
			add_days(self.assignment.month_start, 4),
		)
		if not ald_name:
			self.skipTest("No Leave Type exists on this site to build a throwaway disbursement")

		component = frappe.db.get_value("Salary Component", {"type": "Deduction"}, "name")
		if not component:
			self.skipTest("No Deduction-type Salary Component exists on this site")

		additional_salary = frappe.get_doc({
			"doctype": "Additional Salary",
			"employee": self.assignment.employee,
			"company": self.assignment.company,
			"currency": frappe.get_cached_value("Company", self.assignment.company, "default_currency"),
			"salary_component": component,
			"amount": 1,
			"payroll_date": self.assignment.month_start,
			"ref_doctype": "Annual Leave Disbursement",
			"ref_docname": ald_name,
			"overwrite_salary_structure_amount": 0,
		})
		try:
			additional_salary.insert(ignore_permissions=True)
			additional_salary.submit()
		except frappe.ValidationError as e:
			self.skipTest(f"This site's own Additional Salary rules refused the fixture: {e}")

		from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
			cancel_recovery_not_yet_taken,
		)

		already_taken = cancel_recovery_not_yet_taken(ald_name)

		self.assertEqual(already_taken, [])
		self.assertEqual(
			frappe.db.get_value("Additional Salary", additional_salary.name, "docstatus"), 2
		)


class TestSalarySettlementTotals(SavepointTestCase):
	"""What reaches the net, and what deliberately does not."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.assignment = find_settleable_employee()

	def setUp(self):
		super().setUp()
		if not self.assignment:
			self.skipTest("No employee on this site can be settled")

		self.doc = draft_settlement(
			self.assignment,
			self.assignment.month_start,
			self.assignment.month_end,
			self.assignment.month_end,
		)

	def test_the_net_is_earnings_minus_deductions(self):
		self.assertAlmostEqual(
			flt(self.doc.net_payable),
			flt(self.doc.total_earnings) - flt(self.doc.total_deductions),
			places=2,
		)
		self.assertAlmostEqual(
			flt(self.doc.total_earnings),
			flt(self.doc.earned_amount) + flt(self.doc.leave_salary_amount),
			places=2,
		)

	def test_information_rows_move_no_money(self):
		"""An Information row is something the month's payslip already carries.

		Letting one contribute to the net is how a loan instalment gets deducted twice —
		once from the settlement cash and once again from the payslip.
		"""
		information = [line for line in self.doc.lines if line.entry_type == INFORMATION]
		if not information:
			self.skipTest("Nothing booked into payroll for this employee in this period")

		for line in information:
			with self.subTest(source=line.source_name):
				self.assertEqual(flt(line.payable_amount), 0.0)

		self.assertAlmostEqual(
			flt(self.doc.total_deductions),
			flt(
				sum(
					flt(line.payable_amount)
					for line in self.doc.lines
					if line.entry_type == DEDUCTION
				)
			),
			places=2,
		)

	def test_advances_listed_match_payroll_preview(self):
		"""The settlement and the Payroll Preview read the same advances, or neither is
		trustworthy — one of them is wrong about what the employee owes."""
		preview = frappe.new_doc("Payroll Preview")
		preview.company = self.doc.company
		preview.start_date = self.doc.period_from
		preview.end_date = self.doc.settlement_date

		additional_salaries = preview._get_additional_salaries([self.doc.employee])
		expected = {
			row.name
			for row in preview._get_employee_advances([self.doc.employee], additional_salaries)
			if flt(row.pending_amount) > 0
		}
		listed = {
			line.source_name
			for line in self.doc.lines
			if line.source_doctype == "Employee Advance"
		}

		self.assertEqual(expected, listed)


class TestSalarySettlementRefusals(SavepointTestCase):
	"""The three settlements this document must not let anybody save."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.assignment = find_settleable_employee()

	def setUp(self):
		super().setUp()
		if not self.assignment:
			self.skipTest("No employee on this site can be settled")

	def test_settling_before_the_period_starts_is_refused(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		with self.assertRaises(frappe.ValidationError):
			draft_settlement(
				self.assignment, month_start, month_end, add_days(month_start, -1)
			)

	def test_settling_after_the_period_ends_is_refused(self):
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		with self.assertRaises(frappe.ValidationError):
			draft_settlement(
				self.assignment, month_start, add_days(month_start, 5), month_end
			)

	def test_an_overlapping_submitted_settlement_is_refused(self):
		"""The guard reads docstatus straight out of the table, so the first settlement is
		marked submitted directly. Running the real submit would drag the Journal Entry,
		the payroll payable account and the recovery component into a test about a date
		comparison, and would skip on every site whose accounts are not mapped."""
		month_start, month_end = self.assignment.month_start, self.assignment.month_end
		existing = draft_settlement(self.assignment, month_start, month_end, month_end)
		frappe.db.set_value("Salary Settlement", existing.name, "docstatus", 1)

		with self.assertRaises(frappe.ValidationError):
			draft_settlement(
				self.assignment,
				add_days(month_start, 3),
				add_days(month_start, 10),
				add_days(month_start, 10),
			)

	def test_an_employee_without_a_salary_structure_is_refused(self):
		assigned = set(
			frappe.get_all("Salary Structure Assignment", filters={"docstatus": 1}, pluck="employee")
		)
		candidate = next(
			(
				row
				for row in frappe.get_all(
					"Employee",
					filters={"status": "Active"},
					fields=["name", "company", "date_of_joining"],
					limit=200,
				)
				if row.name not in assigned and row.date_of_joining
			),
			None,
		)
		if not candidate:
			self.skipTest("Every active employee on this site has a Salary Structure Assignment")

		# A month this candidate was already employed for, so the refusal under test is the
		# missing structure and not the employment-window clamp.
		month_start = get_first_day(add_months(getdate(candidate.date_of_joining), 1))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Salary Settlement",
				"employee": candidate.name,
				"company": candidate.company,
				"reason": "Going on Leave",
				"settlement_date": get_last_day(month_start),
				"period_from": month_start,
				"period_to": get_last_day(month_start),
			}).insert(ignore_permissions=True)
