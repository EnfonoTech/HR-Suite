"""Put leave applications that were "approved" by editing Status back to Open, once.

Before the approval workflow let HR approve a leave they had created themselves, the testers set
Status to Approved by hand. Such a leave is not submitted: no Submit button, no leave ledger
entry, absent from the Leave Salary Settlement's list and from the sick-pay tiers. Re-opening it
puts the Approve / Reject buttons back. Only drafts reading Approved or Rejected are touched, and
only on a site where the Leave Application Approval workflow is active.
"""

import frappe

WORKFLOW = "Leave Application Approval"


def execute():
	if not frappe.db.exists("Workflow", {"name": WORKFLOW, "is_active": 1}):
		return
	for name in frappe.get_all(
		"Leave Application", filters={"docstatus": 0, "status": ["in", ["Approved", "Rejected"]]}, pluck="name"
	):
		frappe.db.set_value("Leave Application", name, "status", "Open", update_modified=False)
