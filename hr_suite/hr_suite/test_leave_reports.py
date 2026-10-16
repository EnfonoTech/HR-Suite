"""Phase 7 - the leave, settlement and gratuity reports."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from hr_suite.hr_suite.leave_accrual import accrue_employee
from hr_suite.hr_suite.report.gratuity_liability.gratuity_liability import execute as gratuity
from hr_suite.hr_suite.report.leave_accrual_ledger_report.leave_accrual_ledger_report import execute as ledger_report
from hr_suite.hr_suite.report.leave_and_salary_days_balance.leave_and_salary_days_balance import execute as balances
from hr_suite.hr_suite.report.leave_salary_settlements_due.leave_salary_settlements_due import execute as settlements_due
from hr_suite.hr_suite.test_leave_salary_settlement import SettlementTestBase

YEAR = frappe.utils.getdate(today()).year


def by_employee(rows, employee):
	return next((r for r in rows if r["employee"] == employee), None)


class TestReportsOpen(FrappeTestCase):
	def test_every_report_runs_without_filters(self):
		for report in (balances, ledger_report, settlements_due, gratuity):
			columns, data = report({})
			self.assertTrue(columns)
			self.assertIsInstance(data, list)

	def test_the_reports_are_registered(self):
		for name in ("Leave and Salary Days Balance", "Leave Accrual Ledger Report", "Leave Salary Settlements Due", "Gratuity Liability"):
			self.assertTrue(frappe.db.exists("Report", name), name)


class TestBalances(SettlementTestBase):
	def opening(self, emp, days):
		frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=emp, source="Opening", period_end="%s-01-31" % YEAR, leave_days=days, salary_days=days,
		).insert(ignore_permissions=True)

	def test_both_balances_side_by_side(self):
		emp = self.employee("Both", "SA", "2019-01-01")
		self.opening(emp, 40)
		_c, rows = balances({"employee": emp})
		row = by_employee(rows, emp)
		self.assertEqual(row["engine"], "HR Suite Ledger")
		self.assertEqual((row["leave_balance"], row["salary_days_earned"], row["salary_days_spent"], row["salary_days_balance"]), (40, 40, 0, 40))
		self.assertEqual(row["barrier_met"], "Yes")
		self.assertEqual(row["leave_days_per_year"], 30)  # past five years: the 30-day band

	def test_settled_days_leave_the_salary_balance_and_the_shortfall_is_named(self):
		emp = self.staff("Settled")
		self.settle(emp, self.leave(emp))
		_c, rows = balances({"employee": emp})
		row = by_employee(rows, emp)
		self.assertEqual((row["salary_days_earned"], row["salary_days_spent"], row["salary_days_balance"]), (40, 30, 10))
		self.assertEqual(row["barrier_met"], "No")
		self.assertIn("10", row["shortfall"])

	def test_a_country_on_hrms_accrual_shows_no_salary_balance(self):
		self.set_country(leave_accrual_engine="")
		emp = self.employee("Legacy", "SA", "2019-01-01")
		_c, rows = balances({"employee": emp})
		row = by_employee(rows, emp)
		self.assertEqual(row["engine"], "HRMS Earned Leave")
		self.assertIsNone(row.get("salary_days_balance"))
		_c, ledger_only = balances({"employee": emp, "ledger_only": 1})
		self.assertEqual(ledger_only, [])


class TestLedgerReport(SettlementTestBase):
	def test_running_balance_per_employee_in_date_order(self):
		emp = self.staff("Running", opening=12)
		accrue_employee(emp, "%s-05-31" % YEAR)  # April and May after the March opening
		_c, rows = ledger_report({"employee": emp})
		self.assertEqual([r["source"] for r in rows], ["Opening", "Accrual", "Accrual"])
		self.assertEqual([r["salary_balance"] for r in rows], [12, 14.5, 17])  # 30 a year: 2.5 a month

	def test_filters_by_source_and_period(self):
		emp = self.staff("Filtered", opening=12)
		accrue_employee(emp, "%s-05-31" % YEAR)
		_c, rows = ledger_report({"employee": emp, "source": "Accrual"})
		self.assertEqual(len(rows), 2)
		_c, rows = ledger_report({"employee": emp, "from_date": "%s-05-01" % YEAR})
		self.assertEqual([r["source"] for r in rows], ["Accrual"])

	def test_a_settlement_appears_as_negative_salary_days_with_its_reference(self):
		emp = self.staff("Spent")
		doc = self.settle(emp, self.leave(emp))
		_c, rows = ledger_report({"employee": emp, "source": "Settlement"})
		self.assertEqual([r["salary_days"] for r in rows], [-30])
		self.assertIn(doc.name, rows[0]["reference"])


class TestSettlementsDue(SettlementTestBase):
	def soon(self, emp, opening_days=40):
		start = add_days(today(), 5)
		return self.leave(emp, start=start, end=add_days(start, 29))

	def test_an_approved_leave_with_nothing_settled_is_listed_with_what_could_be_paid(self):
		emp = self.staff("Due", opening=40)
		frappe.db.set_value("Leave Accrual Ledger", {"employee": emp}, "period_end", "%s-01-31" % YEAR)
		la = self.soon(emp)
		_c, rows = settlements_due({"employee": emp})
		row = by_employee(rows, emp)
		self.assertEqual((row["reason"], row["leave_application"], row["salary_days_due"]), ("No settlement", la, 30))
		self.assertEqual((row["earned_balance"], row["payable_now"], row["barrier"]), (40, 30, "Met"))

	def test_below_the_barrier_nothing_is_payable_now(self):
		emp = self.staff("Short", opening=20)
		self.soon(emp)
		row = by_employee(settlements_due({"employee": emp})[1], emp)
		self.assertEqual(row["payable_now"], 0)
		self.assertTrue(row["barrier"].startswith("Short"))

	def test_a_part_paid_leave_stays_listed_until_it_is_fully_paid(self):
		from unittest.mock import patch

		emp = self.staff("Part", opening=20)
		start = add_days(today(), 5)
		la = self.leave(emp, start=start, end=add_days(start, 29))
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			doc = frappe.get_doc(
				doctype="Leave Salary Settlement", employee=emp, leave_application=la, last_working_day=add_days(start, -1),
				pay_below_barrier=1, barrier_override_reason="advance",
			).insert(ignore_permissions=True)
			doc.submit()
		row = by_employee(settlements_due({"employee": emp})[1], emp)
		self.assertEqual((row["reason"], row["salary_days_due"], row["settlement"]), ("Salary days still due", 10, doc.name))

	def test_leave_further_away_than_the_window_is_not_listed(self):
		emp = self.staff("Far", opening=40)
		start = add_days(today(), 90)
		self.leave(emp, start=start, end=add_days(start, 9))
		self.assertIsNone(by_employee(settlements_due({"employee": emp, "within_days": 30})[1], emp))


class TestGratuityLiability(FrappeTestCase):
	def employee(self, name, country, joined, ctc):
		doc = frappe.get_doc(
			doctype="Employee", first_name=name, last_name="Liab", gender="Male", date_of_birth="1980-01-01",
			date_of_joining=joined, company="HRS Dev", status="Active", work_country=country, ctc=ctc,
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_ksa_employee_liability_matches_the_engine_and_resignation_is_lower(self):
		from hr_suite.hr_suite.utils import calculate_settlement

		emp = self.employee("Ksa", "SA", "2019-01-01", 3000)
		_c, rows = gratuity({"as_on": "2026-01-01", "company": "HRS Dev"})
		row = by_employee(rows, emp)
		expected = calculate_settlement(emp, "Termination by Employer", "2026-01-01")["net_entitlement"]
		self.assertEqual(row["liability_termination"], expected)
		self.assertGreater(row["liability_termination"], 0)
		self.assertLess(row["liability_resignation"], row["liability_termination"])  # 7 years: two-thirds
		self.assertEqual(row["wage_base"], 3000)

	def test_a_qatar_employee_uses_its_own_slabs(self):
		emp = self.employee("Qa", "QA", "2024-01-02", 5000)  # exactly 730 days to 1 Jan 2026
		row = by_employee(gratuity({"as_on": "2026-01-01"})[1], emp)
		self.assertEqual(row["liability_termination"], 7000)  # 2 years x 3 weeks (0.7 month) x 5,000

	def test_india_keeps_the_gratuity_act_figure(self):
		emp = self.employee("In", "IN", "2018-01-01", 20000)
		row = by_employee(gratuity({"as_on": "2026-01-01"})[1], emp)
		self.assertEqual(row["liability_termination"], round(15 / 26 * 20000 * 8, 2))

	def test_an_employee_who_cannot_be_calculated_is_listed_with_why_not_dropped(self):
		emp = self.employee("NoPay", "SA", "2019-01-01", 0)
		row = by_employee(gratuity({"as_on": "2026-01-01"})[1], emp)
		self.assertTrue(row["note"].startswith("Not calculated"))
		self.assertIsNone(row.get("liability_termination"))

	def test_someone_who_joins_after_the_date_is_not_liable_yet(self):
		emp = self.employee("Future", "SA", "2027-01-01", 3000)
		self.assertIsNone(by_employee(gratuity({"as_on": "2026-01-01"})[1], emp))
