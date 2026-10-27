"""HR changes the dates of an approved leave that is not settled yet; the leave goes back for approval.

SFT reply, section 11 (27 Oct 2026):
    Pending approval           HR may edit (the workflow's Open state)
    Approved, not yet settled  HR may change the dates; the leave goes back for approval   <- this module
    Leave salary settled       blocked: cancel the settlement first (leave_application_rules.before_cancel)

An approved leave is a submitted document, so its dates cannot be edited in place. This does what HR would
otherwise do by hand, in one transaction: cancel the approved application (HRMS reverses its leave ledger
entry and attendance, HR Suite its unpaid-leave deductions) and create the amendment (`<name>-1`) with the
new dates, status Open, for the same Leave Approver. If the new dates fail any check (balance, overlap,
minimum service) nothing is cancelled.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate

DOCTYPE = "Leave Application"
SAVEPOINT = "hrs_change_leave_dates"
ROLE = "HR Manager"  # it holds the workflow's Cancel transition, which the cancel below goes through


@frappe.whitelist()
def change_approved_leave_dates(application, from_date, to_date, half_day=0, half_day_date=None, reason=None):
	"""Cancel `application` and return the name of its amendment with the new dates, waiting for approval."""
	frappe.only_for(ROLE)
	frappe.has_permission(DOCTYPE, "cancel", doc=application, throw=True)
	doc = frappe.get_doc(DOCTYPE, application)
	from_date, to_date = getdate(from_date), getdate(to_date)

	if doc.docstatus != 1 or doc.status != "Approved":
		frappe.throw(
			_("Only an approved leave can have its dates changed here. {0} is {1}.").format(doc.name, _(doc.status)),
			title=_("Not An Approved Leave"),
		)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."), title=_("Invalid Dates"))
	half_day = cint(half_day)
	if (
		from_date == getdate(doc.from_date)
		and to_date == getdate(doc.to_date)
		and half_day == cint(doc.half_day)
		and (not half_day or getdate(half_day_date) == getdate(doc.half_day_date))
	):
		frappe.throw(_("The dates are the same as on {0}: nothing to change.").format(doc.name), title=_("No Change"))
	_refuse_if_settlement_exists(doc)

	# All or nothing, also when called outside a web request (console, tests): new dates that fail a check
	# (balance, overlap, minimum service) must not leave the approved leave cancelled.
	frappe.db.savepoint(SAVEPOINT)
	try:
		doc.cancel()  # before_cancel refuses a settled leave too; HRMS reverses the ledger entry and attendance
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0  # copy_doc keeps the cancelled docstatus
		amended.amended_from = doc.name
		amended.status = "Open"
		amended.from_date, amended.to_date = from_date, to_date
		amended.half_day = half_day
		amended.half_day_date = getdate(half_day_date) if half_day and half_day_date else None
		amended.unpaid_deduction_rows = ""  # booked again when the amendment is approved
		amended.insert()
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		raise

	note = _("Dates changed by {0} from {1} - {2} to {3} - {4}; back for approval as {5}.").format(
		frappe.session.user,
		formatdate(doc.from_date),
		formatdate(doc.to_date),
		formatdate(from_date),
		formatdate(to_date),
		amended.name,
	)
	if reason:
		note += " " + _("Reason: {0}").format(reason)
	doc.add_comment("Info", note)
	amended.add_comment("Info", note)
	return amended.name


def _refuse_if_settlement_exists(doc):
	"""A settled leave stays locked (section 11); a draft settlement priced the old dates and must go first."""
	rows = frappe.get_all(
		"Leave Salary Settlement",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		fields=["name", "docstatus"],
	)
	submitted = [r.name for r in rows if r.docstatus == 1]
	drafts = [r.name for r in rows if r.docstatus == 0]
	if submitted:
		frappe.throw(
			_("The leave salary for {0} is already settled ({1}). Cancel the settlement first: its Journal Entry "
			  "reverses, and Finance reverses any payment made against it. Then change the dates.").format(
				doc.name, ", ".join(submitted)
			),
			title=_("Leave Salary Already Settled"),
		)
	if drafts:
		frappe.throw(
			_("A draft Leave Salary Settlement ({0}) was made for the current dates of {1}. Delete it first, change "
			  "the dates, then make the settlement again from the new leave.").format(", ".join(drafts), doc.name),
			title=_("Draft Settlement Exists"),
		)
