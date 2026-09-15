# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Let a payroll run finish when the accrual entry needs approval.

`hrms` builds the accrual Journal Entry and submits it in the same breath —
``submit_journal_entry=True`` is hardcoded in ``make_accrual_jv_entry``, with no
Payroll Settings flag to turn it off.

When an approval workflow covers Journal Entry (permission_manager's "Journal
Entry Approval" here), that submit is refused:

    Journal Entry ACC-JV-… is at Draft and cannot be submitted directly —
    it still needs approval.

The refusal raises inside ``submit_salary_slips_for_employees``, so the whole run
aborts: the Payroll Entry is marked Failed and **the payslips stay in draft**. No
payslips, no GL, no loan recovery — from a control that was only ever meant to
hold one journal for review.

So when a workflow covers Journal Entry we create the accrual entry and leave it
in Draft for its approver, which is what the workflow is for, and let the payroll
run complete. The entry still has to be approved before it reaches the ledger.
"""

import frappe
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry


def journal_entry_needs_approval() -> bool:
	"""True when an active approval workflow covers Journal Entry.

	Only permission_manager's PM Workflow is consulted; a site without it keeps
	stock hrms behaviour, so this override is inert where there is nothing to
	approve against.
	"""
	if not frappe.db.exists("DocType", "PM Workflow"):
		return False

	return bool(
		frappe.db.exists("PM Workflow", {"document_type": "Journal Entry", "is_active": 1})
	)


class HRSuitePayrollEntry(PayrollEntry):
	def make_journal_entry(self, *args, **kwargs):
		if kwargs.get("submit_journal_entry") and journal_entry_needs_approval():
			kwargs["submit_journal_entry"] = False
			frappe.msgprint(
				frappe._(
					"The accrual Journal Entry has been left in Draft because Journal Entries "
					"need approval on this site. Approve it to post the payroll to the ledger."
				),
				title=frappe._("Journal Entry awaiting approval"),
				indicator="orange",
			)

		return super().make_journal_entry(*args, **kwargs)
