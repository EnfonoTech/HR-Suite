"""The consultant's UAT bug list for the GCC module, one acceptance test per case in the spec.

Expected figures are worked by hand in the comments from the spec (SFT HR Suite Bug Fix
Specification, 13 Oct 2026), never read back from the code under test.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate

from hr_suite.hr_suite.leave_accrual import accrue_employee, get_salary_days_balance
from hr_suite.hr_suite.test_gratuity import run as gratuity
from hr_suite.hr_suite.test_leave_accrual_ledger import COMPANY, LedgerTestBase, set_leave_workflow
from hr_suite.hr_suite.test_leave_salary_settlement import SettlementTestBase
from hr_suite.hr_suite.test_sick_leave_tiers import SickTestBase


def make_holiday_list(name, year="2026"):
	if not frappe.db.exists("Holiday List", name):
		frappe.get_doc(
			doctype="Holiday List", holiday_list_name=name, from_date="%s-01-01" % year, to_date="%s-12-31" % year
		).insert(ignore_permissions=True)
	frappe.db.set_value("Company", COMPANY, "default_holiday_list", name)


# ── 1. gratuity ───────────────────────────────────────────────────────────────


class TestGratuityAcceptance(FrappeTestCase):
	def test_ksa_terminated_after_seven_years(self):
		# wage 6,000, 200 a day: (5 x 15 + 2 x 30) x 200
		self.assertEqual(gratuity("SA", 7, 6000).net_entitlement, 27000)

	def test_ksa_resigning_at_three_years_gets_a_third(self):
		# 3 x 15 x 200 x 1/3
		self.assertEqual(gratuity("SA", 3, 6000, "Resignation").net_entitlement, 3000)

	def test_ksa_resigning_under_two_years_gets_nothing(self):
		self.assertEqual(gratuity("SA", 1.5, 6000, "Resignation").net_entitlement, 0)

	def test_ksa_resigning_after_twelve_years_gets_the_lot(self):
		# 5 x 15 + 7 x 30 = 285 days x 200
		self.assertEqual(gratuity("SA", 12, 6000, "Resignation").net_entitlement, 57000)

	def test_bahrain_terminated(self):
		# 15 days a year for 3 years, 30 after: 5 years = (3 x 15 + 2 x 30) x 200
		# (service before March 2024: the employer scheme is replaced by SIO contributions after that)
		self.assertEqual(gratuity("BH", 5, 6000, joined="2015-01-01").net_entitlement, 21000)
		self.assertEqual(gratuity("BH", 12, 6000, joined="2005-01-01").net_entitlement, 63000)  # (45 + 9 x 30) days

	def test_the_legacy_gratuity_days_no_longer_say_21_for_saudi(self):
		self.assertEqual(frappe.db.get_value("Country Config", "SA", "days_per_year_below_threshold"), 15)


# ── 3, 5, 10. accrued balance, ledger, pro-rata ───────────────────────────────


class LeaveTestBase(LedgerTestBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_holiday_list("HRS SFT HL")

	def take(self, emp, start, end):
		la = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="Annual Leave", from_date=start, to_date=end,
			status="Approved", company=COMPANY,
		)
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def start_ledger(self, start):
		cfg = frappe.get_doc("Country Config", "SA")
		original = cfg.leave_ledger_start_date
		cfg.leave_ledger_start_date = start
		cfg.save(ignore_permissions=True)

		def restore():
			again = frappe.get_doc("Country Config", "SA")
			again.leave_ledger_start_date = original
			again.save(ignore_permissions=True)

		self.addCleanup(restore)


class TestAccruedBalance(LeaveTestBase):
	def test_four_months_in_the_balance_is_seven_not_twenty_one(self):
		from hr_suite.hr_suite.report.leave_accrual_ledger_report.leave_accrual_ledger_report import execute as ledger_report
		from hr_suite.hr_suite.report.leave_balance_report.leave_balance_report import execute as balance_report

		emp = self.employee("Four", "SA", "2026-01-01")
		accrue_employee(emp, "2026-04-30")

		rows = frappe.get_all("Leave Accrual Ledger", filters={"employee": emp, "source": "Accrual"}, pluck="leave_days")
		self.assertEqual(rows, [1.75] * 4)
		self.assertEqual(self.balance(emp, "2026-04-30"), 7.0)  # 4 x 1.75

		_c, report = balance_report({"employee": emp, "year": 2026})
		self.assertEqual(report[0]["leave_balance"], 7.0)
		self.assertEqual(report[0]["entitlement"], 21)  # the year's entitlement is shown, not paid out

		self.take(emp, "2026-05-04", "2026-05-06")  # 3 days
		self.assertEqual(self.balance(emp, "2026-05-06"), 4.0)
		_c, report = balance_report({"employee": emp, "year": 2026})
		self.assertEqual(report[0]["leave_balance"], 4.0)

		# the ledger report agrees: four accruals, then the leave taken, running balance 4.00
		_c, ledger = ledger_report({"employee": emp})
		self.assertEqual([r["source"] for r in ledger], ["Accrual"] * 4 + ["Leave Taken"])
		self.assertEqual([r["leave_balance"] for r in ledger], [1.75, 3.5, 5.25, 7.0, 4.0])
		taken = ledger[-1]
		self.assertEqual((taken["days_in"], taken["days_out"]), (0, 3))
		self.assertEqual(taken["reference_doctype"], "Leave Application")


class TestProRata(LeaveTestBase):
	def test_one_point_four_five_years_earns_thirty_point_four_five_days(self):
		from hr_suite.hr_suite.report.leave_balance_report.leave_balance_report import execute as balance_report

		self.start_ledger("2025-01-01")
		emp = self.employee("Prorata", "SA", "2025-01-01")
		accrue_employee(emp, "2026-05-31")  # 12 months of year one and 5 completed months of year two

		rows = frappe.get_all("Leave Accrual Ledger", filters={"employee": emp, "source": "Accrual"}, pluck="leave_days")
		self.assertEqual(len(rows), 17)
		self.assertEqual(flt(sum(rows), 2), 29.75)  # 17 x 1.75

		# on 12 June the part-month so far is 12/30 x 1.75 = 0.70, which makes 30.45 = 21 x 1.45
		with patch(
			"hr_suite.hr_suite.report.leave_balance_report.leave_balance_report.today", return_value="2026-06-12"
		):
			_c, report = balance_report({"employee": emp, "year": 2026})
		self.assertEqual(flt(report[0]["accrued_to_date"] + report[0]["accruing_now"], 2), 30.45)

	def test_a_new_joiner_is_prorated_from_the_joining_date(self):
		emp = self.employee("Joiner", "SA", "2026-03-09")
		accrue_employee(emp, "2026-03-31")
		# 23 of 30 days x 1.75
		self.assertEqual(frappe.get_all("Leave Accrual Ledger", filters={"employee": emp}, pluck="leave_days"), [1.34])

	def test_the_rate_steps_up_when_service_crosses_five_years(self):
		self.start_ledger("2025-11-01")
		emp = self.employee("Crossing", "SA", "2021-01-01")
		accrue_employee(emp, "2026-02-28")
		rows = frappe.get_all(
			"Leave Accrual Ledger", filters={"employee": emp, "source": "Accrual"}, fields=["period_start", "leave_days"],
			order_by="period_start",
		)
		# Nov 2025 - Dec 2025 are in the fifth year (1.75); from Jan 2026 five years are complete (2.5)
		self.assertEqual([r.leave_days for r in rows], [1.75, 1.75, 2.5, 2.5])


# ── 4, 8, 11. leave salary ────────────────────────────────────────────────────


class TestLeaveSalaryAcceptance(SettlementTestBase):
	def setUp(self):
		super().setUp()
		self.set_country(leave_salary_min_earned_days=0)  # the spec's default: service is the only barrier
		make_holiday_list("HRS SFT HL")

	def test_eleven_months_service_is_refused_with_the_reason(self):
		emp = self.staff("Eleven", opening=19.25, ctc=6000, joined="2025-05-11")  # 334 days, 11 months
		la = self.leave(emp)
		with self.assertRaises(frappe.ValidationError) as caught:
			self.settle(emp, la)
		self.assertIn("service 334 of the 365 days needed", str(caught.exception))
		self.assertEqual(get_salary_days_balance(emp), 19.25)

	def test_twelve_months_is_allowed_and_pays_all_the_accrued_days(self):
		emp = self.staff("Twelve", opening=21, ctc=6000, joined="2025-04-10")  # 365 days
		doc = self.settle(emp, self.leave(emp, start="2026-04-11", end="2026-05-01"))  # 21 days
		self.assertEqual(doc.salary_days_paid, 21)
		self.assertEqual(doc.leave_salary_amount, 4200)  # 6,000 / 30 x 21
		self.assertEqual(get_salary_days_balance(emp), 0)  # the days leave the ledger

	def test_a_final_settlement_pays_the_accrued_days_before_twelve_months(self):
		emp = self.staff("Exit", opening=10.5, ctc=6000, joined="2026-01-01")  # six months in
		doc = frappe.get_doc(
			doctype="Leave Salary Settlement", settlement_type="Final Settlement", employee=emp,
			last_working_day="2026-06-30",
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.salary_days_paid, 10.5)
		self.assertEqual(doc.leave_salary_amount, 2100)  # 6,000 / 30 x 10.5
		self.assertEqual(doc.worked_days_pay, 0)  # worked days belong to the Salary Settlement
		doc.submit()
		self.assertEqual(get_salary_days_balance(emp), 0)
		doc.cancel()
		self.assertEqual(get_salary_days_balance(emp), 10.5)

	def test_the_exit_rule_can_be_switched_off_per_country(self):
		self.set_country(leave_salary_pay_on_exit=0)
		emp = self.staff("NoExit", opening=10.5, ctc=6000, joined="2026-01-01")
		doc = frappe.get_doc(
			doctype="Leave Salary Settlement", settlement_type="Final Settlement", employee=emp,
			last_working_day="2026-06-30",
		)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_leave_before_the_minimum_service_can_be_blocked(self):
		self.set_country(annual_leave_before_min_service="Block")
		emp = self.staff("Early", opening=5, ctc=6000, joined="2026-03-01")
		with self.assertRaises(frappe.ValidationError) as caught:
			self.leave(emp, start="2026-04-13", end="2026-04-15")
		self.assertIn("service", str(caught.exception))

	def test_leave_before_the_minimum_service_can_be_made_unpaid(self):
		self.set_country(annual_leave_before_min_service="Unpaid")
		emp = self.staff("Unpaid", opening=5, ctc=6000, joined="2026-03-01")
		with patch("hr_suite.hr_suite.leave_application_rules.payroll.ensure_deduction_component", return_value="X"), patch(
			"hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement.resolve_leave_salary_accounts",
			return_value=("", ""),
		):
			la = self.leave(emp, start="2026-04-13", end="2026-04-15")  # 3 days at 200 a day
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-04-13", 600)])
		self.assertTrue(frappe.db.get_value("Leave Application", la, "unpaid_deduction_rows"))

	def test_allow_is_the_default_and_books_nothing(self):
		emp = self.staff("Allowed", opening=5, ctc=6000, joined="2026-03-01")
		self.leave(emp, start="2026-04-13", end="2026-04-15")
		self.assertEqual(self.booked, [])


# ── 2. Can Be Taken From Leave ────────────────────────────────────────────────


class TestCanBeTakenFrom(LeaveTestBase):
	def test_the_field_is_on_the_leave_policy_row(self):
		meta = frappe.get_meta("Leave Policy Detail")
		field = meta.get_field("can_be_taken_from_leave")
		self.assertEqual((field.fieldtype, field.options, field.hidden, field.in_list_view), ("Link", "Leave Type", 0, 1))

	def test_leave_is_deducted_from_the_linked_leave_type(self):
		if not frappe.db.exists("Leave Type", "SFT Emergency"):
			frappe.get_doc(doctype="Leave Type", leave_type_name="SFT Emergency", max_leaves_allowed=5).insert(
				ignore_permissions=True
			)
		policy = frappe.get_doc(
			doctype="Leave Policy", title="SFT Emergency Policy",
			leave_policy_details=[
				{"leave_type": "SFT Emergency", "annual_allocation": 5, "can_be_taken_from_leave": "Annual Leave"}
			],
		)
		policy.insert(ignore_permissions=True)
		policy.submit()
		self.assertEqual(frappe.db.get_value("Leave Type", "SFT Emergency", "allow_negative"), 1)

		emp = self.employee("Drawer", "SA", "2026-01-01")
		accrue_employee(emp, "2026-04-30")  # 7 days of annual leave
		frappe.get_doc(
			doctype="Leave Policy Assignment", employee=emp, leave_policy=policy.name,
			effective_from="2026-01-01", effective_to="2026-12-31", assignment_based_on="",
		).insert(ignore_permissions=True).submit()

		from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

		emergency_before = flt(get_leave_balance_on(emp, "SFT Emergency", "2026-05-06"))
		la = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="SFT Emergency", from_date="2026-05-04",
			to_date="2026-05-05", status="Approved", company=COMPANY,
		)
		la.insert(ignore_permissions=True)
		la.submit()

		self.assertEqual(self.balance(emp, "2026-05-06"), 5.0)  # 7 - 2, taken from Annual Leave
		self.assertEqual(flt(get_leave_balance_on(emp, "SFT Emergency", "2026-05-06")), emergency_before)

		# more than Annual Leave holds is refused, whatever Emergency Leave itself allows
		too_long = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="SFT Emergency", from_date="2026-05-11",
			to_date="2026-05-20", status="Approved", company=COMPANY,
		)
		with patch("frappe.get_roles", return_value=["HR Manager"]):
			self.assertRaises(frappe.ValidationError, too_long.insert, ignore_permissions=True)

		la.cancel()
		self.assertEqual(self.balance(emp, "2026-05-06"), 7.0)  # the days come back

	def test_a_type_cannot_draw_on_itself(self):
		policy = frappe.get_doc(
			doctype="Leave Policy", title="SFT Self Draw",
			leave_policy_details=[{"leave_type": "Annual Leave", "annual_allocation": 5, "can_be_taken_from_leave": "Annual Leave"}],
		)
		self.assertRaises(frappe.ValidationError, policy.insert, ignore_permissions=True)


# ── 6. approval workflow ──────────────────────────────────────────────────────


class TestApprovalWorkflow(LeaveTestBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		set_leave_workflow(1)

	@staticmethod
	def user(email, roles):
		if not frappe.db.exists("User", email):
			frappe.get_doc(doctype="User", email=email, first_name=email.split("@")[0], send_welcome_email=0).insert(
				ignore_permissions=True
			)
		frappe.get_doc("User", email).add_roles(*roles)
		return email

	def setUp(self):
		self.approver = self.user("sft.approver@example.com", ["Leave Approver"])
		self.staff_user = self.user("sft.staff@example.com", ["Employee"])
		self.emp = self.employee("Workflow", "SA", "2026-01-01")
		frappe.db.set_value("Employee", self.emp, {"user_id": self.staff_user, "leave_approver": self.approver})
		accrue_employee(self.emp, "2026-04-30")
		self.addCleanup(frappe.set_user, "Administrator")

	def apply(self, start, end):
		frappe.set_user(self.staff_user)
		la = frappe.get_doc(
			doctype="Leave Application", employee=self.emp, leave_type="Annual Leave", from_date=start, to_date=end,
			company=COMPANY, leave_approver=self.approver,
		)
		la.insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		return la.name

	def actions(self, name, user):
		from frappe.model.workflow import get_transitions

		frappe.set_user(user)
		try:
			return sorted({t.action for t in get_transitions(frappe.get_doc("Leave Application", name))})
		finally:
			frappe.set_user("Administrator")

	def test_the_approver_sees_approve_and_reject(self):
		name = self.apply("2026-05-04", "2026-05-05")
		self.assertEqual(frappe.db.get_value("Leave Application", name, "status"), "Open")
		self.assertEqual(self.actions(name, self.approver), ["Approve", "Reject"])

	def test_the_employee_cannot_approve_their_own_leave_even_as_hr_manager(self):
		name = self.apply("2026-05-04", "2026-05-05")
		self.assertEqual(self.actions(name, self.staff_user), [])
		frappe.get_doc("User", self.staff_user).add_roles("HR Manager", "Leave Approver")
		self.assertEqual(self.actions(name, self.staff_user), [])

	def test_approve_submits_and_takes_the_days(self):
		from frappe.model.workflow import apply_workflow

		name = self.apply("2026-05-04", "2026-05-05")
		frappe.set_user(self.approver)
		apply_workflow(frappe.get_doc("Leave Application", name), "Approve")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Leave Application", name, ["status", "docstatus"]), ("Approved", 1))
		self.assertEqual(self.balance(self.emp, "2026-05-06"), 5.0)  # 7 - 2

	def test_reject_leaves_the_balance_alone(self):
		from frappe.model.workflow import apply_workflow

		name = self.apply("2026-05-04", "2026-05-05")
		frappe.set_user(self.approver)
		apply_workflow(frappe.get_doc("Leave Application", name), "Reject")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Leave Application", name, ["status", "docstatus"]), ("Rejected", 1))
		self.assertEqual(self.balance(self.emp, "2026-05-06"), 7.0)

	def test_another_user_who_is_not_the_named_approver_gets_no_buttons(self):
		other = self.user("sft.other@example.com", ["Leave Approver"])
		name = self.apply("2026-05-04", "2026-05-05")
		self.assertEqual(self.actions(name, other), [])

	def test_hr_who_created_the_leave_for_the_employee_can_approve_it(self):
		# the UAT testers created leave for the employee and approved it as the same user
		from frappe.model.workflow import apply_workflow

		hr = self.user("sft.hr@example.com", ["HR Manager", "Leave Approver"])
		frappe.db.set_value("Employee", self.emp, "leave_approver", hr)
		frappe.set_user(hr)
		la = frappe.get_doc(
			doctype="Leave Application", employee=self.emp, leave_type="Annual Leave", from_date="2026-05-04",
			to_date="2026-05-05", company=COMPANY, leave_approver=hr,
		)
		la.insert(ignore_permissions=True)
		self.assertEqual(self.actions(la.name, hr), ["Approve", "Reject"])
		apply_workflow(frappe.get_doc("Leave Application", la.name), "Approve")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Leave Application", la.name, ["status", "docstatus"]), ("Approved", 1))

	def test_status_cannot_be_set_to_approved_by_hand(self):
		name = self.apply("2026-05-04", "2026-05-05")
		la = frappe.get_doc("Leave Application", name)
		la.status = "Approved"
		with self.assertRaises(frappe.ValidationError) as caught:
			la.save(ignore_permissions=True)
		self.assertIn("Approve or Reject button", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Leave Application", name, "status"), "Open")

	def test_the_patch_reopens_leaves_stuck_before_submit(self):
		from hr_suite.patches.reopen_leave_applications_stuck_before_submit import execute

		stuck = self.apply("2026-05-04", "2026-05-05")
		frappe.db.set_value("Leave Application", stuck, "status", "Approved")  # as the testers left it
		execute()
		self.assertEqual(frappe.db.get_value("Leave Application", stuck, ["status", "docstatus"]), ("Open", 0))

	def test_the_doctor_names_what_is_wrong(self):
		from hr_suite.hr_suite.leave_workflow import diagnose

		name = self.apply("2026-05-04", "2026-05-05")
		findings = diagnose(name, self.approver)
		self.assertTrue(any("Approve (Leave Approver): available" in f for f in findings), findings)
		findings = diagnose(name, self.staff_user)
		self.assertTrue(any("does not hold the role" in f for f in findings), findings)


# ── 7. currency ───────────────────────────────────────────────────────────────


class TestCurrency(FrappeTestCase):
	def test_a_structure_with_no_currency_takes_the_companys(self):
		from hr_suite.hr_suite.salary_currency import default_from_company

		doc = frappe._dict(company=COMPANY, currency=None)
		default_from_company(doc)
		self.assertEqual(doc.currency, frappe.db.get_value("Company", COMPANY, "default_currency"))
		self.assertEqual(doc.currency, "SAR")

	def test_an_explicit_currency_is_kept_and_warned_about(self):
		from hr_suite.hr_suite.salary_currency import default_from_company, warn_if_not_company_currency

		doc = frappe._dict(company=COMPANY, currency="BHD", name="SS-X")
		default_from_company(doc)
		self.assertEqual(doc.currency, "BHD")
		frappe.clear_messages()
		warn_if_not_company_currency(doc)
		self.assertTrue(any("BHD" in m for m in frappe.get_message_log() for m in [str(m)]))

	def test_the_form_script_takes_the_company_currency(self):
		path = frappe.get_app_path("hr_suite", "public", "js", "salary_structure.js")
		with open(path) as f:
			source = f.read()
		self.assertIn("default_currency", source)
		self.assertNotIn("BHD", source)
		self.assertEqual(frappe.get_hooks("doctype_js")["Salary Structure"][-1], "public/js/salary_structure.js")


# ── 9. sick leave ─────────────────────────────────────────────────────────────


class TestSickAcceptance(SickTestBase):
	def split(self, la):
		name = la if isinstance(la, str) else la.name
		return [
			(r.tier_label, flt(r.days, 2))
			for r in frappe.get_all("Leave Application Sick Tier", filters={"parent": name}, fields=["tier_label", "days"], order_by="idx")
		]

	def test_per_day_tiers_in_date_order_sl_0008_and_sl_0010(self):
		emp = self.staff("Tiers")
		self.sick(emp, "2026-08-03", "2026-08-22")  # 20 days: the earlier leave the tester had
		sl_0010 = self.sick(emp, "2026-11-12", "2026-11-21")  # 10 days, submitted first
		self.assertEqual(self.split(sl_0010), [("Full pay", 10)])  # 20 before it: days 21-30

		sl_0008 = self.sick(emp, "2026-09-15", "2026-10-24")  # 40 days dated before it: days 21-60
		self.assertEqual(self.split(sl_0008), [("Full pay", 10), ("75% pay", 30)])
		self.assertEqual(frappe.db.get_value("Leave Application", sl_0008.name, "sick_unpaid_equivalent"), 7.5)  # 30 x 25%
		# SL-0010 now follows 60 days, so all 10 of its days are at 75%
		self.assertEqual(self.split(sl_0010), [("75% pay", 10)])
		self.assertEqual(frappe.db.get_value("Leave Application", sl_0010.name, "sick_unpaid_equivalent"), 2.5)

		# 100 a day: 30 x 25% x 100 = 750 on 0008 and 10 x 25% x 100 = 250 on 0010
		self.assertEqual(sum(b["amount"] for b in self.booked if b["for"] == sl_0008.name), 750)
		self.assertEqual(sum(b["amount"] for b in self.booked if b["for"] == sl_0010.name), 250)

	def test_a_closed_month_gets_an_adjustment_not_an_edit(self):
		booked = []

		def fake_adjust(doc, component, currency, payroll_date, amount, check_closed=True):
			booked.append((doc.name, component, str(payroll_date), flt(amount, 3), check_closed))
			return "AS-ADJ-%s" % len(booked)

		def closed_november(employee, on_date):
			return "SLIP-NOV" if getdate(on_date).month == 11 else None

		def component_for(employee, company, expense_account, component=None, component_type="Deduction"):
			return component, "SAR"

		emp = self.staff("Closed")
		self.sick(emp, "2026-08-03", "2026-08-22")
		sl_0010 = self.sick(emp, "2026-11-12", "2026-11-21")  # full pay, nothing booked

		with patch("hr_suite.hr_suite.leave_payroll.slip_covering", side_effect=closed_november), patch(
			"hr_suite.hr_suite.leave_payroll.next_open_date", return_value=getdate("2026-12-01")
		), patch("hr_suite.hr_suite.leave_payroll.book_additional_salary", side_effect=fake_adjust), patch(
			"hr_suite.hr_suite.leave_payroll.prepare_component", side_effect=component_for
		), patch("hr_suite.hr_suite.sick_leave_tiers._adjustment_component", return_value="Sick Leave Adjustment"):
			earlier = self.sick(emp, "2026-09-15", "2026-10-24")  # pushes 0010 to 75%
			self.assertEqual(booked, [(sl_0010.name, "Sick Leave Deduction", "2026-12-01", 250, False)])
			self.assertFalse([b for b in self.booked if b["for"] == sl_0010.name])  # November itself untouched

			earlier.cancel()  # 0010 is back to full pay: November was over-deducted, so it is given back
			self.assertEqual(booked[-1], (sl_0010.name, "Sick Leave Adjustment", "2026-12-01", 250, False))
		self.assertEqual(self.split(frappe.get_doc("Leave Application", sl_0010.name)), [("Full pay", 10)])

	def test_window_start_by_mode(self):
		from hr_suite.hr_suite.sick_leave_tiers import window_start

		policy = frappe._dict(date_of_joining="2023-03-15")
		for mode, on_date, expected in (
			("Calendar Year", "2026-10-13", "2026-01-01"),
			("Rolling 12 Months", "2026-10-13", "2025-10-14"),
			("Service Year", "2026-10-13", "2026-03-15"),
			("Service Year", "2026-02-01", "2025-03-15"),
		):
			policy.sick_leave_window = mode
			self.assertEqual(window_start(policy, None, COMPANY, on_date), getdate(expected), (mode, on_date))

	def test_the_service_year_window_starts_each_anniversary_afresh(self):
		self.set_country("SA", sick_leave_window="Service Year")
		emp = self.staff("Anniversary", joined="2025-07-01")
		self.sick(emp, "2026-05-01", "2026-05-30")  # 30 days in the year to 30 June
		july = self.sick(emp, "2026-07-10", "2026-07-20")  # a new service year: day 1 again
		self.assertEqual(self.split(july), [("Full pay", 11)])

	def test_the_default_window_is_the_leave_period(self):
		emp = self.staff("Calendar")
		self.sick(emp, "2026-05-01", "2026-05-30")
		july = self.sick(emp, "2026-07-10", "2026-07-20")
		self.assertEqual(self.split(july), [("75% pay", 11)])


# ── allocations outside the ledger ────────────────────────────────────────────


class TestLegacyAllocations(LeaveTestBase):
	def test_an_allocation_the_ledger_did_not_make_is_reported(self):
		from hr_suite.hr_suite.leave_accrual import legacy_annual_allocations

		emp = self.employee("Legacy", "SA", "2026-01-01")
		alloc = frappe.get_doc(
			doctype="Leave Allocation", employee=emp, leave_type="Annual Leave", from_date="2026-01-01",
			to_date="2026-12-31", new_leaves_allocated=30,
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()
		self.assertIn((emp, alloc.name, 30), [(r["employee"], r["allocation"], r["days"]) for r in legacy_annual_allocations("2026-06-01")])

	def test_the_ledgers_own_allocation_is_not(self):
		from hr_suite.hr_suite.leave_accrual import legacy_annual_allocations

		emp = self.employee("Mine", "SA", "2026-01-01")
		accrue_employee(emp, "2026-02-28")
		self.assertNotIn(emp, [r["employee"] for r in legacy_annual_allocations("2026-06-01")])

	def test_an_upfront_grant_the_ledger_later_topped_up_is_still_reported(self):
		"""The UAT case (TT33): a 30-day grant exists first, the ledger then accrues onto that same allocation."""
		from hr_suite.hr_suite.leave_accrual import legacy_annual_allocations

		emp = self.employee("Topped", "SA", "2026-01-01")
		alloc = frappe.get_doc(
			doctype="Leave Allocation", employee=emp, leave_type="Annual Leave", from_date="2026-01-01",
			to_date="2026-12-31", new_leaves_allocated=30,
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()
		accrue_employee(emp, "2026-02-28")  # 2 x 1.75 posted onto the same allocation

		found = [(r["employee"], r["allocation"], r["days"]) for r in legacy_annual_allocations("2026-06-01")]
		self.assertIn((emp, alloc.name, 30), found)  # the 30 only, never the 3.5 the ledger posted


# ── accrual runs from the joining date ────────────────────────────────────────


class TestAccrualFromJoining(LeaveTestBase):
	"""UAT: an employee who joined in 2020 only had accruals from 2023 (a 36-month catch-up cap)."""

	def start_date(self, value):
		doc = frappe.get_doc("Country Config", "SA")
		doc.leave_ledger_start_date = value
		doc.save(ignore_permissions=True)

	def periods(self, emp):
		return [
			str(r.period_start)
			for r in frappe.get_all(
				"Leave Accrual Ledger", filters={"employee": emp, "source": "Accrual"}, fields=["period_start"], order_by="period_start"
			)
		]

	def test_a_long_serving_employee_accrues_from_the_joining_month(self):
		self.addCleanup(self.start_date, "2026-01-01")
		self.start_date(None)
		emp = self.employee("Veteran", "SA", "2020-01-01")
		created = accrue_employee(emp, "2026-09-30")

		periods = self.periods(emp)
		self.assertEqual(len(created), 81)  # Jan 2020 .. Sep 2026, nothing dropped
		self.assertEqual(periods[0], "2020-01-01")
		self.assertEqual(periods[-1], "2026-09-01")
		self.assertTrue(frappe.db.exists("Leave Allocation", {"employee": emp, "from_date": "2020-01-01", "docstatus": 1}))

	def test_months_an_older_run_left_out_behind_the_first_row_are_filled(self):
		self.addCleanup(self.start_date, "2026-01-01")
		self.start_date("2023-10-01")  # what the 36-month cap used to produce
		emp = self.employee("Capped", "SA", "2020-01-01")
		self.assertEqual(len(accrue_employee(emp, "2026-09-30")), 36)

		self.start_date(None)
		filled = accrue_employee(emp, "2026-09-30")
		self.assertEqual(len(filled), 45)  # Jan 2020 .. Sep 2023
		self.assertEqual(self.periods(emp)[0], "2020-01-01")
		self.assertEqual(len(self.periods(emp)), 81)
		self.assertEqual(accrue_employee(emp, "2026-09-30"), [])  # and it is repeatable

	def test_an_opening_balance_still_stops_earlier_months_accruing(self):
		self.addCleanup(self.start_date, "2026-01-01")
		self.start_date(None)
		emp = self.employee("Opened", "SA", "2020-01-01")
		frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="2025-12-31", leave_days=20, salary_days=20
		).insert(ignore_permissions=True)
		created = accrue_employee(emp, "2026-03-31")
		self.assertEqual(self.periods(emp), ["2026-01-01", "2026-02-01", "2026-03-01"])
		self.assertEqual(len(created), 3)


# ── Saudi gratuity rule in the HRMS list ──────────────────────────────────────


class TestGratuityRules(FrappeTestCase):
	NAME = "Saudi Arabia - Termination / End Of Contract"

	def test_the_saudi_rule_is_in_the_hrms_list_with_the_country_slabs(self):
		rule = frappe.get_doc("Gratuity Rule", self.NAME)
		self.assertEqual(rule.calculate_gratuity_amount_based_on, "Sum of all previous slabs")
		self.assertEqual(
			[(s.from_year, s.to_year, s.fraction_of_applicable_earnings) for s in rule.gratuity_rule_slabs],
			[(0, 5, 0.5), (5, 0, 1.0)],  # 15 days = half a month a year, then a month a year
		)

	def test_the_hrms_gratuity_form_pays_the_same_as_the_spec(self):
		from unittest.mock import patch

		doc = frappe.new_doc("Gratuity")
		doc.gratuity_rule = self.NAME
		with patch.object(type(doc), "get_total_component_amount", return_value=6000):
			self.assertEqual(doc.get_gratuity_amount(7), 27000)  # (5 x 15 + 2 x 30) days at 200
			self.assertEqual(doc.get_gratuity_amount(7.5), 30000)  # 2.5 + 2.5 months of 6,000: the half year is pro-rated
			self.assertEqual(doc.get_gratuity_amount(3), 9000)

	def test_countries_hrms_cannot_express_are_left_out(self):
		from hr_suite.hr_suite.gratuity_rules import _expressible
		from hr_suite.hr_suite.policy import get_country_policy

		self.assertFalse(_expressible(get_country_policy("SA")))
		self.assertIn("cap", str(_expressible(get_country_policy("KW"))))
		self.assertIn("ends", str(_expressible(get_country_policy("BH"))))

	def test_an_edited_rule_is_not_overwritten(self):
		from hr_suite.hr_suite.gratuity_rules import sync_gratuity_rules

		frappe.db.set_value("Gratuity Rule", self.NAME, "minimum_year_for_gratuity", 3)
		sync_gratuity_rules()
		self.assertEqual(frappe.db.get_value("Gratuity Rule", self.NAME, "minimum_year_for_gratuity"), 3)


# ── payment advice: automatic ─────────────────────────────────────────────────


class TestAutomaticPaymentAdvice(FrappeTestCase):
	def run_job(self, created=True, configured=True, boom=False):
		from unittest.mock import patch

		from hr_suite.hr_suite import payment_advice as pa

		result = {"advice": "ADV-1", "doctype": pa.ADVICE_DOCTYPE, "created": created}
		with patch.object(pa, "raise_for_document", side_effect=RuntimeError("x") if boom else None, return_value=result), patch(
			"hr_suite.hr_suite.payment_advice_flow.approvals_configured", return_value=configured
		), patch("hr_suite.hr_suite.payment_advice_flow.submit_for_approval") as send, patch.object(
			pa.frappe.db, "get_value", return_value="Steel Force Trading WLL"
		), patch.object(pa.frappe.db, "commit"), patch.object(pa.frappe.db, "rollback"), patch.object(pa.frappe, "log_error") as log:
			pa.raise_after_submit("Leave Salary Settlement", "LSS-1")
		return send, log

	def test_with_approvers_the_advice_is_sent_for_approval(self):
		send, _log = self.run_job()
		send.assert_called_once_with("ADV-1")

	def test_without_approvers_it_stays_a_draft(self):
		send, _log = self.run_job(configured=False)
		send.assert_not_called()

	def test_an_advice_that_already_existed_is_not_sent_again(self):
		send, _log = self.run_job(created=False)
		send.assert_not_called()

	def test_a_failure_is_logged_never_raised(self):
		_send, log = self.run_job(boom=True)
		log.assert_called_once()


# ── accrual before an existing carry-forward allocation ───────────────────────


class TestAccrualBeforeCarryForward(LeaveTestBase):
	def test_a_month_before_a_carry_forward_allocation_is_credited_to_it(self):
		self.start_ledger("2025-12-01")
		emp = self.employee("Carried", "SA", "2024-01-01")
		alloc = frappe.get_doc(
			doctype="Leave Allocation", employee=emp, leave_type="Annual Leave", from_date="2026-01-01",
			to_date="2026-12-31", new_leaves_allocated=1, carry_forward=1,
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()

		created = accrue_employee(emp, "2026-01-31")  # December 2025 and January 2026
		self.assertEqual(len(created), 2)  # no BackDatedAllocationError, nothing lost
		self.assertEqual(self.balance(emp, "2026-01-31"), 4.5)  # the 1 day held + 1.75 + 1.75
		self.assertEqual(
			frappe.get_all("Leave Accrual Ledger", filters={"employee": emp}, pluck="leave_allocation"), [alloc.name] * 2
		)


class TestLegacyAnnualLeaveCopyNeverStopsMigrate(FrappeTestCase):
	"""27 Oct: six leaves the legacy Annual Leave balance check refused made every migrate on sft-uat fail."""

	def test_a_row_that_cannot_be_copied_is_skipped_and_logged(self):
		from hr_suite import install

		row = frappe._dict(name="HR-LAP-TEST-LEGACY", employee="X")
		with (
			patch.object(install.frappe, "get_all", return_value=[row]),
			patch.object(install, "_copy_legacy_annual_leave", side_effect=frappe.ValidationError("refused")),
			patch.object(install.frappe, "log_error") as logged,
		):
			install.migrate_legacy_annual_leave()  # must not raise
		self.assertEqual(logged.call_count, 1)
		self.assertIn("HR-LAP-TEST-LEGACY", logged.call_args.kwargs["message"])
