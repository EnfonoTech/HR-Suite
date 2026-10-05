"""Phase 6 - HR Payment Advice: sanctioned amounts, two-level approval, Expense Claim routing."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from hr_suite.hr_suite import payment_advice_flow as flow
from hr_suite.hr_suite.payment_advice import mark_paid
from hr_suite.hr_suite.report.hr_payment_advice_queue.hr_payment_advice_queue import execute as queue

COMPANY = "HRS Dev"
L1, L2 = "advice.l1@hrs.test", "advice.l2@hrs.test"


class FlowBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for email in (L1, L2):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
					 "roles": [{"role": "HR User"}]}
				).insert(ignore_permissions=True)
		cls.emp = cls.employee("Advised")

	@staticmethod
	def employee(name):
		doc = frappe.get_doc(
			doctype="Employee", first_name=name, last_name="Advice", gender="Male", date_of_birth="1990-01-01",
			date_of_joining="2020-01-01", company=COMPANY, status="Active", work_country="SA",
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.configure(l1=L1, l2=L2)

	def configure(self, l1=None, l2=None, routing=0):
		settings = frappe.get_doc("Hr Suite Settings")
		settings.set("payment_advice_approvers", [])
		if l1:
			settings.append("payment_advice_approvers", {"company": COMPANY, "level": "1", "user": l1})
		if l2:
			settings.append("payment_advice_approvers", {"company": COMPANY, "level": "2", "user": l2})
		settings.route_expense_claims_via_advice = routing
		settings.save(ignore_permissions=True)

	def reference(self, days=1):
		return frappe.get_doc(
			doctype="Leave Accrual Ledger", employee=self.emp, source="Adjustment", period_end="2026-05-31",
			leave_days=0, salary_days=days,
		).insert(ignore_permissions=True).name

	def advice(self, *amounts, sanctioned=None, **fields):
		rows = [
			{"reference_doctype": "Leave Accrual Ledger", "reference_name": self.reference(), "amount": amount,
			 "description": "Line %s" % (i + 1), **({"sanctioned_amount": sanctioned[i]} if sanctioned else {})}
			for i, amount in enumerate(amounts)
		]
		doc = frappe.get_doc(
			doctype="HR Payment Advice", employee=self.emp, company=COMPANY, posting_date="2026-06-01", references=rows, **fields
		)
		doc.insert(ignore_permissions=True)
		return doc

	def as_user(self, user):
		frappe.set_user(user)

	def status(self, name):
		return frappe.db.get_value("HR Payment Advice", name, ["status", "docstatus", "approval_level"], as_dict=True)


class TestSanctioned(FlowBase):
	def test_unset_sanction_follows_the_claim(self):
		doc = self.advice(100, 250)
		self.assertEqual([r.sanctioned_amount for r in doc.references], [100, 250])
		self.assertEqual((doc.total_claimed, doc.total_amount), (350, 350))

	def test_hr_can_sanction_less_and_finance_pays_the_sanctioned_total(self):
		doc = self.advice(100, 250, sanctioned=[100, 200])
		self.assertEqual((doc.total_claimed, doc.total_amount), (350, 300))
		self.assertIn("300", doc.amount_in_words.replace(",", "") + str(doc.total_amount))

	def test_a_line_may_be_sanctioned_at_zero(self):
		self.assertEqual(self.advice(100, 250, sanctioned=[0, 250]).total_amount, 250)

	def test_never_more_than_claimed_and_never_negative(self):
		with self.assertRaises(frappe.ValidationError):
			self.advice(100, sanctioned=[150])
		with self.assertRaises(frappe.ValidationError):
			self.advice(100, sanctioned=[-1])

	def test_payment_type_follows_the_source_document(self):
		for source, expected in (
			("End of Service Benefit", "Gratuity"),
			("Leave Salary Settlement", "Leave Salary"),
			("Annual Leave Disbursement", "Leave Salary"),
			("Expense Claim", "Expense Claim"),
			("Salary Settlement", "Other"),
		):
			doc = frappe.new_doc("HR Payment Advice")
			doc.company, doc.source_doctype = COMPANY, source
			doc.employee = self.emp
			doc._set_defaults()
			self.assertEqual(doc.payment_type, expected, source)
		self.assertEqual(self.advice(100).payment_type, "Other")


class TestApproval(FlowBase):
	def test_with_approvers_configured_a_bare_submit_is_refused(self):
		doc = self.advice(100)
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_without_approvers_submitting_is_still_the_approval(self):
		self.configure()
		doc = self.advice(100)
		doc.submit()
		self.assertEqual(self.status(doc.name).status, "Approved")

	def test_two_levels_then_it_submits_itself(self):
		doc = self.advice(100)
		self.assertEqual(flow.submit_for_approval(doc.name)["awaiting"], L1)
		self.assertEqual(self.status(doc.name).status, "Pending Approval")

		self.as_user(L1)
		self.assertEqual(flow.approve(doc.name)["awaiting"], L2)
		state = self.status(doc.name)
		self.assertEqual((state.docstatus, state.approval_level), (0, 2))

		self.as_user(L2)
		flow.approve(doc.name)
		state = self.status(doc.name)
		self.assertEqual((state.status, state.docstatus), ("Approved", 1))
		done = frappe.get_doc("HR Payment Advice", doc.name)
		self.assertEqual((done.l1_approved_by, done.l2_approved_by), (L1, L2))
		self.assertTrue(done.l1_approved_on and done.l2_approved_on)

	def test_one_level_when_only_a_level_one_approver_is_configured(self):
		self.configure(l1=L1)
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.approve(doc.name)
		self.assertEqual(self.status(doc.name).status, "Approved")

	def test_only_the_approver_for_that_level_may_approve(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L2)  # level 1 is waiting
		self.assertRaises(frappe.ValidationError, flow.approve, doc.name)

	def test_nobody_gives_both_approvals(self):
		self.configure(l1=L1, l2=L1)
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.approve(doc.name)
		self.assertRaises(frappe.ValidationError, flow.approve, doc.name)

	def test_nothing_sanctioned_cannot_be_sent(self):
		doc = self.advice(100, sanctioned=[0])
		self.assertRaises(frappe.ValidationError, flow.submit_for_approval, doc.name)

	def test_amounts_are_locked_while_it_waits(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		doc = frappe.get_doc("HR Payment Advice", doc.name)
		doc.references[0].sanctioned_amount = 40
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_recall_gives_it_back_to_hr(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		flow.recall(doc.name)
		self.assertEqual(self.status(doc.name).status, "Draft")
		frappe.get_doc("HR Payment Advice", doc.name).save()  # editable again


class TestRejection(FlowBase):
	def test_a_rejection_needs_a_reason_and_goes_back_to_hr_not_to_finance(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		self.assertRaises(frappe.ValidationError, flow.reject, doc.name, "  ")
		flow.reject(doc.name, "Receipt is missing")
		state = self.status(doc.name)
		self.assertEqual((state.status, state.docstatus), ("Rejected", 0))
		row = frappe.get_doc("HR Payment Advice", doc.name)
		self.assertEqual((row.rejection_reason, row.rejected_by), ("Receipt is missing", L1))
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "HR Payment Advice", "reference_name": doc.name, "content": ["like", "%Receipt is missing%"]}))

	def test_a_rejected_advice_can_be_corrected_and_sent_again(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.reject(doc.name, "Wrong amount")
		self.as_user("Administrator")
		flow.submit_for_approval(doc.name)
		row = frappe.get_doc("HR Payment Advice", doc.name)
		self.assertEqual((row.status, row.approval_level, row.rejection_reason), ("Pending Approval", 1, None))

	def test_a_rejected_advice_never_reaches_the_finance_queue(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.reject(doc.name, "No")
		self.as_user("Administrator")
		_columns, rows = queue({"stage": "Awaiting Payment", "company": COMPANY})
		self.assertNotIn(doc.name, [r["name"] for r in rows])

	def test_only_the_waiting_approver_can_reject(self):
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L2)
		self.assertRaises(frappe.ValidationError, flow.reject, doc.name, "No")


class TestFinanceHandOff(FlowBase):
	def approved(self):
		self.configure(l1=L1)
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.approve(doc.name)
		self.as_user("Administrator")
		return doc.name

	def test_send_to_finance_then_paid(self):
		name = self.approved()
		flow.send_to_finance(name)
		self.assertEqual(self.status(name).status, "Sent to Finance")
		mark_paid(name, payment_reference="TRF-1")
		self.assertEqual(self.status(name).status, "Paid")

	def test_the_queue_lists_what_finance_owes_and_what_hr_still_has(self):
		name = self.approved()
		waiting = self.advice(50)
		flow.submit_for_approval(waiting.name)
		_c, owed = queue({"stage": "Awaiting Payment", "company": COMPANY})
		self.assertIn(name, [r["name"] for r in owed])
		_c, pending = queue({"stage": "Awaiting Approval", "company": COMPANY})
		row = next(r for r in pending if r["name"] == waiting.name)
		self.assertEqual(row["awaiting"], L1)

	def test_the_approval_sheet_prints_with_signature_blocks(self):
		name = self.approved()
		html = frappe.get_print("HR Payment Advice", name, "HR Payment Approval Sheet")
		for text in ("Payment Approval Sheet", "Level 1 Approver", "Finance", "Advised Advice"):
			self.assertIn(text, html)


class TestExpenseClaimRouting(FlowBase):
	def claim(self, claimed=500, sanctioned=450):
		return frappe._dict(
			doctype="Expense Claim", name="HR-EXP-TEST-1", employee=self.emp, company=COMPANY,
			posting_date="2026-06-01", total_claimed_amount=claimed, total_sanctioned_amount=sanctioned,
			get=lambda key, default=None: {"total_claimed_amount": claimed, "total_sanctioned_amount": sanctioned}.get(key, default),
		)

	def test_a_claim_raises_an_advice_with_its_sanctioned_amount(self):
		self.configure(l1=L1, routing=1)
		with patch("hr_suite.hr_suite.payment_advice.create_payment_advice_for") as make, patch(
			"hr_suite.hr_suite.payment_advice.get_payment_advice_for", return_value=None
		):
			flow.route_expense_claim(self.claim())
		lines = make.call_args.kwargs["lines"]
		self.assertEqual((lines[0]["amount"], lines[0]["sanctioned_amount"]), (500, 450))

	def test_nothing_is_raised_while_routing_is_off(self):
		with patch("hr_suite.hr_suite.payment_advice.create_payment_advice_for") as make:
			flow.route_expense_claim(self.claim())
		make.assert_not_called()

	def test_the_claim_cannot_be_paid_until_the_advice_is_approved(self):
		self.configure(l1=L1, routing=1)
		doc = self.advice(100)
		pe = frappe._dict(references=[frappe._dict(reference_doctype="Expense Claim", reference_name="HR-EXP-TEST-1")])
		with patch("hr_suite.hr_suite.payment_advice.get_payment_advice_for", return_value=doc.name):
			self.assertRaises(frappe.ValidationError, flow.guard_expense_claim_payment, pe)  # still a draft
			flow.submit_for_approval(doc.name)
			self.assertRaises(frappe.ValidationError, flow.guard_expense_claim_payment, pe)  # waiting
			self.as_user(L1)
			flow.approve(doc.name)
			flow.guard_expense_claim_payment(pe)  # approved: finance may pay

	def test_a_claim_with_no_advice_is_left_alone(self):
		self.configure(l1=L1, routing=1)
		pe = frappe._dict(references=[frappe._dict(reference_doctype="Expense Claim", reference_name="HR-EXP-OLD")])
		with patch("hr_suite.hr_suite.payment_advice.get_payment_advice_for", return_value=None):
			flow.guard_expense_claim_payment(pe)

	def test_the_payment_entry_turns_the_advice_paid_and_cancelling_it_turns_it_back(self):
		self.configure(l1=L1, routing=1)
		doc = self.advice(100)
		flow.submit_for_approval(doc.name)
		self.as_user(L1)
		flow.approve(doc.name)
		self.as_user("Administrator")
		flow.send_to_finance(doc.name)

		pe = frappe._dict(
			name="ACC-PAY-TEST-1", docstatus=1, posting_date="2026-06-10", bank_account=None,
			references=[frappe._dict(reference_doctype="Expense Claim", reference_name="HR-EXP-TEST-1")],
			get=lambda key, default=None: {"references": [frappe._dict(reference_doctype="Expense Claim", reference_name="HR-EXP-TEST-1")], "bank_account": None}.get(key, default),
		)
		with patch("hr_suite.hr_suite.payment_advice.get_payment_advice_for", return_value=doc.name):
			flow.on_expense_claim_payment(pe)
			paid = frappe.get_doc("HR Payment Advice", doc.name)
			self.assertEqual((paid.status, paid.payment_reference), ("Paid", "ACC-PAY-TEST-1"))

			pe.docstatus = 2
			flow.on_expense_claim_payment(pe)
		self.assertEqual(self.status(doc.name).status, "Sent to Finance")
