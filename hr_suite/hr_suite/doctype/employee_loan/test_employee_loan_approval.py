from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.doctype.employee_loan import employee_loan as loan_module


test_ignore = ["Journal Entry"]


class TestEmployeeLoanApproval(FrappeTestCase):
	def test_legacy_submitted_loans_resolve_to_approved(self):
		self.assertEqual(
			loan_module.resolve_legacy_approval_status(1, "Draft", None),
			"Approved",
		)

	def test_legacy_disbursed_loans_resolve_to_disbursed(self):
		self.assertEqual(
			loan_module.resolve_legacy_approval_status(1, "Draft", "ACC-JV-2026-00001"),
			"Disbursed",
		)

	def test_submitted_disbursement_requires_ready_status(self):
		doc = frappe.get_doc(
			{
				"doctype": "Employee Loan",
				"employee": "HR-EMP-00001",
				"employee_name": "Demo Employee",
				"company": "amd",
				"loan_amount": 1000,
				"loan_date": "2026-03-01",
				"repayment_method": "Equal Installments",
				"installment_count": 4,
				"repayment_start_date": "2026-04-01",
				"approval_status": "Approved",
				"docstatus": 1,
			}
		)

		with self.assertRaises(frappe.ValidationError):
			doc.create_disbursement_journal_entry()

	def test_approve_disbursement_moves_status(self):
		doc = frappe.get_doc(
			{
				"doctype": "Employee Loan",
				"name": "LOAN-TEST-0001",
				"approval_status": "Approved",
				"docstatus": 1,
			}
		)

		with patch.object(loan_module, "_assert_loan_approver"), patch.object(loan_module.frappe, "get_doc", return_value=doc):
			result = loan_module.approve_loan_disbursement("LOAN-TEST-0001")

		self.assertEqual(result["approval_status"], "Ready for Disbursement")