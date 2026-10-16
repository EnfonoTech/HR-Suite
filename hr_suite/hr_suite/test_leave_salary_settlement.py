"""Phase 4 - Leave Salary Settlement: pricing, the barrier, payroll exclusion and the return."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from hr_suite.hr_suite.doctype.leave_salary_settlement.leave_salary_settlement import (
	price_settlement,
	record_rejoin,
)
from hr_suite.hr_suite.leave_accrual import get_salary_days_balance
from hr_suite.hr_suite.test_leave_accrual_ledger import COMPANY, LedgerTestBase


def price(**over):
	"""The spec's worked example: salary 4,000 over 30 days, last working day the 10th."""
	args = dict(
		leave_days=30, paid_days_before=0, earned_balance=40, min_earned=30, service_days=800, min_service=365,
		below_barrier_allowed=False, monthly_gross=4000, days_worked=10, pays_worked_days=True, is_first=True,
		leave_monthly=4000, days_per_month=30, ticket_due=False, ticket_amount=0, previously_paid=0,
	)
	args.update(over)
	return price_settlement(**args)


class TestPricing(FrappeTestCase):
	def test_spec_example_pay_worked_days_yes(self):
		# worked 1st-10th 1,333.33 + leave salary 4,000.00 = 5,333.33
		result = price()
		self.assertEqual(result.worked_pay, 1333.333)
		self.assertEqual(result.leave_salary, 4000)
		self.assertEqual(result.total, 5333.333)

	def test_spec_example_pay_worked_days_no(self):
		result = price(pays_worked_days=False)
		self.assertEqual(result.worked_pay, 0)
		self.assertEqual(result.total, 4000)

	def test_both_minimums_must_be_met(self):
		short_balance = price(earned_balance=20)
		self.assertFalse(short_balance.eligible)
		self.assertEqual(short_balance.leave_salary, 0)
		self.assertEqual(short_balance.unpaid_days, 30)
		self.assertIn("earned salary days", short_balance.shortfall)
		self.assertEqual(short_balance.worked_pay, 1333.333)  # the worked days are still paid

		short_service = price(service_days=200)
		self.assertEqual(short_service.leave_salary, 0)
		self.assertIn("service", short_service.shortfall)

	def test_hr_override_pays_only_what_is_earned(self):
		result = price(earned_balance=12, below_barrier_allowed=True)
		self.assertEqual(result.paid_days, 12)
		self.assertEqual(result.unpaid_days, 18)
		self.assertEqual(result.leave_salary, 1600)

	def test_partial_payout_when_balance_covers_part(self):
		result = price(earned_balance=35, leave_days=45)
		self.assertEqual(result.paid_days, 35)
		self.assertEqual(result.unpaid_days, 10)

	def test_a_later_settlement_pays_neither_worked_days_nor_ticket(self):
		result = price(is_first=False, paid_days_before=12, earned_balance=35, ticket_due=True, ticket_amount=1500)
		self.assertEqual(result.worked_pay, 0)
		self.assertEqual(result.ticket, 0)
		self.assertEqual(result.due, 18)
		self.assertEqual(result.paid_days, 18)

	def test_ticket_and_previously_paid(self):
		result = price(ticket_due=True, ticket_amount=1500, previously_paid=1000)
		self.assertEqual(result.total, 5833.333)  # 1,333.333 + 4,000 + 1,500 - 1,000

	def test_never_negative(self):
		self.assertEqual(price(previously_paid=999999).total, 0)

	def test_a_zero_leave_salary_is_not_an_error(self):
		self.assertEqual(price(earned_balance=0, pays_worked_days=False).total, 0)


class SettlementTestBase(LedgerTestBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		hl = frappe.get_doc(doctype="Holiday List", holiday_list_name="HRS LSS HL", from_date="2026-01-01", to_date="2026-12-31")
		hl.insert(ignore_permissions=True)
		frappe.db.set_value("Company", COMPANY, "default_holiday_list", hl.name)

	def setUp(self):
		self.booked = []
		counter = iter(range(1, 100))

		def fake_book(doc, component, currency, payroll_date, amount):
			name = "AS-FAKE-%s" % next(counter)
			self.booked.append({"name": name, "date": str(payroll_date), "amount": flt(amount, 3)})
			return name

		patches = [
			patch("hr_suite.hr_suite.leave_payroll.prepare_component", return_value=("Leave Salary Recovery", "SAR")),
			patch("hr_suite.hr_suite.leave_payroll.book_deduction", side_effect=fake_book),
			patch(
				"hr_suite.hr_suite.doctype.leave_salary_settlement.leave_salary_settlement.LeaveSalarySettlement._expense_account",
				return_value="",
			),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)
		# The optional second barrier (earned days) is off by default; most tests here exercise it.
		self.set_country(leave_salary_min_earned_days=30)

	def staff(self, name, opening=40, ctc=4000, joined="2020-01-01"):
		emp = self.employee(name, "SA", joined)
		frappe.db.set_value("Employee", emp, "ctc", ctc)
		if opening:
			frappe.get_doc(
				doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="2026-03-31",
				leave_days=opening, salary_days=opening,
			).insert(ignore_permissions=True)
		return emp

	def leave(self, emp, start="2026-04-11", end="2026-05-10"):
		la = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="Annual Leave", from_date=start, to_date=end,
			status="Approved", company=COMPANY,
		)
		la.insert(ignore_permissions=True)
		la.submit()
		return la.name

	def settle(self, emp, la, submit=True, **fields):
		doc = frappe.get_doc(
			doctype="Leave Salary Settlement", employee=emp, leave_application=la, last_working_day="2026-04-10", **fields
		)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	def set_country(self, **values):
		"""Change the Saudi Country Config for one test only; the original is restored afterwards."""
		cfg = frappe.get_doc("Country Config", "SA")
		original = {field: cfg.get(field) for field in values}
		for field, value in values.items():
			cfg.set(field, value)
		cfg.save(ignore_permissions=True)

		def restore():
			again = frappe.get_doc("Country Config", "SA")
			for field, value in original.items():
				again.set(field, value)
			again.save(ignore_permissions=True)

		self.addCleanup(restore)

	def set_pays_worked_days(self, value):
		self.set_country(pay_worked_days_in_settlement=value)


class TestSettlementDocument(SettlementTestBase):
	def test_priced_from_the_ledger_and_the_policy(self):
		emp = self.staff("Priced")
		doc = self.settle(emp, self.leave(emp), submit=False)
		self.assertEqual(doc.earned_salary_days, 40)
		self.assertEqual(doc.min_earned_days, 30)
		self.assertTrue(doc.eligible)
		self.assertEqual(doc.salary_days_paid, 30)
		self.assertEqual(doc.leave_salary_amount, 4000)
		self.assertEqual(doc.worked_days_pay, 1333.333)
		self.assertEqual(doc.total_payable, 5333.333)
		self.assertEqual([r.line_type for r in doc.pay_lines], ["Worked Days Salary", "Leave Salary"])

	def test_submit_spends_the_earned_days_in_the_ledger(self):
		emp = self.staff("Spender")
		self.settle(emp, self.leave(emp))
		self.assertEqual(get_salary_days_balance(emp), 10)

	def test_cancel_puts_them_back(self):
		emp = self.staff("Canceller")
		doc = self.settle(emp, self.leave(emp))
		doc.cancel()
		self.assertEqual(get_salary_days_balance(emp), 40)
		self.assertEqual(doc.status, "Cancelled")

	def test_below_the_barrier_the_settlement_is_refused_with_the_reason(self):
		emp = self.staff("Short", opening=20)
		la = self.leave(emp)
		with self.assertRaises(frappe.ValidationError) as caught:
			self.settle(emp, la)
		self.assertIn("earned salary days", str(caught.exception))
		self.assertEqual(get_salary_days_balance(emp), 20)  # nothing spent

	def test_only_hr_with_the_override_role_may_pay_below_the_barrier(self):
		emp = self.staff("Override", opening=20)
		la = self.leave(emp)
		with patch("frappe.get_roles", return_value=["HR Manager"]):
			self.assertRaises(frappe.ValidationError, self.settle, emp, la, pay_below_barrier=1, barrier_override_reason="x")
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			self.assertRaises(frappe.ValidationError, self.settle, emp, la, pay_below_barrier=1)  # no reason
			doc = self.settle(emp, la, pay_below_barrier=1, barrier_override_reason="Medical leave, approved by CEO")
		self.assertEqual(doc.salary_days_paid, 20)
		self.assertEqual(doc.salary_days_unpaid, 10)

	def test_a_second_settlement_releases_what_has_since_been_earned(self):
		emp = self.staff("Later", opening=20)
		la = self.leave(emp)
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			self.settle(emp, la, pay_below_barrier=1, barrier_override_reason="advance")
		frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Adjustment", period_end="2026-05-31", leave_days=0, salary_days=30
		).insert(ignore_permissions=True)
		second = self.settle(emp, la, submit=False)
		self.assertEqual(second.salary_days_due, 10)
		self.assertEqual(second.salary_days_paid, 10)
		self.assertEqual(second.worked_days_pay, 0)

	def test_a_country_not_on_the_ledger_is_refused(self):
		emp = self.staff("Legacy")
		la = self.leave(emp)
		self.set_country(leave_accrual_engine="")
		self.assertRaises(frappe.ValidationError, self.settle, emp, la)


class TestPayrollExclusion(SettlementTestBase):
	def test_worked_days_paid_here_so_payroll_skips_april_and_loses_may_leave_days(self):
		self.set_pays_worked_days(1)
		emp = self.staff("Skipped")
		self.settle(emp, self.leave(emp))
		# April: 1,333.333 worked + 20 leave days x 133.333 = 4,000 (the whole month); May: 10 days
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-04-10", 4000), ("2026-05-01", 1333.333)])

	def test_worked_days_left_to_payroll_when_the_policy_says_so(self):
		self.set_pays_worked_days(0)
		emp = self.staff("NotSkipped")
		self.settle(emp, self.leave(emp))
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-04-11", 2666.667), ("2026-05-01", 1333.333)])

	def test_a_later_settlement_books_nothing_more(self):
		emp = self.staff("Once", opening=20)
		la = self.leave(emp)
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			self.settle(emp, la, pay_below_barrier=1, barrier_override_reason="advance")
		first_run = len(self.booked)
		frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Adjustment", period_end="2026-05-31", leave_days=0, salary_days=30
		).insert(ignore_permissions=True)
		self.settle(emp, la)
		self.assertEqual(len(self.booked), first_run)


class TestReturnFromLeave(SettlementTestBase):
	def test_early_return_recovers_unused_days_and_frees_payroll(self):
		self.set_pays_worked_days(1)
		emp = self.staff("Early", opening=40)
		doc = self.settle(emp, self.leave(emp))
		self.booked.clear()
		result = record_rejoin(doc.name, "2026-05-01")
		# leave 11 Apr - 10 May, back 1 May: 10 unused days x 133.3333 = 1,333.333 recovered
		self.assertEqual(result["unused_days"], 10)
		self.assertEqual(result["recovery_amount"], 1333.333)
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-05-01", 1333.333)])
		self.assertEqual(get_salary_days_balance(emp), 20)  # 40 - 30 + 10 restored

	def test_correcting_the_date_starts_clean(self):
		emp = self.staff("Corrected", opening=40)
		doc = self.settle(emp, self.leave(emp))
		record_rejoin(doc.name, "2026-05-01")
		result = record_rejoin(doc.name, "2026-05-06")
		self.assertEqual(result["unused_days"], 5)
		self.assertEqual(get_salary_days_balance(emp), 15)  # 10 left + 5 restored, the first 10 withdrawn

	def test_late_return_inside_the_balance_is_covered_by_leave(self):
		emp = self.staff("LateCovered", opening=45)
		doc = self.settle(emp, self.leave(emp))
		self.booked.clear()
		result = record_rejoin(doc.name, "2026-05-15")  # 4 days over; 15 days of HRMS balance remain
		self.assertEqual((result["extra_days"], result["extension_days_covered"], result["extra_days_unpaid"]), (4, 4, 0))
		self.assertEqual(self.booked, [])

	def test_late_return_beyond_the_balance_is_unpaid(self):
		emp = self.staff("LateUnpaid", opening=34)
		doc = self.settle(emp, self.leave(emp))
		# 34 - 30 taken = 4 days left; back 8 days late: 4 covered, 4 unpaid = 4 x 133.333
		result = record_rejoin(doc.name, "2026-05-19")
		self.assertEqual((result["extra_days"], result["extension_days_covered"], result["extra_days_unpaid"]), (8, 4, 4))
		self.assertEqual(self.booked[-1]["amount"], 533.333)

	def test_rejoin_is_recorded_on_the_first_settlement_only(self):
		emp = self.staff("Wrong", opening=20)
		la = self.leave(emp)
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			self.settle(emp, la, pay_below_barrier=1, barrier_override_reason="advance")
		frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Adjustment", period_end="2026-05-31", leave_days=0, salary_days=30
		).insert(ignore_permissions=True)
		second = self.settle(emp, la)
		self.assertRaises(frappe.ValidationError, record_rejoin, second.name, "2026-05-11")


class TestHandOff(SettlementTestBase):
	def test_the_settlement_goes_to_a_payment_advice_for_finance(self):
		from hr_suite.hr_suite.payment_advice import raise_for_document

		emp = self.staff("Advised")
		doc = self.settle(emp, self.leave(emp))
		result = raise_for_document("Leave Salary Settlement", doc.name)
		self.assertTrue(result["created"])
		advice = frappe.get_doc(result["doctype"], result["advice"])
		total = flt(advice.get("total_amount") or advice.get("payment_amount"), 2)
		self.assertEqual(total, 5333.33)  # the advice carries the currency's own 2 decimals
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "payment_advice"), result["advice"])
		# asking again returns the same advice, never a second one
		self.assertFalse(raise_for_document("Leave Salary Settlement", doc.name)["created"])

	def test_the_advice_is_written_back_onto_the_settlement(self):
		from hr_suite.hr_suite.payment_advice import raise_for_document

		emp = self.staff("Linked")
		doc = self.settle(emp, self.leave(emp))
		raise_for_document("Leave Salary Settlement", doc.name)
		doc.reload()
		self.assertTrue(doc.payment_advice)

	def test_the_old_disbursement_is_refused_for_a_ledger_country(self):
		emp = self.staff("Old")
		la = self.leave(emp)
		disbursement = frappe.get_doc(
			doctype="Annual Leave Disbursement", employee=emp, company=COMPANY, leave_application=la,
			leave_type="Annual Leave", leave_from_date="2026-04-11", leave_to_date="2026-05-10", leave_days_to_pay=30,
		)
		self.assertRaises(frappe.ValidationError, disbursement.insert, ignore_permissions=True)
