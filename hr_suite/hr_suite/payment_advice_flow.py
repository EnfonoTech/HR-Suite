"""Two-level approval for the HR Payment Advice, and Expense Claim routing through it.

Every payment to an employee outside payroll passes HR Payment Advice before Finance sees
it. HR records what is claimed and what it sanctions (never more than claimed); a level 1
and, where configured, a level 2 approver sign it off in the system; the final approval
submits it and it reaches Finance's queue. A rejection returns it to the claimant with the
reason and nothing reaches Finance.

    Draft -> Pending Approval (level 1 -> level 2) -> Approved -> Sent to Finance -> Paid
                       \\-> Rejected (back to HR, may be resubmitted)

Approvers come from Hr Suite Settings, per company. A company with none configured keeps the
older behaviour: submitting the advice is the approval. HR does no accounting; Finance books
and pays from the approved advice.

Nothing here builds SQL from strings. Every .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

ADVICE = "HR Payment Advice"
SETTINGS = "Hr Suite Settings"
PENDING, REJECTED, APPROVED, SENT, PAID = "Pending Approval", "Rejected", "Approved", "Sent to Finance", "Paid"


# ── configuration ─────────────────────────────────────────────────────────────


def get_approvers(company):
	"""(level 1 user, level 2 user) for a company. A company's own row beats a blank-company row."""
	rows = frappe.get_all(
		"Payment Advice Approver",
		filters={"parent": SETTINGS, "parenttype": SETTINGS},
		fields=["company", "level", "user"],
		order_by="idx asc",
	)
	found = {}
	for row in rows:
		if row.company and row.company != company:
			continue
		level = cint(row.level)
		if level not in found or (row.company and not found[level][1]):
			found[level] = (row.user, row.company)
	return (found.get(1, (None,))[0], found.get(2, (None,))[0])


def approvals_configured(company) -> bool:
	return bool(get_approvers(company)[0])


# ── actions ───────────────────────────────────────────────────────────────────


def _load(name, docstatus):
	doc = frappe.get_doc(ADVICE, name)
	if doc.docstatus != docstatus:
		frappe.throw(
			_("{0} is {1}, so this action is not available.").format(
				doc.name, _("submitted") if doc.docstatus == 1 else _("cancelled") if doc.docstatus == 2 else _("a draft")
			),
			title=_("Wrong State"),
		)
	return doc


def _assign(doc, user, description):
	try:
		from frappe.desk.form.assign_to import add

		add({"assign_to": [user], "doctype": ADVICE, "name": doc.name, "description": description, "notify": 0})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: could not assign payment advice " + doc.name)


def _clear_assignments(doc):
	try:
		from frappe.desk.form.assign_to import clear

		clear(ADVICE, doc.name, ignore_permissions=True)
	except Exception:
		pass


@frappe.whitelist()
def submit_for_approval(name):
	"""HR has reviewed the lines and sanctioned the amounts: send it to the level 1 approver."""
	doc = _load(name, 0)
	frappe.has_permission(ADVICE, "write", doc=doc, throw=True)

	if not approvals_configured(doc.company):
		frappe.throw(
			_("No approver is configured for {0}. Add one in Hr Suite Settings > HR Payment Advice Approval, "
			  "or submit the advice directly.").format(doc.company),
			title=_("No Approver"),
		)
	if doc.status not in ("Draft", REJECTED):
		frappe.throw(_("Only a draft or rejected advice can be sent for approval."), title=_("Wrong State"))
	if flt(doc.total_amount) <= 0:
		frappe.throw(_("Sanction at least one line before sending it for approval."), title=_("Nothing Sanctioned"))

	l1, l2 = get_approvers(doc.company)
	doc.approver_l1 = doc.approver_l1 or l1
	doc.approver_l2 = doc.approver_l2 or l2
	doc.flags.approval_action = True
	doc.status = PENDING
	doc.approval_level = 1
	doc.rejection_reason = doc.rejected_by = doc.rejected_on = None
	doc.l1_approved_by = doc.l1_approved_on = doc.l2_approved_by = doc.l2_approved_on = None
	doc.save()

	_assign(doc, doc.approver_l1, _("Approve payment advice {0} for {1}").format(doc.name, doc.employee_name))
	return {"name": doc.name, "status": doc.status, "awaiting": doc.approver_l1}


@frappe.whitelist()
def approve(name):
	"""The approver for the level it is waiting at signs it; the last signature submits it."""
	doc = _load(name, 0)
	frappe.has_permission(ADVICE, "read", doc=doc, throw=True)
	if doc.status != PENDING:
		frappe.throw(_("{0} is not waiting for approval.").format(doc.name), title=_("Wrong State"))

	level = cint(doc.approval_level) or 1
	expected = doc.approver_l1 if level == 1 else doc.approver_l2
	if frappe.session.user != expected:
		frappe.throw(
			_("Level {0} of this advice is waiting for {1}.").format(level, expected or _("an approver")),
			title=_("Not Your Approval"),
		)
	if level == 2 and frappe.session.user == doc.l1_approved_by:
		frappe.throw(_("The same person cannot give both approvals."), title=_("Second Approver Needed"))

	doc.flags.approval_action = True
	# The approver is checked against the advice above; they need not hold write rights on it.
	doc.flags.ignore_permissions = True
	now = now_datetime()
	if level == 1:
		doc.l1_approved_by, doc.l1_approved_on = frappe.session.user, now
	else:
		doc.l2_approved_by, doc.l2_approved_on = frappe.session.user, now

	_clear_assignments(doc)
	if level == 1 and doc.approver_l2:
		doc.approval_level = 2
		doc.save()
		_assign(doc, doc.approver_l2, _("Approve payment advice {0} for {1}").format(doc.name, doc.employee_name))
		return {"name": doc.name, "status": doc.status, "awaiting": doc.approver_l2}

	doc.approval_level = 0
	doc.flags.approval_complete = True
	# Approving IS the submission, so the approver needs no submit right either.
	doc.save()
	doc.submit()
	return {"name": doc.name, "status": frappe.db.get_value(ADVICE, doc.name, "status"), "awaiting": None}


@frappe.whitelist()
def reject(name, reason):
	"""Return the advice to the claimant, with the reason. Nothing reaches Finance."""
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Say why it is being rejected."), title=_("Reason Required"))

	doc = _load(name, 0)
	if doc.status != PENDING:
		frappe.throw(_("{0} is not waiting for approval.").format(doc.name), title=_("Wrong State"))
	level = cint(doc.approval_level) or 1
	expected = doc.approver_l1 if level == 1 else doc.approver_l2
	if frappe.session.user != expected:
		frappe.throw(
			_("Level {0} of this advice is waiting for {1}.").format(level, expected or _("an approver")),
			title=_("Not Your Approval"),
		)

	doc.flags.approval_action = True
	doc.status = REJECTED
	doc.approval_level = 0
	doc.rejection_reason, doc.rejected_by, doc.rejected_on = reason, frappe.session.user, now_datetime()
	doc.flags.ignore_permissions = True
	doc.save()
	_clear_assignments(doc)
	doc.add_comment("Comment", _("Rejected by {0}: {1}").format(frappe.session.user, reason))
	_notify_claimant(
		doc,
		_("Payment advice {0} was rejected").format(doc.name),
		_("Your payment request {0} was rejected by {1}.<br><br><b>Reason:</b> {2}").format(
			doc.name, frappe.session.user, frappe.utils.escape_html(reason)
		),
	)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def recall(name):
	"""HR takes an advice back from the approver to correct it."""
	doc = _load(name, 0)
	frappe.has_permission(ADVICE, "write", doc=doc, throw=True)
	if doc.status != PENDING:
		frappe.throw(_("Only an advice that is waiting for approval can be recalled."), title=_("Wrong State"))
	doc.flags.approval_action = True
	doc.status = "Draft"
	doc.approval_level = 0
	doc.l1_approved_by = doc.l1_approved_on = doc.l2_approved_by = doc.l2_approved_on = None
	doc.save()
	_clear_assignments(doc)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def send_to_finance(name):
	"""Release an approved advice to Finance's queue."""
	doc = _load(name, 1)
	frappe.has_permission(ADVICE, "write", doc=doc, throw=True)
	if doc.status != APPROVED:
		frappe.throw(_("Only an approved advice can be sent to Finance."), title=_("Wrong State"))
	doc.db_set({"status": SENT, "sent_to_finance_on": now_datetime()})
	return {"name": doc.name, "status": SENT}


def _notify_claimant(doc, subject, message):
	"""Best effort: a mail that cannot be sent never undoes the rejection."""
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if not user:
		return
	try:
		frappe.sendmail(
			recipients=[user], subject=subject, message=message, reference_doctype=ADVICE, reference_name=doc.name
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: rejection mail failed for " + doc.name)


# ── Expense Claim routing ─────────────────────────────────────────────────────


def routing_enabled() -> bool:
	return bool(cint(frappe.db.get_single_value(SETTINGS, "route_expense_claims_via_advice")))


def route_expense_claim(doc, method=None):
	"""on_submit of an Expense Claim: raise the advice that stands between the claim and payment."""
	if not routing_enabled():
		return

	from hr_suite.hr_suite.payment_advice import create_payment_advice_for, get_payment_advice_for

	if get_payment_advice_for("Expense Claim", doc.name):
		return
	claimed = flt(doc.get("total_claimed_amount"))
	if claimed <= 0:
		return

	create_payment_advice_for(
		doc,
		lines=[
			{
				"amount": claimed,
				"sanctioned_amount": flt(doc.get("total_sanctioned_amount")),
				"description": _("Expense claim {0}").format(doc.name),
			}
		],
		description=_("Expense claim {0}").format(doc.name),
	)


def withdraw_expense_claim_advice(doc, method=None):
	"""on_cancel of an Expense Claim: the claim is gone, so is its advice - unless it was paid."""
	from hr_suite.hr_suite.payment_advice import get_payment_advice_for

	name = get_payment_advice_for("Expense Claim", doc.name)
	if not name:
		return
	advice = frappe.get_doc(ADVICE, name)
	if advice.status == PAID:
		frappe.throw(
			_("Payment Advice {0} was paid on {1}. Reverse that payment in the accounts before cancelling the claim.").format(
				name, advice.payment_date
			),
			title=_("Already Paid"),
		)
	if advice.docstatus == 0:
		frappe.delete_doc(ADVICE, name, force=True, ignore_permissions=True)
	elif advice.docstatus == 1:
		advice.flags.ignore_permissions = True
		advice.cancel()


def guard_expense_claim_payment(doc, method=None):
	"""validate on Payment Entry: a claim with an advice is paid only once the advice is approved."""
	if not routing_enabled():
		return
	from hr_suite.hr_suite.payment_advice import get_payment_advice_for

	for row in doc.get("references") or []:
		if row.reference_doctype != "Expense Claim":
			continue
		name = get_payment_advice_for("Expense Claim", row.reference_name)
		if not name:
			continue  # a claim submitted before routing was switched on
		status = frappe.db.get_value(ADVICE, name, "status")
		if status not in (APPROVED, SENT, PAID):
			frappe.throw(
				_("Expense Claim {0} cannot be paid yet: its Payment Advice {1} is {2}. "
				  "Finance pays a claim once HR has approved the advice.").format(row.reference_name, name, _(status)),
				title=_("Payment Advice Not Approved"),
			)


def on_expense_claim_payment(doc, method=None):
	"""on_submit / on_cancel of a Payment Entry against a claim: the advice turns Paid, or back."""
	if not routing_enabled():
		return
	from hr_suite.hr_suite.payment_advice import _record_payment, _sync_paid_state, get_payment_advice_for

	for row in doc.get("references") or []:
		if row.reference_doctype != "Expense Claim":
			continue
		name = get_payment_advice_for("Expense Claim", row.reference_name)
		if not name:
			continue
		advice = frappe.get_doc(ADVICE, name)
		if doc.docstatus == 1 and advice.docstatus == 1 and advice.status in (APPROVED, SENT):
			_record_payment(advice, doc.name, doc.posting_date, doc.get("bank_account"))
		elif doc.docstatus == 2 and advice.status == PAID and advice.payment_reference == doc.name:
			advice.db_set(
				{"status": SENT, "payment_reference": None, "payment_date": None, "amount_paid": 0, "paid_by": None}
			)
			advice.status = SENT
			_sync_paid_state(advice)
