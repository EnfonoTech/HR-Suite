"""Leave Salary Settlement: pricing, the barrier, the accrual, the payment, the payroll days and the return."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

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

		# the two accounts the settlement posts to, mapped for this company the way an administrator would
		cls.expense_account = frappe.db.get_value(
			"Account", {"company": COMPANY, "root_type": "Expense", "is_group": 0}, "name"
		)
		cls.payable_account = frappe.db.get_value(
			"Account", {"company": COMPANY, "account_type": "Payable", "is_group": 0}, "name"
		)
		cls.map_accounts(cls.expense_account, cls.payable_account)

	@classmethod
	def map_accounts(cls, expense, payable):
		settings = frappe.get_doc("Hr Suite Settings")
		settings.set("hr_account_mappings", [
			row for row in (settings.get("hr_account_mappings") or [])
			if row.company != COMPANY or row.purpose not in ("Leave Salary Expense", "Leave Salary Payable")
		])
		if expense:
			settings.append("hr_account_mappings", {"company": COMPANY, "purpose": "Leave Salary Expense", "account": expense})
		if payable:
			settings.append("hr_account_mappings", {"company": COMPANY, "purpose": "Leave Salary Payable", "account": payable})
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Hr Suite Settings", "Hr Suite Settings")

	def setUp(self):
		self.booked = []  # payroll deductions: only the early-return recovery and unpaid late days now
		counter = iter(range(1, 100))

		def fake_book(doc, component, currency, payroll_date, amount):
			name = "AS-FAKE-%s" % next(counter)
			self.booked.append({"name": name, "date": str(payroll_date), "amount": flt(amount, 3), "component": component})
			return name

		def fake_component(employee, company, expense_account, component=None, component_type="Deduction"):
			return (component or "Leave Salary Recovery"), "SAR"

		patches = [
			patch("hr_suite.hr_suite.leave_payroll.prepare_component", side_effect=fake_component),
			patch("hr_suite.hr_suite.leave_payroll.book_deduction", side_effect=fake_book),
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
		fields.setdefault("last_working_day", "2026-04-10")
		doc = frappe.get_doc(doctype="Leave Salary Settlement", employee=emp, leave_application=la, **fields)
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
		self.assertEqual(doc.worked_days_pay, 0)  # the days worked stay in normal payroll
		self.assertEqual(doc.total_payable, 4000)
		self.assertEqual([r.line_type for r in doc.pay_lines], ["Leave Salary"])

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


class TestAccrual(SettlementTestBase):
	"""Submit recognises the leave salary once: expense against the employee-tagged payable, no bank line."""

	def accrual(self, doc):
		doc.reload()
		return frappe.get_doc("Journal Entry", doc.accrual_journal_entry)

	def test_submit_posts_one_accrual_with_the_employee_on_the_payable(self):
		emp = self.staff("Accrued")
		doc = self.settle(emp, self.leave(emp, "2026-10-01", "2026-10-21"), last_working_day="2026-09-30")
		je = self.accrual(doc)
		self.assertEqual(je.docstatus, 1)
		rows = {r.account: r for r in je.accounts}
		self.assertEqual(set(rows), {self.expense_account, self.payable_account})  # nothing else, no bank or cash
		self.assertEqual(flt(rows[self.expense_account].debit_in_account_currency), 2800)  # 21 days x 133.333
		payable = rows[self.payable_account]
		self.assertEqual(flt(payable.credit_in_account_currency), 2800)
		self.assertEqual((payable.party_type, payable.party), ("Employee", emp))
		self.assertEqual(doc.payroll_stage, "Accrual Posted")

	def test_no_payroll_rows_are_created(self):
		emp = self.staff("NoRows")
		doc = self.settle(emp, self.leave(emp, "2026-10-01", "2026-10-21"), last_working_day="2026-09-30")
		self.assertEqual(frappe.db.count("Additional Salary", {"ref_doctype": "Leave Salary Settlement", "ref_docname": doc.name}), 0)
		self.assertEqual(self.booked, [])

	def test_only_the_leave_salary_is_paid_here_not_the_days_worked(self):
		emp = self.staff("LeaveOnly")
		doc = self.settle(emp, self.leave(emp))  # last working day the 10th, leave from the 11th: same month
		self.assertEqual(doc.worked_days_pay, 0)
		self.assertEqual(doc.pay_worked_days_in_settlement, 0)
		self.assertEqual(doc.total_payable, doc.leave_salary_amount)

	def test_the_accrual_is_not_posted_twice(self):
		emp = self.staff("Once")
		doc = self.settle(emp, self.leave(emp, "2026-10-01", "2026-10-21"), last_working_day="2026-09-30")
		first = doc.reload().accrual_journal_entry
		doc._post_accrual()
		self.assertEqual(doc.reload().accrual_journal_entry, first)
		self.assertEqual(frappe.db.count("Journal Entry", {"user_remark": ["like", "%{0}%".format(doc.name)]}), 1)

	def test_an_unmapped_company_is_told_what_to_map_and_nothing_is_posted(self):
		self.map_accounts(None, None)
		self.addCleanup(self.map_accounts, self.expense_account, self.payable_account)
		emp = self.staff("Unmapped")
		la = self.leave(emp, "2026-10-01", "2026-10-21")
		with self.assertRaises(frappe.ValidationError) as caught:
			self.settle(emp, la, last_working_day="2026-09-30")
		self.assertIn("Leave Salary Payable", str(caught.exception))
		# a refused submit rolls back in a real request; here only the missing posting matters
		self.assertFalse(frappe.db.get_value("Leave Salary Settlement", {"employee": emp}, "accrual_journal_entry"))

	def test_a_payable_that_cannot_carry_the_employee_is_refused(self):
		emp = self.staff("NoParty")
		la = self.leave(emp, "2026-10-01", "2026-10-21")
		real = frappe.get_cached_value

		def not_payable(doctype, name, fieldname=None, *args, **kwargs):
			if doctype == "Account" and name == self.payable_account and fieldname == "account_type":
				return ""
			return real(doctype, name, fieldname, *args, **kwargs)

		with patch("frappe.get_cached_value", side_effect=not_payable):
			self.assertRaises(frappe.ValidationError, self.settle, emp, la, last_working_day="2026-09-30")

	def test_cancelling_the_settlement_cancels_the_accrual(self):
		emp = self.staff("Reversed")
		doc = self.settle(emp, self.leave(emp, "2026-10-01", "2026-10-21"), last_working_day="2026-09-30")
		je = doc.reload().accrual_journal_entry
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)

	def test_a_leave_already_settled_in_full_cannot_be_settled_again(self):
		emp = self.staff("Twice", opening=60)
		la = self.leave(emp, "2026-10-01", "2026-10-21")
		self.settle(emp, la, last_working_day="2026-09-30")
		second = self.settle(emp, la, submit=False, last_working_day="2026-09-30")
		self.assertEqual(second.salary_days_due, 0)
		self.assertRaises(frappe.ValidationError, second.submit)

	def test_two_open_drafts_for_one_leave_are_refused(self):
		emp = self.staff("Drafts")
		la = self.leave(emp, "2026-10-01", "2026-10-21")
		self.settle(emp, la, submit=False, last_working_day="2026-09-30")
		self.assertRaises(frappe.ValidationError, self.settle, emp, la, submit=False, last_working_day="2026-09-30")

	def test_sick_leave_is_not_settled_as_annual_leave(self):
		emp = self.staff("Sick")
		la = self.leave(emp, "2026-10-01", "2026-10-05")
		frappe.db.set_value("Leave Application", la, "leave_type", "Sick Leave")  # an approved sick leave
		self.assertRaises(frappe.ValidationError, self.settle, emp, la, last_working_day="2026-09-30")

	def test_country_config_refuses_an_earning_as_the_recovery_component(self):
		cfg = frappe.get_doc("Country Config", "SA")
		original = cfg.leave_salary_recovery_component
		self.addCleanup(lambda: frappe.db.set_value("Country Config", "SA", "leave_salary_recovery_component", original))
		earning = frappe.get_doc(doctype="Salary Component", salary_component="TEST LSS Earn", salary_component_abbr="TLE", type="Earning").insert(ignore_permissions=True)
		cfg.leave_salary_recovery_component = earning.name
		self.assertRaises(frappe.ValidationError, cfg.save, ignore_permissions=True)


class TestPayrollDays(SettlementTestBase):
	"""Payroll leaves the settled leave days out of the payment days, and waits for the return."""

	def settled(self, name, start="2026-10-04", end="2026-10-15", lwd="2026-10-03"):
		emp = self.staff(name)
		return emp, self.settle(emp, self.leave(emp, start, end), last_working_day=lwd)

	def slip(self, emp, start="2026-10-01", end="2026-10-31"):
		slip = frappe.new_doc("Salary Slip")
		slip.employee, slip.start_date, slip.end_date = emp, start, end
		return slip

	def test_the_settled_leave_days_are_counted(self):
		from hr_suite.hr_suite.overrides.salary_slip import count_excluded_days, settled_leave_ranges

		emp, doc = self.settled("Counted")
		ranges = settled_leave_ranges(emp, "2026-10-01", "2026-10-31")
		self.assertEqual(count_excluded_days(ranges, "2026-10-01", "2026-10-31"), 12)  # 4 to 15 October inclusive
		self.assertEqual(count_excluded_days(ranges, "2026-10-01", "2026-10-31", holidays=["2026-10-09"]), 11)
		self.assertEqual(count_excluded_days(ranges, "2026-11-01", "2026-11-30"), 0)  # another month

	def test_a_settlement_without_an_accrual_is_the_old_kind_and_is_not_excluded(self):
		from hr_suite.hr_suite.overrides.salary_slip import settled_leave_ranges

		emp, doc = self.settled("Legacy")
		frappe.db.set_value("Leave Salary Settlement", doc.name, "accrual_journal_entry", None)
		self.assertEqual(settled_leave_ranges(emp, "2026-10-01", "2026-10-31"), [])

	def test_a_cancelled_settlement_no_longer_excludes_days(self):
		from hr_suite.hr_suite.overrides.salary_slip import settled_leave_ranges

		emp, doc = self.settled("Cancelled")
		doc.cancel()
		self.assertEqual(settled_leave_ranges(emp, "2026-10-01", "2026-10-31"), [])

	def test_the_salary_slip_pays_only_the_days_outside_the_leave(self):
		emp, doc = self.settled("SlipDays")
		slip = self.slip(emp)
		slip.get_working_days_details()
		self.assertEqual(slip.leave_without_pay, 0)  # annual leave is never leave without pay
		self.assertEqual(slip.payment_days, slip.total_working_days - 12)

	def test_a_real_salary_slip_pays_the_days_outside_the_leave_and_nothing_else(self):
		"""31-day October, 12 leave days settled in advance: 19 payment days, the component scales, no extra rows."""
		emp, doc = self.settled("FullSlip")
		record_rejoin(doc.name, "2026-10-16")  # the return is confirmed, so payroll may run

		component = frappe.get_doc(
			doctype="Salary Component", salary_component="TEST LSS Basic", salary_component_abbr="TLSB", type="Earning",
			depends_on_payment_days=1,
		).insert(ignore_permissions=True)
		structure = frappe.get_doc(
			doctype="Salary Structure", name="TEST LSS Structure", company=COMPANY, is_active="Yes", payroll_frequency="Monthly",
			earnings=[{"salary_component": component.name, "amount": 3100}],
		)
		structure.insert(ignore_permissions=True)
		structure.submit()
		frappe.get_doc(
			doctype="Salary Structure Assignment", employee=emp, salary_structure=structure.name, from_date="2020-01-01",
			company=COMPANY, base=3100,
		).insert(ignore_permissions=True).submit()

		slip = frappe.new_doc("Salary Slip")
		slip.employee, slip.company, slip.posting_date = emp, COMPANY, "2026-10-31"
		slip.start_date, slip.end_date = "2026-10-01", "2026-10-31"
		slip.get_emp_and_working_day_details()
		slip.insert(ignore_permissions=True)

		self.assertEqual(slip.payment_days, 19)  # 31 days less the 12 settled leave days
		self.assertEqual(slip.leave_without_pay, 0)
		self.assertEqual(flt(slip.gross_pay, 2), 1900)  # 3,100 x 19 / 31
		self.assertEqual([r.salary_component for r in slip.earnings], [component.name])  # no leave salary line
		self.assertEqual(len(slip.deductions), 0)  # and no exclusion or recovery line

	def test_an_employee_without_a_settlement_is_untouched(self):
		emp = self.staff("Plain")
		slip = self.slip(emp)
		slip.get_working_days_details()
		self.assertEqual(slip.payment_days, slip.total_working_days)

	def test_the_return_must_be_confirmed_before_payroll_for_the_days_after_the_leave(self):
		emp, doc = self.settled("Waiting")
		slip = self.slip(emp)
		with self.assertRaises(frappe.ValidationError) as caught:
			slip._hrs_require_confirmed_return()
		self.assertIn(doc.name, str(caught.exception))

		record_rejoin(doc.name, "2026-10-16")
		slip._hrs_require_confirmed_return()  # recorded: payroll may run

	def test_no_confirmation_is_needed_when_the_leave_covers_the_rest_of_the_period(self):
		emp, doc = self.settled("Covers", start="2026-10-20", end="2026-11-10", lwd="2026-10-19")
		self.slip(emp)._hrs_require_confirmed_return()  # October ends inside the leave: nothing after it to pay

	def test_attendance_after_the_leave_confirms_the_return(self):
		from hr_suite.hr_suite.overrides.salary_slip import return_confirmed

		emp, doc = self.settled("Attended")
		settlement = {"leave_to": getdate("2026-10-15"), "rejoin_date": None}
		self.assertFalse(return_confirmed(emp, settlement))
		with patch("frappe.db.exists", return_value="ATT-1"):
			self.assertTrue(return_confirmed(emp, settlement))


class TestPaymentEntry(SettlementTestBase):
	"""Finance pays the accrued payable with a Payment Entry made from the approved HR Payment Advice."""

	def advice_for(self, name):
		from hr_suite.hr_suite.payment_advice import raise_for_document

		emp = self.staff(name)
		doc = self.settle(emp, self.leave(emp, "2026-10-01", "2026-10-21"), last_working_day="2026-09-30")
		advice = frappe.get_doc("HR Payment Advice", raise_for_document("Leave Salary Settlement", doc.name)["advice"])
		advice.submit()
		return emp, doc, advice

	def test_mark_as_paid_by_hand_is_refused_for_leave_salary(self):
		from hr_suite.hr_suite.payment_advice import mark_paid

		emp, doc, advice = self.advice_for("NoManual")
		self.assertRaises(frappe.ValidationError, mark_paid, advice.name, payment_reference="x")

	def test_finance_gets_a_draft_payment_entry_for_the_employee_against_the_accrual(self):
		from hr_suite.hr_suite.payment_advice import make_payment_entry

		emp, doc, advice = self.advice_for("DraftPE")
		result = make_payment_entry(advice.name)
		entry = frappe.get_doc("Payment Entry", result["payment_entry"])
		self.assertEqual(entry.docstatus, 0)  # Finance chooses the bank and submits
		self.assertEqual((entry.party_type, entry.party), ("Employee", emp))
		self.assertEqual(entry.hr_payment_advice, advice.name)
		self.assertEqual(flt(entry.paid_amount), 2800)
		self.assertEqual([(r.reference_doctype, r.reference_name) for r in entry.references], [("Journal Entry", doc.reload().accrual_journal_entry)])
		self.assertEqual(make_payment_entry(advice.name)["payment_entry"], entry.name)  # asking again returns the same draft

	def pay(self, advice, amount):
		"""Stand in for a submitted Payment Entry of `amount` made from the advice."""
		entry = frappe.get_doc({
			"doctype": "Payment Entry", "payment_type": "Pay", "company": COMPANY, "party_type": "Employee",
			"party": advice.employee, "paid_amount": amount, "received_amount": amount, "hr_payment_advice": advice.name,
			"posting_date": "2026-10-20",
		})
		entry.db_insert()
		frappe.db.set_value("Payment Entry", entry.name, "docstatus", 1)
		return entry

	def test_the_advice_is_partly_paid_then_paid_and_the_settlement_follows(self):
		from hr_suite.hr_suite.payment_advice import sync_hr_advice_payment

		emp, doc, advice = self.advice_for("Partly")
		first = self.pay(advice, 1000)
		sync_hr_advice_payment(advice.name)
		self.assertEqual(frappe.db.get_value("HR Payment Advice", advice.name, ["status", "amount_paid"]), ("Partially Paid", 1000))
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "payroll_stage"), "Partially Paid")
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "status"), "Approved")

		second = self.pay(advice, 1800)
		sync_hr_advice_payment(advice.name)
		self.assertEqual(frappe.db.get_value("HR Payment Advice", advice.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "payroll_stage"), "Payment Completed")

		frappe.db.set_value("Payment Entry", second.name, "docstatus", 2)  # the last payment is cancelled
		sync_hr_advice_payment(advice.name)
		self.assertEqual(frappe.db.get_value("HR Payment Advice", advice.name, ["status", "amount_paid"]), ("Partially Paid", 1000))
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "status"), "Approved")

		frappe.db.set_value("Payment Entry", first.name, "docstatus", 2)
		sync_hr_advice_payment(advice.name)
		self.assertIn(frappe.db.get_value("HR Payment Advice", advice.name, "status"), ("Approved", "Sent to Finance"))
		self.assertEqual(frappe.db.get_value("HR Payment Advice", advice.name, "amount_paid"), 0)

	def test_an_unpaid_advice_is_not_treated_as_paid(self):
		from hr_suite.hr_suite.payment_advice import sync_hr_advice_payment

		emp, doc, advice = self.advice_for("Unpaid")
		sync_hr_advice_payment(advice.name)
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "status"), "Approved")
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "payroll_stage"), "Payment Advice Created")


class TestReturnFromLeave(SettlementTestBase):
	def test_early_return_before_payment_books_nothing_and_restores_the_days(self):
		emp = self.staff("Early", opening=40)
		doc = self.settle(emp, self.leave(emp))
		result = record_rejoin(doc.name, "2026-05-01")
		# leave 11 Apr - 10 May, back 1 May: 10 unused days. Nothing has been paid, so nothing is taken back.
		self.assertEqual(result["unused_days"], 10)
		self.assertEqual(self.booked, [])
		self.assertEqual(get_salary_days_balance(emp), 20)  # 40 - 30 + 10 restored

	def test_early_return_after_payment_takes_the_unused_days_back_at_payroll(self):
		emp = self.staff("EarlyPaid", opening=40)
		doc = self.settle(emp, self.leave(emp))
		frappe.db.set_value("Leave Salary Settlement", doc.name, "status", "Paid")
		result = record_rejoin(doc.name, "2026-05-01")
		self.assertEqual(result["recovery_amount"], 1333.333)  # 10 unused days x 133.3333
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-05-01", 1333.333)])

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
		self.assertEqual(total, 4000)  # the leave salary only: the days worked stay in payroll
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

	def test_the_form_shows_the_advice_raised_for_the_settlement(self):
		from hr_suite.hr_suite.payment_advice import get_advice_state, raise_for_document

		emp = self.staff("Shown")
		doc = self.settle(emp, self.leave(emp))
		before = get_advice_state("Leave Salary Settlement", doc.name)
		self.assertIsNone(before["advice"])  # nothing raised yet: the form offers Create
		self.assertIn(before["target"], ("HR Payment Advice", "Payment Advice"))

		result = raise_for_document("Leave Salary Settlement", doc.name)
		state = get_advice_state("Leave Salary Settlement", doc.name)
		self.assertEqual((state["advice"], state["doctype"]), (result["advice"], result["doctype"]))
		self.assertTrue(state["status"])

	def test_a_cancelled_advice_is_not_shown_and_create_is_offered_again(self):
		from hr_suite.hr_suite.payment_advice import get_advice_state, raise_for_document

		emp = self.staff("Withdrawn")
		doc = self.settle(emp, self.leave(emp))
		first = raise_for_document("Leave Salary Settlement", doc.name)
		frappe.db.set_value(first["doctype"], first["advice"], "docstatus", 2)
		self.assertIsNone(get_advice_state("Leave Salary Settlement", doc.name)["advice"])
		self.assertTrue(raise_for_document("Leave Salary Settlement", doc.name)["created"])

	def test_the_settlement_raises_the_hr_payment_advice_even_where_finance_advice_exists(self):
		"""Leave salary is approved by HR first (level 1 / 2), so it never goes straight to sf_trading's advice."""
		from hr_suite.hr_suite import payment_advice as pa

		emp = self.staff("HrFirst")
		doc = self.settle(emp, self.leave(emp))
		with patch.object(pa, "finance_advice_available", return_value=True), patch.object(
			pa, "get_finance_advice_for", return_value=None
		), patch.object(pa, "create_finance_advice_for", side_effect=AssertionError("finance advice raised")):
			self.assertEqual(pa.get_advice_state("Leave Salary Settlement", doc.name)["target"], "HR Payment Advice")
			result = pa.raise_for_document("Leave Salary Settlement", doc.name)
		self.assertEqual((result["doctype"], result["created"]), ("HR Payment Advice", True))
		self.assertEqual(frappe.db.get_value("Leave Salary Settlement", doc.name, "payment_advice_type"), "HR Payment Advice")

	def test_a_finance_advice_raised_earlier_is_not_doubled_by_an_hr_advice(self):
		from hr_suite.hr_suite import payment_advice as pa

		emp = self.staff("NoDouble")
		doc = self.settle(emp, self.leave(emp))
		with patch.object(pa, "finance_advice_available", return_value=True), patch.object(
			pa, "get_finance_advice_for", return_value="PA-OLD"
		):
			result = pa.raise_for_document("Leave Salary Settlement", doc.name)
		self.assertEqual((result["advice"], result["doctype"], result["created"]), ("PA-OLD", "Payment Advice", False))
		self.assertFalse(frappe.db.exists("HR Payment Advice", {"source_name": doc.name}))

	def test_hr_can_raise_a_finance_advice_without_create_rights_on_it(self):
		"""sf_trading's Payment Advice gives create to accounts roles only; HR raises it from its own document."""
		from types import SimpleNamespace

		from hr_suite.hr_suite import payment_advice as pa

		emp = self.staff("HrRaises")
		doc = self.settle(emp, self.leave(emp))
		asked = []

		def has_permission(doctype, ptype="read", doc=None, throw=False, **kwargs):
			asked.append((doctype, ptype))
			return True

		spec = {**pa.SOURCE_DOCUMENTS["Leave Salary Settlement"], "hr_advice": False}
		with patch.dict(pa.SOURCE_DOCUMENTS, {"Leave Salary Settlement": spec}), patch.object(
			pa, "finance_advice_available", return_value=True
		), patch.object(pa, "get_finance_advice_for", return_value=None), patch.object(
			pa, "create_finance_advice_for", return_value=SimpleNamespace(name="PA-X")
		), patch.object(pa, "_write_back_advice_link"), patch.object(
			pa, "assert_doctype_permissions", side_effect=AssertionError("create on the finance advice")
		), patch("frappe.has_permission", side_effect=has_permission):
			result = pa.raise_for_document("Leave Salary Settlement", doc.name)

		self.assertEqual((result["advice"], result["doctype"], result["created"]), ("PA-X", "Payment Advice", True))
		self.assertIn(("Leave Salary Settlement", "write"), asked)
		self.assertNotIn(("Payment Advice", "create"), asked)

	def test_the_old_disbursement_is_refused_for_a_ledger_country(self):
		emp = self.staff("Old")
		la = self.leave(emp)
		disbursement = frappe.get_doc(
			doctype="Annual Leave Disbursement", employee=emp, company=COMPANY, leave_application=la,
			leave_type="Annual Leave", leave_from_date="2026-04-11", leave_to_date="2026-05-10", leave_days_to_pay=30,
		)
		self.assertRaises(frappe.ValidationError, disbursement.insert, ignore_permissions=True)
