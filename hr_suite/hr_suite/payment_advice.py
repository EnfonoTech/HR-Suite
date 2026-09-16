"""payment_advice.py — the one road from an HR money document to the finance desk.

Every HR document that owes an employee money outside the payroll run — an annual
leave disbursement, a final settlement, an end of service benefit, a loan payout —
calls :func:`create_payment_advice_for` on submit. Finance answers with
:func:`mark_paid`, and the source document hears back.

Two rules hold this together:

* **Raise once.** An HR document submitted, cancelled and amended, or whose
  ``on_submit`` runs twice through a hook and a controller, must not put in a
  second claim for the same money. Everything goes through
  :func:`get_payment_advice_for` first.
* **Never block the HR document.** Where an approval workflow covers HR Payment
  Advice, an automatic submit is refused, and that refusal would propagate out of
  the source document's ``on_submit`` and roll the whole thing back — which is how
  a payroll run died once before. The advice is left in Draft for its approver
  instead; the money is still recorded and still reaches the employee once signed.
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, nowdate

from hr_suite.hr_suite.utils import assert_doctype_permissions

ADVICE_DOCTYPE = "HR Payment Advice"
REFERENCE_DOCTYPE = "HR Payment Advice Reference"

# The status fields a source document might carry, in the order they are trusted.
# End of Service Benefit keeps payment state on `payment_status`; Annual Leave
# Disbursement keeps it on `status`.
PAID_STATUS_FIELDS = ("payment_status", "status")


def payment_advice_needs_approval() -> bool:
	"""True when an active approval workflow covers HR Payment Advice.

	Same shape, and the same reason, as
	:func:`hr_suite.hr_suite.utils.journal_entry_needs_approval`: where a PM Workflow
	covers a doctype an automatic submit is refused, and the caller has to create the
	document and leave it in Draft rather than take its own operation down with it.

	Only permission_manager's PM Workflow is consulted, so a site without it keeps
	stock behaviour.
	"""
	if not frappe.db.exists("DocType", "PM Workflow"):
		return False

	return bool(frappe.db.exists("PM Workflow", {"document_type": ADVICE_DOCTYPE, "is_active": 1}))


def get_payment_advice_for(source_doctype: str, source_name: str) -> str | None:
	"""Name of the live advice already raised for a document, or None.

	Cancelled advices do not count — an advice that was cancelled is a claim that was
	withdrawn, and the document is free to raise another.
	"""
	if not source_doctype or not source_name:
		return None

	advice = frappe.qb.DocType(ADVICE_DOCTYPE)
	rows = (
		frappe.qb.from_(advice)
		.select(advice.name)
		.where(
			(advice.source_doctype == source_doctype)
			& (advice.source_name == source_name)
			& (advice.docstatus < 2)
		)
		.orderby(advice.creation)
		.limit(1)
	).run(as_dict=True)

	if rows:
		return rows[0].name

	# An advice raised for several documents at once carries only the first of them
	# as its source, so the references table is the second place to look.
	reference = frappe.qb.DocType(REFERENCE_DOCTYPE)
	rows = (
		frappe.qb.from_(reference)
		.inner_join(advice)
		.on(reference.parent == advice.name)
		.select(advice.name)
		.where(
			(reference.parenttype == ADVICE_DOCTYPE)
			& (reference.reference_doctype == source_doctype)
			& (reference.reference_name == source_name)
			& (advice.docstatus < 2)
		)
		.orderby(advice.creation)
		.limit(1)
	).run(as_dict=True)

	return rows[0].name if rows else None


def create_payment_advice_for(doc, lines=None, description: str | None = None):
	"""Raise — or return — the one payment advice that carries ``doc`` to finance.

	:param doc: the HR document that owes the money, as a Document object.
	:param lines: what finance is being asked to pay, as a list of dicts with
	        ``amount`` and ``description``. ``reference_doctype`` and
	        ``reference_name`` default to ``doc`` itself, so a document paying only
	        for itself passes amounts and nothing else.
	:param description: fallback description for lines that carry none, and the
	        advice's remarks.

	Returns the HR Payment Advice document, whether it was raised now or already
	existed.
	"""
	if isinstance(doc, str):
		frappe.throw(
			_("create_payment_advice_for() needs the source document itself, not its name."),
			title=_("Payment Advice"),
		)

	existing = get_payment_advice_for(doc.doctype, doc.name)
	if existing:
		return frappe.get_doc(ADVICE_DOCTYPE, existing)

	rows = _normalise_lines(doc, lines, description)
	if not rows:
		frappe.throw(
			_("{0} {1} has nothing to pay, so no payment advice can be raised for it.").format(
				_(doc.doctype), doc.name
			),
			title=_("Nothing to Pay"),
		)

	employee = cstr(doc.get("employee"))
	if not employee:
		frappe.throw(
			_("{0} {1} names no employee, so no payment advice can be raised for it.").format(
				_(doc.doctype), doc.name
			),
			title=_("No Employee"),
		)

	company = doc.get("company") or frappe.db.get_value("Employee", employee, "company")

	advice = frappe.get_doc(
		{
			"doctype": ADVICE_DOCTYPE,
			"employee": employee,
			"company": company,
			"posting_date": doc.get("posting_date") or doc.get("transaction_date") or nowdate(),
			"source_doctype": doc.doctype,
			"source_name": doc.name,
			"auto_generated": 1,
			"remarks": description or _("Raised by {0} {1}").format(_(doc.doctype), doc.name),
			"references": rows,
		}
	)

	# The advice is a consequence of a document this user was already allowed to
	# submit. Demanding a separate create permission here would abort their submit
	# and roll the HR document back with it.
	advice.insert(ignore_permissions=True)

	needs_approval = payment_advice_needs_approval()
	if needs_approval:
		# Submitting under an approval workflow is refused, and the refusal would
		# travel out of the source document's on_submit. Leave it for the approver.
		frappe.msgprint(
			_("Payment Advice <b>{0}</b> was raised for {1} and is waiting for approval. "
			  "It reaches finance once approved.").format(advice.name, advice.employee_name or employee),
			title=_("Payment Advice awaiting approval"),
			indicator="orange",
		)
	else:
		advice.submit()
		frappe.msgprint(
			_("Payment Advice <b>{0}</b> was raised for {1}.").format(
				advice.name, advice.employee_name or employee
			),
			title=_("Payment Advice Raised"),
			indicator="green",
		)

	return advice


def _normalise_lines(doc, lines, description) -> list:
	"""Turn whatever the caller passed into reference rows, dropping the empty ones.

	A zero line is not a payment; sending finance a 0.00 row to confirm wastes a
	human being's afternoon.
	"""
	rows = []
	for line in lines or []:
		amount = flt(line.get("amount"))
		if amount <= 0:
			continue

		rows.append(
			{
				"reference_doctype": line.get("reference_doctype") or doc.doctype,
				"reference_name": line.get("reference_name") or doc.name,
				"description": cstr(line.get("description") or description or ""),
				"amount": amount,
			}
		)

	return rows


@frappe.whitelist()
def mark_paid(advice: str, payment_reference: str = None, payment_date: str = None, bank_account: str = None):
	"""Finance confirms the money left; every source document hears about it.

	Public HTTP endpoint — permissions are checked here, not by the caller.
	"""
	advice_doc = frappe.get_doc(ADVICE_DOCTYPE, advice)
	assert_doctype_permissions(ADVICE_DOCTYPE, ("write", "submit"), doc=advice_doc)

	if advice_doc.docstatus != 1:
		frappe.throw(
			_("Only a submitted payment advice can be marked paid. {0} is {1}.").format(
				advice_doc.name, _("Draft") if advice_doc.docstatus == 0 else _("Cancelled")
			),
			title=_("Not Submitted"),
		)

	if advice_doc.status == "Paid":
		# A second click on Mark as Paid must not overwrite the reference of the
		# payment that actually happened.
		return {
			"name": advice_doc.name,
			"status": advice_doc.status,
			"already_paid": True,
			"updated": [],
		}

	payment_reference = cstr(payment_reference).strip()
	if not payment_reference:
		frappe.throw(
			_("A payment reference is required — cheque number, transfer reference or WPS batch."),
			title=_("Payment Reference Missing"),
		)

	values = {
		"status": "Paid",
		"payment_reference": payment_reference,
		"payment_date": getdate(payment_date) if payment_date else getdate(nowdate()),
		"amount_paid": flt(advice_doc.total_amount),
		"paid_by": frappe.session.user,
	}
	if bank_account:
		values["bank_account"] = bank_account

	# Every one of these fields carries allow_on_submit in the DocType JSON. Without
	# it this line is an UpdateAfterSubmitError.
	advice_doc.db_set(values)

	updated = _write_back_payment_status(advice_doc)

	frappe.msgprint(
		_("Payment Advice {0} marked paid. {1} document(s) updated.").format(advice_doc.name, len(updated)),
		alert=True,
		indicator="green",
	)

	return {
		"name": advice_doc.name,
		"status": advice_doc.status,
		"already_paid": False,
		"updated": updated,
	}


def _write_back_payment_status(advice) -> list:
	"""Tell every document on the advice that it has been paid.

	The source documents are submitted. ``doc.save()`` on a submitted document
	re-validates every field and refuses the ones without allow_on_submit — End of
	Service Benefit's ``payment_status`` is one of them — so a confirmation would
	fail on documents that have nothing wrong with them. A direct column write
	touches the status and nothing else. The same reasoning applies to the advice's
	own reference rows: saving the parent to change a child row re-validates the
	whole table.

	A document with no status this app recognises is left alone rather than guessed
	at; its row records that nothing was written.
	"""
	updated = []
	seen = set()

	targets = [(row.reference_doctype, row.reference_name, row.name) for row in advice.references]
	if advice.source_doctype and advice.source_name:
		targets.append((advice.source_doctype, advice.source_name, None))

	for reference_doctype, reference_name, row_name in targets:
		if not reference_doctype or not reference_name:
			continue

		key = (reference_doctype, reference_name)
		if key in seen:
			continue
		seen.add(key)

		fieldname = paid_status_field(reference_doctype)
		if not fieldname:
			continue

		# One read that answers both questions: does it still exist, and is it still
		# live. A cancelled document is not paid, whatever the advice says.
		current = frappe.db.get_value(reference_doctype, reference_name, ["docstatus", fieldname], as_dict=True)
		if not current or current.docstatus == 2 or cstr(current.get(fieldname)) == "Cancelled":
			continue

		frappe.db.set_value(reference_doctype, reference_name, fieldname, "Paid")
		updated.append(
			{"reference_doctype": reference_doctype, "reference_name": reference_name, "fieldname": fieldname}
		)

		if row_name:
			frappe.db.set_value(REFERENCE_DOCTYPE, row_name, "reference_status", "Paid")

	return updated


def paid_status_field(doctype: str) -> str | None:
	"""The field on ``doctype`` that can be set to exactly "Paid", or None.

	Exact match on the option, never a substring: Work Injury offers "Compensation
	Paid", which is a different thing and must not be written by this.
	"""
	meta = frappe.get_meta(doctype)

	for fieldname in PAID_STATUS_FIELDS:
		field = meta.get_field(fieldname)
		if not field or field.fieldtype != "Select":
			continue

		options = [option.strip() for option in cstr(field.options).split("\n")]
		if "Paid" in options:
			return fieldname

	return None
