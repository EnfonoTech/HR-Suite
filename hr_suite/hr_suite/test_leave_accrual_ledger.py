"""Phase 3 - Leave Accrual Ledger: month arithmetic, the monthly job, and the leave rules."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from hr_suite.hr_suite.leave_accrual import (
	accrue_employee,
	accrual_for_month,
	check_annual_leave_rules,
	get_salary_days_balance,
)

COMPANY = "HRS Dev"


def month(start, end, joining="2020-01-01", relieving=None, leave=0, unpaid=0, basis="Over 30 Days"):
	return accrual_for_month(start, end, joining, relieving, leave, unpaid, 2.5, 1.75, basis)


class TestMonthArithmetic(FrappeTestCase):
	def test_a_full_month_earns_exactly_the_monthly_rate_whatever_its_length(self):
		for start, end in (("2026-02-01", "2026-02-28"), ("2026-04-01", "2026-04-30"), ("2026-03-01", "2026-03-31")):
			result = month(start, end)
			self.assertEqual(result.days_worked, 30)
			self.assertEqual(result.leave_days, 2.5)
			self.assertEqual(result.salary_days, 1.75)

	def test_joining_month_over_30_days(self):
		# joining 9 March: 8 days excluded, 23 worked -> 23/30 x 2.5 = 1.92
		result = month("2026-03-01", "2026-03-31", joining="2026-03-09")
		self.assertEqual(result.days_worked, 23)
		self.assertEqual(result.leave_days, 1.92)

	def test_joining_month_scaled_to_the_month(self):
		# 23/31 x 30 = 22.26 days -> 2.5 x 22.258/30 = 1.85, the spec's figure
		result = month("2026-03-01", "2026-03-31", joining="2026-03-09", basis="Month Fraction")
		self.assertEqual(result.days_worked, 22.26)
		self.assertEqual(result.leave_days, 1.85)

	def test_exit_month(self):
		# leaves on the 20th of a 30-day month: 10 days after exit excluded
		result = month("2026-04-01", "2026-04-30", relieving="2026-04-20")
		self.assertEqual(result.days_worked, 20)
		self.assertEqual(result.leave_days, 1.67)

	def test_annual_leave_and_unpaid_days_reduce_the_month(self):
		result = month("2026-03-01", "2026-03-31", leave=5, unpaid=2)
		self.assertEqual(result.days_worked, 24)  # 31 - 7
		self.assertEqual(result.leave_days, 2.0)

	def test_sick_leave_is_not_an_input(self):
		# the function takes no sick-leave argument: sick days cannot reduce accrual
		self.assertEqual(month("2026-03-01", "2026-03-31").leave_days, 2.5)

	def test_excluded_days_never_exceed_the_month(self):
		result = month("2026-03-01", "2026-03-31", leave=40)
		self.assertEqual(result.days_worked, 0)
		self.assertEqual(result.leave_days, 0)


def set_leave_workflow(active):
	"""Switch the Leave Application approval workflow; returns what it was."""
	from hr_suite.hr_suite.leave_workflow import WORKFLOW

	was = frappe.db.get_value("Workflow", WORKFLOW, "is_active")
	if was is not None and int(was) != int(active):
		doc = frappe.get_doc("Workflow", WORKFLOW)
		doc.is_active = int(active)
		doc.save(ignore_permissions=True)
	return was


class LedgerTestBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# These tests insert already-approved Leave Applications, which an active approval
		# workflow refuses (a new document may only start in its first state).
		cls._workflow_was = set_leave_workflow(0)
		for code in ("SA", "BH"):
			doc = frappe.get_doc("Country Config", code)
			doc.leave_accrual_engine = "HR Suite Ledger"
			doc.leave_ledger_start_date = "2026-01-01"
			doc.save(ignore_permissions=True)
		# Leave Types are synced only for countries that have active employees.
		for code in ("SA", "BH"):
			cls._make_employee("Anchor" + code, code, "2019-01-01")

		from hr_suite.hr_suite.leave_setup import sync_leave_types_from_country_config

		sync_leave_types_from_country_config()

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		set_leave_workflow(cls._workflow_was)
		for code in ("SA", "BH"):
			frappe.clear_document_cache("Country Config", code)

	@staticmethod
	def _make_employee(first, country, joined):
		doc = frappe.get_doc(
			doctype="Employee", first_name=first, last_name="Ledger", gender="Male", date_of_birth="1990-01-01",
			date_of_joining=joined, company=COMPANY, status="Active", work_country=country,
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def employee(self, first, country, joined):
		return self._make_employee(first, country, joined)

	def balance(self, employee, on_date):
		from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

		return flt(get_leave_balance_on(employee, "Annual Leave", on_date), 2)


class TestMonthlyAccrual(LedgerTestBase):
	def test_ksa_joiner_accrues_each_month_into_ledger_and_hrms(self):
		emp = self.employee("Joiner", "SA", "2026-01-15")
		created = accrue_employee(emp, "2026-03-31")
		self.assertEqual(len(created), 3)

		rows = frappe.get_all(
			"Leave Accrual Ledger", filters={"employee": emp}, fields=["period_start", "days_worked", "leave_days", "salary_days"],
			order_by="period_start",
		)
		# 21 days a year = 1.75 a month; January is 17 of 31 days -> 17/30
		self.assertEqual([r.days_worked for r in rows], [17, 30, 30])
		self.assertEqual([r.leave_days for r in rows], [0.99, 1.75, 1.75])
		self.assertEqual(get_salary_days_balance(emp), 4.49)
		self.assertEqual(self.balance(emp, "2026-03-31"), 4.49)

	def test_running_twice_creates_nothing_new(self):
		emp = self.employee("Twice", "SA", "2026-01-01")
		accrue_employee(emp, "2026-02-28")
		self.assertEqual(accrue_employee(emp, "2026-02-28"), [])
		self.assertEqual(frappe.db.count("Leave Accrual Ledger", {"employee": emp}), 2)

	def test_a_missed_run_is_made_up_by_the_next(self):
		emp = self.employee("Missed", "SA", "2026-01-01")
		accrue_employee(emp, "2026-01-31")
		self.assertEqual(len(accrue_employee(emp, "2026-04-30")), 3)

	def test_the_ksa_band_steps_up_after_five_years(self):
		emp = self.employee("Veteran", "SA", "2020-01-01")
		accrue_employee(emp, "2026-01-31")
		row = frappe.get_all("Leave Accrual Ledger", filters={"employee": emp}, fields=["leave_days"])[0]
		self.assertEqual(row.leave_days, 2.5)  # 30 a year after five years

	def test_an_employee_override_changes_leave_and_salary_days_separately(self):
		emp = self.employee("Override", "SA", "2026-01-01")
		frappe.db.set_value("Employee", emp, {"override_leave_days_per_year": 30, "override_salary_days_per_year": 21})
		accrue_employee(emp, "2026-01-31")
		row = frappe.get_all("Leave Accrual Ledger", filters={"employee": emp}, fields=["leave_days", "salary_days"])[0]
		self.assertEqual((row.leave_days, row.salary_days), (2.5, 1.75))

	def test_annual_leave_taken_reduces_that_months_accrual(self):
		emp = self.employee("Away", "SA", "2026-01-01")
		with patch("hr_suite.hr_suite.leave_accrual.get_leave_days", return_value=5):
			accrue_employee(emp, "2026-02-28")
		feb = frappe.get_all("Leave Accrual Ledger", filters={"employee": emp, "period_start": "2026-02-01"}, fields=["days_worked"])[0]
		self.assertEqual(feb.days_worked, 23)  # 28 - 5

	def test_the_old_hrms_accrual_is_off_for_ledger_countries(self):
		leave_type = frappe.get_doc("Leave Type", "Annual Leave")
		self.assertEqual(leave_type.is_earned_leave, 0)
		self.assertEqual(leave_type.allow_negative, 1)


class TestOpeningBalance(LedgerTestBase):
	def test_opening_balance_then_accrual_resumes_the_next_month(self):
		emp = self.employee("Opening", "SA", "2019-05-01")
		opening = frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="2026-02-28", leave_days=12, salary_days=10,
		).insert(ignore_permissions=True)
		self.assertEqual(self.balance(emp, "2026-02-28"), 12)

		created = accrue_employee(emp, "2026-04-30")
		self.assertEqual(len(created), 2)  # March and April only; Feb is inside the opening balance
		self.assertEqual(opening.period_start, opening.period_end)
		self.assertEqual(get_salary_days_balance(emp), 10 + 2 * 1.75 * 0 + 2 * 2.5)  # 2020+ joiner: 30 days a year
		self.assertEqual(self.balance(emp, "2026-04-30"), 17)

	def test_opening_is_imported_once(self):
		emp = self.employee("Once", "SA", "2020-01-01")
		args = dict(doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="2026-02-28", leave_days=5, salary_days=5)
		frappe.get_doc(args).insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, frappe.get_doc(args).insert, ignore_permissions=True)

	def test_opening_cannot_follow_accrual(self):
		emp = self.employee("Late", "SA", "2026-01-01")
		accrue_employee(emp, "2026-01-31")
		self.assertRaises(
			frappe.ValidationError,
			frappe.get_doc(doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="2026-01-31", leave_days=5, salary_days=5).insert,
			ignore_permissions=True,
		)

	def test_adjustment_moves_both_balances_and_can_be_negative(self):
		emp = self.employee("Adjust", "SA", "2026-01-01")
		accrue_employee(emp, "2026-01-31")
		frappe.get_doc(doctype="Leave Accrual Ledger", employee=emp, source="Adjustment", period_end="2026-01-31", leave_days=-0.75, salary_days=-0.5).insert(ignore_permissions=True)
		self.assertEqual(self.balance(emp, "2026-01-31"), 1.0)
		self.assertEqual(get_salary_days_balance(emp), 1.25)

	def test_a_ledger_row_cannot_be_deleted(self):
		emp = self.employee("Keep", "SA", "2026-01-01")
		name = accrue_employee(emp, "2026-01-31")[0]
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Leave Accrual Ledger", name)


class TestAnnualLeaveRules(LedgerTestBase):
	def application(self, emp, days, balance, start="2026-09-01"):
		doc = frappe._dict(employee=emp, leave_type="Annual Leave", from_date=start, to_date=start, total_leave_days=days)
		doc.balance = balance
		return doc

	def run_rule(self, doc, roles):
		"""Run the rule as a user holding `roles`, with the HRMS balance fixed at doc.balance."""
		with patch("frappe.get_roles", return_value=roles), patch(
			"hr_suite.hr_suite.leave_accrual._balance_for_consumption", return_value=doc.balance
		):
			check_annual_leave_rules(doc)

	def test_self_service_cannot_exceed_the_balance(self):
		emp = self.employee("Capped", "SA", "2020-01-01")
		self.assertRaises(frappe.ValidationError, self.run_rule, self.application(emp, 10, 5), ["Employee"])
		self.run_rule(self.application(emp, 5, 5), ["Employee"])  # exactly the balance is fine

	def test_hr_with_the_override_role_may_go_negative(self):
		emp = self.employee("Advance", "SA", "2020-01-01")
		self.run_rule(self.application(emp, 10, 5), ["HR Manager", "HR Leave Override"])

	def test_bahrain_leave_is_not_available_before_a_year(self):
		emp = self.employee("Early", "BH", "2026-03-01")
		doc = self.application(emp, 2, 10, start="2026-09-01")
		self.assertRaises(frappe.ValidationError, self.run_rule, doc, ["Employee"])
		self.run_rule(doc, ["HR Leave Override"])

	def test_other_leave_types_are_untouched(self):
		emp = self.employee("Sick", "SA", "2020-01-01")
		doc = self.application(emp, 40, 0)
		doc.leave_type = "Sick Leave"
		self.run_rule(doc, ["Employee"])

	def test_the_balance_is_read_from_hrms_not_the_empty_form_field(self):
		"""Regression: Leave Application.leave_balance is filled in by the browser only, so it
		is empty on the server; reading it made every application look like it exceeded 0."""
		emp = self.employee("Real", "SA", "2025-06-01")
		accrue_employee(emp, "2026-03-31")  # 5.25 days accrued
		doc = frappe._dict(employee=emp, leave_type="Annual Leave", from_date="2026-04-05", to_date="2026-04-06", total_leave_days=2)
		with patch("frappe.get_roles", return_value=["Employee"]):
			check_annual_leave_rules(doc)  # 2 days against a real balance of 5.25: allowed
