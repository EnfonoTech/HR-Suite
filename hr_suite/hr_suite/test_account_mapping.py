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
