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