"""HR Payment Advice — the handshake between HR and finance.

These tests read the end state back rather than watching the mechanism: after a
mark_paid the advice must *say* Paid, carry the reference finance gave it, and have
told its source documents. Where the site has no employee to test with, they skip
rather than invent one.

The one thing asserted without any site data is allow_on_submit. Every field this
feature writes after submit is written on a submitted document, and a missing
allow_on_submit turns each of those writes into an UpdateAfterSubmitError that only
shows up the first time finance confirms a real payment.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate, nowdate

from hr_suite.hr_suite.payment_advice import (
	ADVICE_DOCTYPE,
	REFERENCE_DOCTYPE,
	create_payment_advice_for,
	get_payment_advice_for,
	mark_paid,
	paid_status_field,
	payment_advice_needs_approval,
)

# Written by mark_paid() on a submitted advice.
AFTER_SUBMIT_FIELDS = ("status", "payment_reference", "payment_date", "amount_paid", "paid_by", "bank_account")


def _an_employee(count=1):
	"""Active employees whose `employee` field is filled, or [] when the site has none."""
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "employee": ["!=", ""]},
		fields=["name", "company"],
		limit=count,
		order_by="creation asc",
	)


class TestPaymentAdviceMetadata(FrappeTestCase):
	"""Runs on any site, with or without HR data."""

	def test_both_doctypes_are_installed(self):
		self.assertTrue(frappe.db.exists("DocType", ADVICE_DOCTYPE))
		self.assertTrue(frappe.db.exists("DocType", REFERENCE_DOCTYPE))
		self.assertTrue(frappe.get_meta(ADVICE_DOCTYPE).is_submittable)
		self.assertTrue(frappe.get_meta(REFERENCE_DOCTYPE).istable)

	def test_every_field_written_after_submit_allows_it(self):
		meta = frappe.get_meta(ADVICE_DOCTYPE)
		missing = [
			fieldname
			for fieldname in AFTER_SUBMIT_FIELDS
			if not (meta.get_field(fieldname) and meta.get_field(fieldname).allow_on_submit)
		]
		self.assertFalse(
			missing,
			f"{ADVICE_DOCTYPE} fields written after submit without allow_on_submit: {missing}. "
			"mark_paid() would raise UpdateAfterSubmitError.",
		)

		row_status = frappe.get_meta(REFERENCE_DOCTYPE).get_field("reference_status")
		self.assertTrue(row_status.allow_on_submit)

	def test_status_offers_the_whole_route(self):
		options = frappe.get_meta(ADVICE_DOCTYPE).get_field("status").options.split("\n")
		for state in ("Draft", "Pending Approval", "Approved", "Paid", "Cancelled"):
			self.assertIn(state, options)

	def test_naming_series(self):
		self.assertIn("HRPA-.YYYY.-.####", frappe.get_meta(ADVICE_DOCTYPE).get_field("naming_series").options)


class TestPaidStatusField(FrappeTestCase):
	"""Which field the write-back is allowed to touch, and which it must not."""

	def test_end_of_service_keeps_payment_state_on_its_own_field(self):
		if not frappe.db.exists("DocType", "End of Service Benefit"):
			self.skipTest("End of Service Benefit is not installed on this site")
		self.assertEqual(paid_status_field("End of Service Benefit"), "payment_status")

	def test_leave_disbursement_keeps_it_on_status(self):
		if not frappe.db.exists("DocType", "Annual Leave Disbursement"):
			self.skipTest("Annual Leave Disbursement is not installed on this site")
		self.assertEqual(paid_status_field("Annual Leave Disbursement"), "status")

	def test_a_near_miss_option_is_not_a_paid_status(self):
		if not frappe.db.exists("DocType", "Work Injury"):
			self.skipTest("Work Injury is not installed on this site")
		# Work Injury offers "Compensation Paid", which is a different thing.
		self.assertIsNone(paid_status_field("Work Injury"))

	def test_a_doctype_with_no_paid_status_is_left_alone(self):
		self.assertIsNone(paid_status_field("Employee"))


class PaymentAdviceCase(FrappeTestCase):
	"""Shared fixture: an advice against a real employee, cleaned up afterwards."""

	def setUp(self):
		self.created = []
		employees = _an_employee()
		if not employees:
			self.skipTest("No active Employee on this site")
		self.employee = employees[0]

	def tearDown(self):
		for name in self.created:
			try:
				frappe.delete_doc(ADVICE_DOCTYPE, name, force=True, ignore_permissions=True, delete_permanently=True)
			except frappe.DoesNotExistError:
				pass

	def _advice(self, rows=None, submit=True):
		advice = frappe.get_doc(
			{
				"doctype": ADVICE_DOCTYPE,
				"employee": self.employee.name,
				"company": self.employee.company,
				"posting_date": nowdate(),
				"remarks": "Created by test_payment_advice.py",
				"references": rows
				if rows is not None
				else [
					{
						"reference_doctype": "Employee",
						"reference_name": self.employee.name,
						"description": "Test line",
						"amount": 250,
					}
				],
			}
		)
		advice.insert(ignore_permissions=True)
		self.created.append(advice.name)

		if submit:
			advice.submit()

		return advice


class TestPaymentAdviceLifecycle(PaymentAdviceCase):
	def setUp(self):
		super().setUp()
		if payment_advice_needs_approval():
			self.skipTest("An approval workflow covers HR Payment Advice on this site; it cannot be submitted here")

	def test_a_submitted_advice_reaches_finance_with_its_total_spelled_out(self):
		advice = self._advice(
			rows=[
				{"reference_doctype": "Employee", "reference_name": self.employee.name, "description": "Leave salary", "amount": 300},
			]
		)
		advice.reload()

		self.assertEqual(advice.docstatus, 1)
		self.assertEqual(advice.status, "Approved")
		self.assertEqual(flt(advice.total_amount), 300.0)
		self.assertTrue(advice.amount_in_words)
		self.assertEqual(advice.references[0].currency, frappe.get_cached_value("Company", advice.company, "default_currency"))

	def test_mark_paid_leaves_the_advice_saying_paid(self):
		advice = self._advice()

		mark_paid(advice.name, payment_reference="CHQ-00042", payment_date=nowdate(), bank_account=None)

		advice.reload()
		self.assertEqual(advice.status, "Paid")
		self.assertEqual(advice.payment_reference, "CHQ-00042")
		self.assertEqual(flt(advice.amount_paid), flt(advice.total_amount))
		self.assertEqual(advice.payment_date, getdate(nowdate()))
		self.assertTrue(advice.paid_by)

	def test_a_second_confirmation_does_not_rewrite_the_first(self):
		advice = self._advice()
		mark_paid(advice.name, payment_reference="TRF-001", payment_date=nowdate())

		result = mark_paid(advice.name, payment_reference="TRF-999", payment_date=nowdate())

		self.assertTrue(result["already_paid"])
		advice.reload()
		self.assertEqual(advice.payment_reference, "TRF-001")

	def test_a_reference_with_no_paid_status_is_left_untouched(self):
		before = frappe.db.get_value("Employee", self.employee.name, "status")
		advice = self._advice()

		result = mark_paid(advice.name, payment_reference="CHQ-00043", payment_date=nowdate())

		self.assertEqual(result["updated"], [])
		self.assertEqual(frappe.db.get_value("Employee", self.employee.name, "status"), before)
		self.assertFalse(frappe.db.get_value(REFERENCE_DOCTYPE, advice.references[0].name, "reference_status"))

	def test_a_draft_advice_cannot_be_marked_paid(self):
		advice = self._advice(submit=False)
		self.assertRaises(frappe.ValidationError, mark_paid, advice.name, "CHQ-1", nowdate())

	def test_a_paid_advice_cannot_be_cancelled(self):
		advice = self._advice()
		mark_paid(advice.name, payment_reference="CHQ-00044", payment_date=nowdate())

		advice.reload()
		self.assertRaises(frappe.ValidationError, advice.cancel)


class TestPaymentAdviceGuards(PaymentAdviceCase):
	def test_a_reference_row_needs_an_amount(self):
		self.assertRaises(
			frappe.ValidationError,
			self._advice,
			[{"reference_doctype": "Employee", "reference_name": self.employee.name, "amount": 0}],
		)

	def test_the_same_document_cannot_be_listed_twice(self):
		rows = [
			{"reference_doctype": "Employee", "reference_name": self.employee.name, "amount": 100},
			{"reference_doctype": "Employee", "reference_name": self.employee.name, "amount": 100},
		]
		self.assertRaises(frappe.ValidationError, self._advice, rows)

	def test_an_advice_cannot_carry_another_employee(self):
		employees = _an_employee(count=2)
		if len(employees) < 2:
			self.skipTest("Need two active employees to test cross-employee references")

		other = employees[1]
		rows = [{"reference_doctype": "Employee", "reference_name": other.name, "amount": 100}]
		self.assertRaises(frappe.ValidationError, self._advice, rows)

	def test_an_advice_needs_at_least_one_reference(self):
		self.assertRaises(frappe.ValidationError, self._advice, [])


class TestPaymentAdviceIdempotency(PaymentAdviceCase):
	"""One source document, one claim on the money — however many times it asks."""

	def setUp(self):
		super().setUp()
		# A leftover advice from a crashed run would be picked up by the idempotency
		# lookup and make these assertions meaningless.
		if get_payment_advice_for("Employee", self.employee.name):
			self.skipTest("An advice already exists for this employee; clear it before running this test")

	def test_raising_twice_returns_the_same_advice(self):
		source = frappe.get_doc("Employee", self.employee.name)
		lines = [{"amount": 175, "description": "Leave salary advance"}]

		first = create_payment_advice_for(source, lines, description="Leave salary advance")
		self.created.append(first.name)
		second = create_payment_advice_for(source, lines, description="Leave salary advance")

		self.assertEqual(first.name, second.name)
		self.assertEqual(
			frappe.db.count(ADVICE_DOCTYPE, {"source_doctype": "Employee", "source_name": self.employee.name}), 1
		)

	def test_the_advice_records_what_raised_it(self):
		source = frappe.get_doc("Employee", self.employee.name)
		advice = create_payment_advice_for(source, [{"amount": 50, "description": "Ticket"}])
		self.created.append(advice.name)

		advice.reload()
		self.assertEqual(advice.source_doctype, "Employee")
		self.assertEqual(advice.source_name, self.employee.name)
		self.assertTrue(advice.auto_generated)
		self.assertEqual(advice.references[0].reference_doctype, "Employee")
		self.assertEqual(advice.references[0].reference_name, self.employee.name)
		self.assertEqual(flt(advice.total_amount), 50.0)
		self.assertEqual(get_payment_advice_for("Employee", self.employee.name), advice.name)

	def test_zero_lines_never_reach_finance(self):
		source = frappe.get_doc("Employee", self.employee.name)
		self.assertRaises(frappe.ValidationError, create_payment_advice_for, source, [{"amount": 0}])
