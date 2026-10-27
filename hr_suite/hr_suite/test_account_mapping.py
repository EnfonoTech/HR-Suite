"""The account mapping is per company, and a useless row is refused rather than ignored.

These assert the END STATE a payroll depends on: that a mapping resolves for the company
it was written for and for no other, and that a row which could never post is rejected on
save instead of being silently skipped when a Journal Entry is built.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.utils import (
	ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE,
	ACCOUNT_PURPOSE_LEAVE_SALARY_PAYABLE,
	ACCOUNT_PURPOSE_SETTLEMENT_ADVANCE,
	get_mapped_account,
)


def _an_account(company, root_type):
	return frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 0},
		"name",
	)


class TestAccountMappingIsPerCompany(FrappeTestCase):
	def setUp(self):
		self.settings = frappe.get_doc("Hr Suite Settings")
		self.original = [r.as_dict() for r in (self.settings.get("hr_account_mappings") or [])]

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_cache(doctype="Hr Suite Settings")

	def test_the_legacy_global_fields_are_gone(self):
		meta = frappe.get_meta("Hr Suite Settings")
		for gone in (
			"leave_salary_expense_account",
			"leave_salary_payable_account",
			"settlement_advance_account",
		):
			self.assertIsNone(
				meta.get_field(gone),
				f"{gone} is still on Hr Suite Settings — a single global account cannot "
				f"serve a site with more than one company.",
			)
		self.assertIsNotNone(meta.get_field("hr_account_mappings"))

	def test_a_mapping_resolves_only_for_its_own_company(self):
		companies = frappe.get_all("Company", pluck="name", limit=2)
		if len(companies) < 2:
			self.skipTest("Needs two companies to prove the mapping is company-scoped")

        # Two companies, an expense account in the first, a mapping for the first only.
		owner, other = companies[0], companies[1]
		account = _an_account(owner, "Expense")
		if not account:
			self.skipTest(f"No postable expense account in {owner}")

		self.settings.set("hr_account_mappings", [])
		self.settings.append("hr_account_mappings", {
			"company": owner,
			"purpose": ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE,
			"account": account,
		})
		self.settings.flags.ignore_permissions = True
		self.settings.save()
		frappe.clear_cache(doctype="Hr Suite Settings")

		self.assertEqual(
			get_mapped_account(owner, ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE, "Expense"), account
		)
		self.assertEqual(
			get_mapped_account(other, ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE, "Expense"), "",
			"A mapping written for one company must not answer for another — that is the "
			"whole reason this stopped being a single global field.",
		)

	def test_wrong_root_type_is_refused_on_save(self):
		company = frappe.get_all("Company", pluck="name", limit=1)
		if not company:
			self.skipTest("No company on this site")
		company = company[0]
		asset = _an_account(company, "Asset")
		if not asset:
			self.skipTest(f"No postable asset account in {company}")

		self.settings.set("hr_account_mappings", [])
		self.settings.append("hr_account_mappings", {
			"company": company,
			# An asset account cannot be the leave salary EXPENSE.
			"purpose": ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE,
			"account": asset,
		})
		self.settings.flags.ignore_permissions = True
		with self.assertRaises(frappe.ValidationError):
			self.settings.save()

	def test_two_rows_for_the_same_company_and_purpose_are_refused(self):
		company = frappe.get_all("Company", pluck="name", limit=1)
		if not company:
			self.skipTest("No company on this site")
		company = company[0]
		account = _an_account(company, "Asset")
		if not account:
			self.skipTest(f"No postable asset account in {company}")

		self.settings.set("hr_account_mappings", [])
		for _i in range(2):
			self.settings.append("hr_account_mappings", {
				"company": company,
				"purpose": ACCOUNT_PURPOSE_SETTLEMENT_ADVANCE,
				"account": account,
			})
		self.settings.flags.ignore_permissions = True
		with self.assertRaises(frappe.ValidationError):
			self.settings.save()

	def test_no_mapping_resolves_to_empty_not_an_error(self):
		self.settings.set("hr_account_mappings", [])
		self.settings.flags.ignore_permissions = True
		self.settings.save()
		frappe.clear_cache(doctype="Hr Suite Settings")

		company = frappe.get_all("Company", pluck="name", limit=1)
		if not company:
			self.skipTest("No company on this site")

		self.assertEqual(
			get_mapped_account(company[0], ACCOUNT_PURPOSE_LEAVE_SALARY_PAYABLE, "Liability"), "",
			"An unmapped purpose must return empty so the caller's fallback runs; raising "
			"here would break a disbursement mid-submit.",
		)


class TestPayableAndCompanyChecksOnSave(FrappeTestCase):
	"""Issue B: the mistakes that used to surface only at settlement submit are refused when the settings are saved."""

	def setUp(self):
		self.settings = frappe.get_doc("Hr Suite Settings")
		self.settings.flags.ignore_permissions = True
		self.company = frappe.get_all("Company", pluck="name", limit=1)
		if not self.company:
			self.skipTest("Needs a company")
		self.company = self.company[0]
		# Start from empty tables, so a row already on the site cannot be what a test sees refused.
		self.settings.set("hr_account_mappings", [])
		self.settings.set("statutory_deduction_accounts", [])

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_cache(doctype="Hr Suite Settings")

	def _liability(self, payable: bool):
		filters = {"company": self.company, "root_type": "Liability", "is_group": 0}
		filters["account_type"] = "Payable" if payable else ["not in", ["Payable", "Receivable"]]
		return frappe.db.get_value("Account", filters, "name")

	def test_every_employee_tagged_purpose_needs_a_payable_account(self):
		from hr_suite.hr_suite.utils import PAYABLE_PURPOSES

		account = self._liability(payable=False)
		if not account:
			self.skipTest("No liability account without an account type")
		for purpose in sorted(PAYABLE_PURPOSES):
			# A fresh copy each time: a refused save leaves the in-memory timestamp ahead of the database.
			settings = frappe.get_doc("Hr Suite Settings")
			settings.flags.ignore_permissions = True
			settings.set("statutory_deduction_accounts", [])
			settings.set("hr_account_mappings", [])
			settings.append("hr_account_mappings", {"company": self.company, "purpose": purpose, "account": account})
			with self.assertRaises(frappe.ValidationError, msg=purpose) as caught:
				settings.save()
			self.assertIn("Payable", str(caught.exception))

	def test_a_payable_account_is_accepted_for_the_new_purposes(self):
		from hr_suite.hr_suite.utils import ACCOUNT_PURPOSE_BONUS_PAYABLE, ACCOUNT_PURPOSE_GRATUITY_PROVISION

		account = self._liability(payable=True)
		if not account:
			self.skipTest("No payable account")
		self.settings.set("hr_account_mappings", [])
		for purpose in (ACCOUNT_PURPOSE_BONUS_PAYABLE, ACCOUNT_PURPOSE_GRATUITY_PROVISION):
			self.settings.append("hr_account_mappings", {"company": self.company, "purpose": purpose, "account": account})
		self.settings.save()

	def test_a_new_expense_purpose_refuses_a_liability(self):
		from hr_suite.hr_suite.utils import ACCOUNT_PURPOSE_AIR_TICKET_EXPENSE

		account = self._liability(payable=True)
		if not account:
			self.skipTest("No payable account")
		self.settings.set("hr_account_mappings", [])
		self.settings.append(
			"hr_account_mappings", {"company": self.company, "purpose": ACCOUNT_PURPOSE_AIR_TICKET_EXPENSE, "account": account}
		)
		self.assertRaises(frappe.ValidationError, self.settings.save)

	def test_a_deduction_account_from_another_company_is_refused(self):
		companies = frappe.get_all("Company", pluck="name", limit=2)
		if len(companies) < 2:
			self.skipTest("Needs two companies")
		foreign = _an_account(companies[1], "Liability")
		if not foreign:
			self.skipTest(f"No liability account in {companies[1]}")
		self.settings.set("statutory_deduction_accounts", [])
		self.settings.append("statutory_deduction_accounts", {"company": companies[0], "account": foreign})
		self.assertRaises(frappe.ValidationError, self.settings.save)
