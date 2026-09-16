"""Leave salary is paid once and recovered once.

These tests assert the state the site is left in — what the allocation says, what the
Additional Salary rows add up to, what survives a cancellation — rather than which
method produced it. Each one skips cleanly when the site has no employee the whole
chain can actually run on, because a site without a Leave Allocation or a Salary
Structure Assignment cannot disburse leave at all and a test that invented one would
be testing its own fixture.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, today

from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
	get_allocation_balance,
	get_leave_allocation,
)
from hr_suite.hr_suite.utils import (
	compute_leave_salary,
	get_employee_salary_components,
	get_leave_salary_recovery_component,
	get_leave_salary_terms,
	split_days_by_month,
)

DISBURSED_DAYS = 5


def find_disbursable_employee():
	"""An employee with an allocation, a salary and a live leave window, or None."""
	if not frappe.db.exists("DocType", "Leave Allocation"):
		return None

	allocations = frappe.get_all(
		"Leave Allocation",
		filters={"docstatus": 1, "to_date": [">=", today()]},
		fields=["name", "employee", "leave_type", "from_date", "to_date", "total_leaves_allocated"],
		order_by="total_leaves_allocated desc",
		limit=50,
	)

	for allocation in allocations:
		if flt(allocation.total_leaves_allocated) < DISBURSED_DAYS:
			continue
		if frappe.db.get_value("Employee", allocation.employee, "status") != "Active":
			continue
		if frappe.db.get_value("Employee", allocation.employee, "relieving_date"):
			continue
		if not frappe.db.exists(
			"Salary Structure Assignment", {"employee": allocation.employee, "docstatus": 1}
		):
			continue

		salary = get_employee_salary_components(allocation.employee) or {}
		if flt(salary.get("basic_salary")) <= 0:
			continue

		period = leave_period_inside(allocation)
		if not period:
			continue
		if get_allocation_balance(
			allocation.employee, allocation.leave_type, period[0], allocation
		) < DISBURSED_DAYS:
			continue

		allocation.leave_from_date, allocation.leave_to_date = period
		return allocation

	return None


def leave_period_inside(allocation):
	"""A short leave that straddles a month end, so the split has two months to find."""
	for months_ahead in (1, 0, 2):
		start = add_days(get_last_day(add_months(today(), months_ahead)), -2)
		end = add_days(start, DISBURSED_DAYS - 1)
		if getdate(start) >= getdate(allocation.from_date) and getdate(end) <= getdate(allocation.to_date):
			return getdate(start), getdate(end)
	return None


def build_disbursement(allocation, **overrides):
	doc = frappe.get_doc({
		"doctype": "Annual Leave Disbursement",
		"naming_series": "ALD-.YYYY.-.####",
		"employee": allocation.employee,
		"leave_type": allocation.leave_type,
		"leave_from_date": allocation.leave_from_date,
		"leave_to_date": allocation.leave_to_date,
		"leave_days_to_pay": DISBURSED_DAYS,
	})
	doc.update(overrides)
	return doc



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

class TestLeaveSalaryArithmetic(FrappeTestCase):
	"""The month split and the pricing, neither of which needs a site with data."""

	def test_split_covers_every_day_exactly_once(self):
		chunks = split_days_by_month("2026-03-12", "2026-04-01")

		self.assertEqual([str(month) for month, _days in chunks], ["2026-03-01", "2026-04-01"])
		self.assertEqual([days for _month, days in chunks], [20, 1])
		self.assertEqual(sum(days for _month, days in chunks), 21)

	def test_split_inside_one_month_is_one_chunk(self):
		chunks = split_days_by_month("2026-06-05", "2026-06-09")

		self.assertEqual(len(chunks), 1)
		self.assertEqual(chunks[0][0], getdate(get_first_day("2026-06-05")))
		self.assertEqual(chunks[0][1], 5)

	def test_split_refuses_a_backwards_period(self):
		self.assertEqual(split_days_by_month("2026-06-09", "2026-06-05"), [])

	def test_price_follows_country_config_not_a_thirty_day_month(self):
		employee = frappe.db.get_value(
			"Employee", {"status": "Active"}, "name", order_by="creation desc"
		)
		if not employee:
			self.skipTest("No Active Employee on this site")

		salary = get_employee_salary_components(employee) or {}
		if flt(salary.get("basic_salary")) <= 0:
			self.skipTest(f"{employee} has no basic salary to price leave from")

		terms = get_leave_salary_terms(employee)
		priced = compute_leave_salary(employee, DISBURSED_DAYS)

		# The total is the sum of the component lines, and each line is that component
		# over the country's month — not over 30.
		self.assertAlmostEqual(priced["total"], sum(priced["lines"].values()), places=2)
		for component_field, amount in priced["lines"].items():
			expected = flt(salary[component_field]) / flt(terms["days_per_month"]) * DISBURSED_DAYS
			self.assertAlmostEqual(amount, expected, places=2)

		# Components the country does not pay during leave contribute nothing.
		self.assertFalse(set(priced["lines"]) - set(terms["components"]))
		self.assertTrue(terms["basis"])


class TestLeaveSalaryRecoveryComponent(SavepointTestCase):
	def test_recovery_component_is_a_deduction_that_ignores_payment_days(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("No Company on this site")

		name = get_leave_salary_recovery_component(company, "")
		component = frappe.get_doc("Salary Component", name)

		self.assertEqual(component.type, "Deduction")
		# The advance was a fixed sum; scaling it by the month's payment days would give
		# back less than was handed over, and a leave month is exactly the month whose
		# payment days are unusual.
		self.assertEqual(component.depends_on_payment_days, 0)


class TestAnnualLeaveDisbursement(SavepointTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.allocation = find_disbursable_employee()

	def setUp(self):
		super().setUp()
		if not self.allocation:
			self.skipTest("No employee on this site has an allocation, a salary and a free leave window")

		# Submitting refuses outright when the recovery component has no account for the
		# company, because paying leave salary that payroll cannot claw back pays the same
		# days twice. That is a site configuration gap, not a defect to fail a test on.
		from hr_suite.hr_suite.integrations.hrms import ensure_salary_component_account

		company = frappe.db.get_value("Employee", self.allocation.employee, "company")
		component = get_leave_salary_recovery_component(company, "")
		postable, reason = ensure_salary_component_account(
			component, company, component_type="Deduction", depends_on_payment_days=0
		)
		if not postable:
			self.skipTest(reason)

	def test_submit_books_one_recovery_per_payroll_month(self):
		doc = build_disbursement(self.allocation)
		doc.insert()
		doc.submit()

		doc.reload()
		months = split_days_by_month(doc.leave_from_date, doc.leave_to_date)
		rows = frappe.get_all(
			"Additional Salary",
			filters={"ref_doctype": doc.doctype, "ref_docname": doc.name, "docstatus": 1},
			fields=["name", "amount", "payroll_date", "type", "salary_component",
					"overwrite_salary_structure_amount", "is_recurring"],
		)

		self.assertEqual(len(rows), len(months))
		self.assertGreater(len(months), 1, "the chosen period should straddle a month end")

		# Payroll reads Deduction rows whose payroll_date lands inside the slip period, so
		# a row of the wrong type or in the wrong month is never recovered at all.
		booked_months = sorted({get_first_day(row.payroll_date) for row in rows})
		self.assertEqual(booked_months, sorted(month for month, _days in months))
		for row in rows:
			self.assertEqual(row.type, "Deduction")
			self.assertEqual(row.is_recurring, 0)
			self.assertEqual(row.overwrite_salary_structure_amount, 0)

		# What is taken back equals what was advanced, to the fils.
		self.assertAlmostEqual(
			sum(flt(row.amount) for row in rows),
			flt(doc.leave_salary_recovery_amount),
			places=3,
		)

	def test_the_ticket_is_paid_but_never_recovered(self):
		ticket = 500.0
		doc = build_disbursement(self.allocation, ticket_entitled=1, ticket_amount=ticket)
		doc.insert()
		doc.submit()
		doc.reload()

		# Paid: the ticket rides on the total. Not recovered: it is an entitlement, not an
		# advance of salary, so payroll must not claw it back.
		self.assertAlmostEqual(
			flt(doc.total_leave_pay), flt(doc.leave_salary_recovery_amount) + ticket, places=3
		)

		recovered = sum(
			flt(amount)
			for amount in frappe.get_all(
				"Additional Salary",
				filters={"ref_doctype": doc.doctype, "ref_docname": doc.name, "docstatus": 1},
				pluck="amount",
			)
		)
		self.assertAlmostEqual(recovered, flt(doc.leave_salary_recovery_amount), places=3)
		self.assertLess(recovered, flt(doc.total_leave_pay))

	def test_submit_records_the_basis_and_the_journal_entry(self):
		doc = build_disbursement(self.allocation)
		doc.insert()
		self.assertTrue(doc.leave_salary_basis, "HR must be able to see which country rule applied")

		doc.submit()
		doc.reload()

		if not doc.linked_payroll_entry:
			# No salary expense or payable account is mapped on this site; the controller
			# says so instead of posting to an arbitrary account.
			self.skipTest("Site has no salary expense/payable accounts to post against")

		je = frappe.get_doc("Journal Entry", doc.linked_payroll_entry)
		self.assertIn(je.docstatus, (0, 1))
		self.assertAlmostEqual(flt(je.total_debit), flt(doc.total_leave_pay), places=2)
		self.assertIn(doc.name, je.user_remark or "")

	def test_cancel_strands_no_deduction_on_a_future_payslip(self):
		doc = build_disbursement(self.allocation)
		doc.insert()
		doc.submit()
		journal_entry = doc.linked_payroll_entry

		doc.reload()
		doc.cancel()
		doc.reload()

		self.assertEqual(
			frappe.get_all(
				"Additional Salary",
				filters={"ref_doctype": doc.doctype, "ref_docname": doc.name, "docstatus": 1},
				pluck="name",
			),
			[],
		)
		self.assertEqual(doc.status, "Cancelled")

		if journal_entry:
			# Either cancelled, or deleted because it was still a draft awaiting approval —
			# what must not survive is a postable entry for a disbursement that is gone.
			docstatus = frappe.db.get_value("Journal Entry", journal_entry, "docstatus")
			self.assertIn(docstatus, (2, None))

	def test_the_same_period_cannot_be_disbursed_twice(self):
		doc = build_disbursement(self.allocation)
		doc.insert()
		doc.submit()

		before = frappe.db.count("Annual Leave Disbursement", {"employee": self.allocation.employee})

		with self.assertRaises(frappe.ValidationError):
			build_disbursement(self.allocation).insert()

		self.assertEqual(
			frappe.db.count("Annual Leave Disbursement", {"employee": self.allocation.employee}),
			before,
		)

	def test_more_days_than_the_allocation_holds_is_refused(self):
		balance = get_allocation_balance(
			self.allocation.employee,
			self.allocation.leave_type,
			self.allocation.leave_from_date,
			self.allocation,
		)
		over = flt(balance) + 10
		doc = build_disbursement(
			self.allocation,
			leave_to_date=add_days(self.allocation.leave_from_date, int(over) - 1),
			leave_days_to_pay=over,
		)

		before = frappe.db.count("Annual Leave Disbursement", {"employee": self.allocation.employee})
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

		self.assertEqual(
			frappe.db.count("Annual Leave Disbursement", {"employee": self.allocation.employee}),
			before,
		)

	def test_the_allocation_on_file_is_the_hrms_one(self):
		doc = build_disbursement(self.allocation)
		doc.insert()

		allocation = get_leave_allocation(
			self.allocation.employee, self.allocation.leave_type, self.allocation.leave_from_date
		)
		self.assertEqual(doc.leave_allocation, allocation.name)
		self.assertEqual(
			flt(doc.leave_days_entitled), flt(allocation.total_leaves_allocated)
		)
