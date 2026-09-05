from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.doctype.employee_loan import employee_loan as loan_module


test_ignore = ["Journal Entry"]


class TestEmployeeLoan(FrappeTestCase):
	def test_build_installment_plan_equal_installments_balances_last_row(self):
		rows = loan_module._build_installment_plan(
			1000,
			"Equal Installments",
			3,
			0,
			date(2026, 1, 1),
		)

		self.assertEqual(len(rows), 3)
		self.assertEqual(rows[0]["installment_amount"], 333.33)
		self.assertEqual(rows[1]["installment_amount"], 333.33)
		self.assertEqual(rows[2]["installment_amount"], 333.34)

	def test_build_installment_plan_fixed_installment_creates_final_partial_row(self):
		rows = loan_module._build_installment_plan(
			950,
			"Fixed Installment Amount",
			0,
			300,
			date(2026, 1, 1),
		)

		self.assertEqual([row["installment_amount"] for row in rows], [300, 300, 300, 50])

	def test_get_due_loan_deduction_sums_outstanding_rows(self):
		fake_rows = [
			frappe._dict(loan_name="LOAN-1", installment_name="INST-1", installment_amount=250, outstanding_amount=250),
			frappe._dict(loan_name="LOAN-1", installment_name="INST-2", installment_amount=250, outstanding_amount=100),
		]
		with patch.object(loan_module.frappe.db, "sql", return_value=fake_rows):
			result = loan_module.get_due_loan_deduction("EMP-0001", 3, 2026)

		self.assertEqual(result["loan_deduction"], 350)
		self.assertEqual(result["installment_names"], ["INST-1", "INST-2"])
		self.assertEqual(result["loan_names"], ["LOAN-1"])

	def test_apply_and_revert_payroll_loan_deduction_preserve_partial_history(self):
		class _Installment:
			def __init__(self):
				self.name = "INST-1"
				self.parent = "LOAN-1"
				self.installment_amount = 250
				self.deducted_amount = 150
				self.outstanding_amount = 100
				self.deduction_status = "Pending"
				self.deduction_date = None
				self.payroll_reference = None
				self.payroll_deducted_amount = 0

			def db_set(self, fieldname, value, update_modified=False):
				setattr(self, fieldname, value)

		installment = _Installment()
		payroll_doc = SimpleNamespace(
			name="PAY-0001",
			posting_date="2026-03-31",
			employees=[frappe._dict({"loan_installments": "INST-1"})],
		)

		def _locked_state(_name):
			return frappe._dict({
				"name": installment.name,
				"parent": installment.parent,
				"installment_amount": installment.installment_amount,
				"deducted_amount": installment.deducted_amount,
				"outstanding_amount": installment.outstanding_amount,
				"deduction_status": installment.deduction_status,
				"payroll_reference": installment.payroll_reference,
				"payroll_deducted_amount": installment.payroll_deducted_amount,
			})

		with patch.object(loan_module, "_get_locked_installment_state", side_effect=_locked_state), patch.object(
			loan_module.frappe, "get_doc", return_value=installment
		), patch.object(
			loan_module, "_update_parent_loan_summary"
		):
			loan_module.apply_payroll_loan_deductions(payroll_doc)
			loan_module.apply_payroll_loan_deductions(payroll_doc)

		self.assertEqual(installment.deducted_amount, 250)
		self.assertEqual(installment.outstanding_amount, 0)
		self.assertEqual(installment.payroll_deducted_amount, 100)
		self.assertEqual(installment.payroll_reference, "PAY-0001")

		with patch.object(loan_module.frappe, "get_all", return_value=[frappe._dict({
			"name": "INST-1",
			"parent": "LOAN-1",
			"installment_amount": 250,
			"payroll_deducted_amount": 100,
		})]), patch.object(loan_module.frappe, "get_doc", return_value=installment), patch.object(
			loan_module, "_update_parent_loan_summary"
		):
			loan_module.revert_payroll_loan_deductions(payroll_doc)

		self.assertEqual(installment.deducted_amount, 150)
		self.assertEqual(installment.outstanding_amount, 100)
		self.assertEqual(installment.payroll_deducted_amount, 0)
		self.assertIsNone(installment.payroll_reference)

	def test_apply_payroll_loan_deduction_blocks_conflicting_payroll(self):
		payroll_doc = SimpleNamespace(
			name="PAY-0002",
			posting_date="2026-03-31",
			employees=[frappe._dict({"loan_installments": "INST-1"})],
		)

		with patch.object(loan_module, "_get_locked_installment_state", return_value=frappe._dict({
			"name": "INST-1",
			"parent": "LOAN-1",
			"installment_amount": 250,
			"deducted_amount": 250,
			"outstanding_amount": 0,
			"deduction_status": "Deducted",
			"payroll_reference": "PAY-OTHER",
			"payroll_deducted_amount": 250,
		})):
			with self.assertRaises(frappe.ValidationError):
				loan_module.apply_payroll_loan_deductions(payroll_doc)


class TestEmployeeLoanPayrollBooking(FrappeTestCase):
	"""The Employee Loan -> Additional Salary -> Salary Slip route.

	`apply_payroll_loan_deductions` is only ever called by hr_suite's Monthly Payroll, so
	a loan run through the supported Payroll Entry -> Salary Slip path used to be silently
	never deducted. These defend the wiring that fixes that, and above all the single
	rule that keeps it safe: an instalment belongs to exactly one payroll engine.
	"""

	def _installment(self, **overrides):
		row = {
			"installment_amount": 100,
			"deducted_amount": 0,
			"outstanding_amount": 100,
			"deduction_status": loan_module.INSTALLMENT_PENDING,
		}
		row.update(overrides)
		return frappe._dict(row)

	def test_outstanding_balance_falls_as_instalments_are_deducted(self):
		"""Regression: `outstanding_amount or installment_amount` treated a fully
		recovered instalment (outstanding 0, therefore falsy) as still wholly owed, so a
		loan could be repaid in full and still report its entire principal outstanding,
		and `status` could never reach Closed."""
		loan = frappe.new_doc("Employee Loan")
		loan.docstatus = 1
		loan.set("installments", [])
		for row in (
			self._installment(deducted_amount=100, outstanding_amount=0, deduction_status="Deducted"),
			self._installment(deducted_amount=100, outstanding_amount=0, deduction_status="Deducted"),
			self._installment(deduction_status="Scheduled"),
		):
			loan.append("installments", row)

		loan._update_summary()

		self.assertEqual(loan.total_deducted, 200)
		self.assertEqual(loan.outstanding_balance, 100)
		self.assertEqual(loan.status, "Active")

	def test_a_fully_recovered_loan_closes(self):
		loan = frappe.new_doc("Employee Loan")
		loan.docstatus = 1
		loan.set("installments", [])
		loan.append(
			"installments",
			self._installment(deducted_amount=100, outstanding_amount=0, deduction_status="Deducted"),
		)

		loan._update_summary()

		self.assertEqual(loan.outstanding_balance, 0)
		self.assertEqual(loan.status, "Closed")

	def test_a_cancelled_instalment_is_not_owed(self):
		loan = frappe.new_doc("Employee Loan")
		loan.docstatus = 1
		loan.set("installments", [])
		loan.append("installments", self._installment(deduction_status="Cancelled"))

		loan._update_summary()

		self.assertEqual(loan.outstanding_balance, 0)

	def test_monthly_payroll_refuses_an_instalment_already_booked_onto_a_payslip(self):
		"""THE double-deduction guard. Real money: taking it twice is worse than never."""
		payroll_doc = SimpleNamespace(
			name="PAY-0003",
			posting_date="2026-10-31",
			employees=[frappe._dict({"loan_installments": "INST-9"})],
		)
		booked = frappe._dict({
			"name": "INST-9",
			"parent": "LOAN-9",
			"installment_number": 2,
			"installment_amount": 100,
			"deducted_amount": 0,
			"outstanding_amount": 100,
			"deduction_status": loan_module.INSTALLMENT_SCHEDULED,
			"payroll_reference": None,
			"payroll_deducted_amount": 0,
			"additional_salary": "HR-ADS-0001",
		})

		with patch.object(loan_module, "_get_locked_installment_state", return_value=booked):
			with self.assertRaises(frappe.ValidationError):
				loan_module.apply_payroll_loan_deductions(payroll_doc)

	def test_get_due_loan_deduction_hides_booked_instalments_from_monthly_payroll(self):
		"""Monthly Payroll must never even be OFFERED an instalment a payslip owns."""
		captured = {}

		def fake_sql(query, values=None, as_dict=False):
			captured["query"] = query
			return []

		with patch.object(loan_module.frappe.db, "sql", side_effect=fake_sql):
			loan_module.get_due_loan_deduction("EMP-0001", 9, 2026)

		self.assertIn("additional_salary IS NULL", captured["query"])
		self.assertIn("'Pending', 'Deferred'", captured["query"])

	def test_arrears_are_booked_into_the_run_being_prepared_not_a_dead_period(self):
		"""An instalment that fell due in a period that has already run has to be moved
		forward, or no Salary Slip will ever look for it and it is never recovered."""
		state = frappe._dict({
			"installment_number": 3,
			"due_date": date(2026, 4, 1),
			"outstanding_amount": 300,
			"installment_amount": 300,
		})
		employee = frappe._dict({"status": "Active", "date_of_joining": date(2026, 6, 1), "relieving_date": None})
		loan = frappe._dict({"employee": "EMP-0001"})

		# Booked on its own due date it precedes the joining date and is refused...
		with patch.object(loan_module.frappe.db, "exists", return_value=True):
			on_due_date = loan_module._installment_blocker(loan, state, employee, "BHD")
			in_current_period = loan_module._installment_blocker(
				loan, state, employee, "BHD", payroll_date=date(2026, 9, 1)
			)

		self.assertIn("before the employee joined", on_due_date)
		self.assertEqual(in_current_period, "")

	def test_an_instalment_for_a_relieved_employee_is_refused_not_booked(self):
		state = frappe._dict({
			"installment_number": 1,
			"due_date": date(2026, 9, 5),
			"outstanding_amount": 100,
			"installment_amount": 100,
		})
		employee = frappe._dict({
			"status": "Active",
			"date_of_joining": date(2020, 1, 1),
			"relieving_date": date(2026, 8, 31),
		})

		reason = loan_module._installment_blocker(frappe._dict({"employee": "EMP-1"}), state, employee, "BHD")

		self.assertIn("Full and Final Statement", reason)

	def test_an_employee_with_no_salary_structure_is_refused_with_a_readable_reason(self):
		state = frappe._dict({
			"installment_number": 1,
			"due_date": date(2026, 9, 5),
			"outstanding_amount": 100,
			"installment_amount": 100,
		})
		employee = frappe._dict({"status": "Active", "date_of_joining": date(2020, 1, 1), "relieving_date": None})

		reason = loan_module._installment_blocker(frappe._dict({"employee": "EMP-1"}), state, employee, "")

		self.assertIn("Salary Structure", reason)

	def test_cancelling_a_booking_frees_the_instalment_but_never_a_paid_one(self):
		freed = []

		def fake_set_value(doctype, name, values, update_modified=True):
			freed.append((name, values))

		rows = [
			frappe._dict({"name": "INST-1", "parent": "LOAN-1", "deduction_status": "Scheduled"}),
			frappe._dict({"name": "INST-2", "parent": "LOAN-1", "deduction_status": "Deducted"}),
		]
		with patch.object(loan_module.frappe, "get_all", return_value=rows), patch.object(
			loan_module.frappe.db, "set_value", side_effect=fake_set_value
		):
			loan_module.release_installment_for_additional_salary("HR-ADS-0001")

		self.assertEqual(len(freed), 1)
		self.assertEqual(freed[0][0], "INST-1")
		self.assertEqual(freed[0][1]["deduction_status"], loan_module.INSTALLMENT_PENDING)
		self.assertIsNone(freed[0][1]["additional_salary"])

	def test_only_deduction_rows_raised_from_a_booking_are_read_back_off_a_payslip(self):
		"""The link is `Salary Detail.additional_salary`, which hrms writes itself
		(salary_slip.py update_component_row) - never a date-and-amount guess."""
		slip = frappe._dict({
			"name": "SS-1",
			"deductions": [
				frappe._dict({"salary_component": "Loan Repayment", "amount": 100, "additional_salary": "HR-ADS-1"}),
				frappe._dict({"salary_component": "GOSI", "amount": 35, "additional_salary": None}),
			],
		})
		with patch.object(
			loan_module.frappe,
			"get_all",
			return_value=[frappe._dict({"name": "INST-1", "parent": "LOAN-1", "additional_salary": "HR-ADS-1"})],
		):
			amounts = loan_module._loan_installments_on_salary_slip(slip)

		self.assertEqual(amounts, {"INST-1": 100})
