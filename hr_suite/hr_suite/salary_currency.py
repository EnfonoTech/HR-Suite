"""Salary Structure currency follows the company.

HRMS leaves the currency of a Salary Structure to the user's default, so a Saudi company's
structure created by a user whose default is BHD came out in BHD, and every Salary Structure
Assignment, Salary Slip and leave salary figure inherited it. The Salary Structure form now
fills the company's currency (public/js/salary_structure.js); this is the same rule for a
structure built in code, plus a warning when someone then picks another currency.

A different currency is legitimate (a payroll payable account held in it), so this warns and
never refuses.
"""

import frappe
from frappe import _


def company_currency(company):
	return frappe.db.get_value("Company", company, "default_currency") if company else None


def default_from_company(doc, method=None):
	"""before_validate: a structure with no currency takes the company's."""
	if not doc.get("currency"):
		doc.currency = company_currency(doc.company)


def warn_if_not_company_currency(doc, method=None):
	expected = company_currency(doc.company)
	if expected and doc.currency and doc.currency != expected:
		frappe.msgprint(
			_("{0} is in {1}, but the default currency of {2} is {3}. Check this is intended: slips, leave salary "
			  "and settlements for these employees will be in {1}.").format(
				doc.name or _("This Salary Structure"), doc.currency, doc.company, expected
			),
			title=_("Currency Differs From The Company"),
			indicator="orange",
		)


def mismatches():
	"""[(Salary Structure, company, currency, company currency)] where they differ. For clean-up."""
	out = []
	for row in frappe.get_all("Salary Structure", fields=["name", "company", "currency", "docstatus"], filters={"docstatus": ["<", 2]}):
		expected = company_currency(row.company)
		if expected and row.currency != expected:
			out.append((row.name, row.company, row.currency, expected))
	return out
