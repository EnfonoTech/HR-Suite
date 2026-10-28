"""Monthly gratuity provision and finalisation (SFT reply, section 10; team document 28 Oct 2026).

Expected figures are worked by hand from the spec: monthly = Basic / 30 x days per year / 12, KSA 15 days a
year for the first five years and 30 after (Country Config slabs), never read back from the code under test.
"""

import frappe
from frappe.utils import flt

from hr_suite.hr_suite import gratuity_provision as gp
from hr_suite.hr_suite.policy import get_country_policy
from hr_suite.hr_suite.test_leave_accrual_ledger import COMPANY
from hr_suite.hr_suite.test_leave_salary_settlement import SettlementTestBase


class TestGratuityProvision(SettlementTestBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		parent = frappe.db.get_value(
			"Account", {"company": COMPANY, "root_type": "Liability", "is_group": 1, "account_type": ["in", ["Payable", ""]]}, "name"
		)
		cls.gratuity_payable = cls.account("HRS Gratuity Payable", parent, "Payable")
		cls.gratuity_provision = cls.account("HRS Gratuity Provision", parent, "Payable")
		cls.plain_liability = cls.account("HRS Gratuity Plain", parent, "")
		cls.map_gratuity(cls.gratuity_provision)
		cls.configure("2026-01-01", "Gratuity Payable")

	@staticmethod
	def account(name, parent, account_type):
		existing = frappe.db.get_value("Account", {"company": COMPANY, "account_name": name}, "name")
		return existing or frappe.get_doc(
			doctype="Account", account_name=name, company=COMPANY, parent_account=parent, account_type=account_type,
			root_type="Liability",
		).insert(ignore_permissions=True).name

	@classmethod
	def map_gratuity(cls, provision):
		settings = frappe.get_doc("Hr Suite Settings")
		purposes = ("Gratuity Expense", "Gratuity Payable", "Gratuity Provision")
		settings.set("hr_account_mappings", [r for r in settings.get("hr_account_mappings") or [] if r.company != COMPANY or r.purpose not in purposes])
		for purpose, account in zip(purposes, (cls.expense_account, cls.gratuity_payable, provision)):
			settings.append("hr_account_mappings", {"company": COMPANY, "purpose": purpose, "account": account})
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Hr Suite Settings", "Hr Suite Settings")

	@staticmethod
	def configure(start, credit):
		for field, value in (("gratuity_provision_start_date", start), ("gratuity_monthly_credit", credit), ("gratuity_auto_post", 0)):
			frappe.db.set_single_value("Hr Suite Settings", field, value)

	def rows(self, emp, source=None):
		filters = {"employee": emp}
		if source:
			filters["source"] = source
		return frappe.get_all("Gratuity Accrual", filters=filters, fields=["name", "amount", "journal_entry", "days_per_year", "source"])

	# ── the figure ──

	def test_days_per_year_follow_the_slabs(self):
		policy = get_country_policy("SA")
		self.assertEqual(gp.days_per_year(policy, 4.9), 15.0)  # half a month a year
		self.assertEqual(gp.days_per_year(policy, 5.0), 30.0)  # a month a year from the sixth year

	def test_monthly_amount_and_a_part_month(self):
		policy = get_country_policy("SA")
		# 4000 / 30 x 30 / 12 = 333.33 after five years
		self.assertEqual(gp.monthly_amount(policy, 4000, "2020-01-01", "2026-10-01", "2026-10-31").amount, 333.33)
		# 4000 / 30 x 15 / 12 = 166.667 a month; joined 16 Oct: 16 of 31 days = 86.02
		self.assertEqual(gp.monthly_amount(policy, 4000, "2026-10-16", "2026-10-01", "2026-10-31").amount, 86.02)

	# ── posting a month ──

	def test_a_month_posts_once_per_employee_tagged_to_the_employee(self):
		emp = self.staff("GratMonthly", opening=0, ctc=4000)
		result = gp.post_month(COMPANY, "2026-10-31")
		rows = self.rows(emp, "Monthly")
		self.assertEqual([(r.amount, r.days_per_year) for r in rows], [(333.33, 30.0)])
		je = frappe.get_doc("Journal Entry", result["journal_entry"])
		mine = [a for a in je.accounts if a.party == emp]
		self.assertEqual([(a.account, flt(a.credit_in_account_currency)) for a in mine], [(self.gratuity_payable, 333.33)])
		self.assertTrue(any(a.account == self.expense_account and flt(a.debit_in_account_currency) == 333.33 for a in je.accounts))

		gp.post_month(COMPANY, "2026-10-15")  # same month again
		self.assertEqual(len(self.rows(emp, "Monthly")), 1)

		je.cancel()  # gives the month back
		self.assertEqual(self.rows(emp, "Monthly"), [])
		gp.post_month(COMPANY, "2026-10-31")
		self.assertEqual(len(self.rows(emp, "Monthly")), 1)

	def test_nothing_before_the_start_date(self):
		emp = self.staff("GratEarly", opening=0)
		gp.post_month(COMPANY, "2025-12-31")
		self.assertEqual(self.rows(emp), [])

	def test_the_credit_account_must_be_payable(self):
		# Hr Suite Settings refuses the mapping itself; the provision checks again, for a type changed later
		with self.assertRaises(frappe.ValidationError) as caught:
			self.map_gratuity(self.plain_liability)
		self.assertIn("Account Type is not Payable", str(caught.exception))
		frappe.db.set_value("Account", self.gratuity_provision, "account_type", "")
		self.addCleanup(frappe.db.set_value, "Account", self.gratuity_provision, "account_type", "Payable")
		frappe.clear_cache()
		self.configure("2026-01-01", "Gratuity Provision")
		self.addCleanup(self.configure, "2026-01-01", "Gratuity Payable")
		self.staff("GratPlain", opening=0)
		with self.assertRaises(frappe.ValidationError) as caught:
			gp.post_month(COMPANY, "2026-09-30")
		self.assertIn("Account Type is not Payable", str(caught.exception))

	# ── opening balance ──

	def test_one_opening_row_by_hand_and_nothing_else(self):
		emp = self.staff("GratOpening", opening=0)
		frappe.get_doc(doctype="Gratuity Accrual", employee=emp, source="Opening", posting_date="2025-12-31", amount=2500).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(doctype="Gratuity Accrual", employee=emp, source="Opening", posting_date="2025-12-31", amount=1).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(doctype="Gratuity Accrual", employee=emp, source="Monthly", posting_date="2026-01-31", amount=1).insert()
		self.assertEqual(gp.accrued_to_date(emp), 2500)

	# ── finalisation ──

	def finalise(self, emp, reason, relieving="2026-06-30"):
		frappe.db.set_value("Employee", emp, "relieving_date", relieving)
		doc = frappe.get_doc(doctype="Gratuity Finalisation", employee=emp, exit_reason=reason)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_resignation_reverses_the_excess_and_pays_through_an_advice(self):
		from hr_suite.hr_suite.gratuity import calculate_for_employee

		emp = self.staff("GratResign", opening=0, ctc=4000, joined="2023-01-01")
		frappe.get_doc(doctype="Gratuity Accrual", employee=emp, source="Opening", posting_date="2025-12-31", amount=6000).insert()
		final = flt(calculate_for_employee(emp, "2026-06-30", "Resignation").net_entitlement, 2)
		doc = self.finalise(emp, "Resignation")

		self.assertEqual((doc.accrued_to_date, doc.final_amount), (6000, final))
		self.assertLess(doc.difference, 0)  # 3.5 years: a third of the gratuity, less than provided
		je = frappe.get_doc("Journal Entry", doc.journal_entry)
		self.assertEqual(
			sorted((a.account, flt(a.debit_in_account_currency), flt(a.credit_in_account_currency), a.party or "") for a in je.accounts),
			sorted([(self.gratuity_payable, abs(doc.difference), 0.0, emp), (self.expense_account, 0.0, abs(doc.difference), "")]),
		)
		self.assertEqual(gp.accrued_to_date(emp), final)  # provided now equals what is paid
		from hr_suite.hr_suite.payment_advice import raise_for_document

		raise_for_document("Gratuity Finalisation", doc.name)  # what the job does after the submit commits
		doc.reload()
		advice = frappe.get_doc("HR Payment Advice", doc.payment_advice)
		self.assertEqual((advice.employee, flt(advice.total_amount)), (emp, final))

		from hr_suite.hr_suite.payment_advice import _gratuity_payment_entry

		entry = frappe.get_doc("Payment Entry", _gratuity_payment_entry(advice, doc.name)["payment_entry"])
		self.assertEqual((entry.party, entry.paid_to, flt(entry.paid_amount)), (emp, self.gratuity_payable, final))


	def test_provision_moves_to_payable_at_exit(self):
		self.configure("2026-01-01", "Gratuity Provision")
		self.addCleanup(self.configure, "2026-01-01", "Gratuity Payable")
		emp = self.staff("GratProvision", opening=0, ctc=4000, joined="2020-01-01")
		doc = self.finalise(emp, "Termination")
		je = frappe.get_doc("Journal Entry", doc.journal_entry)
		moves = {(a.account, flt(a.debit_in_account_currency), flt(a.credit_in_account_currency)) for a in je.accounts if a.party == emp}
		self.assertIn((self.gratuity_provision, doc.final_amount, 0.0), moves)
		self.assertIn((self.gratuity_payable, 0.0, doc.final_amount), moves)

	def test_a_second_finalisation_is_refused(self):
		emp = self.staff("GratTwice", opening=0, joined="2020-01-01")
		self.finalise(emp, "Termination")
		with self.assertRaises(frappe.ValidationError):
			self.finalise(emp, "Termination")

	def test_gratuity_is_not_paid_on_the_payslip(self):
		with self.assertRaises(frappe.ValidationError):
			gp.refuse_pay_via_salary_slip(frappe._dict(pay_via_salary_slip=1))
		gp.refuse_pay_via_salary_slip(frappe._dict(pay_via_salary_slip=0))
