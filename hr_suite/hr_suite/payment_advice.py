"""payment_advice.py — the one road from an HR money document to the finance desk.

Every HR document that owes an employee money outside the payroll run — an annual
leave disbursement, a final settlement, an end of service benefit, a loan payout —
reaches finance as an HR Payment Advice. Finance answers with :func:`mark_paid`, and
the source document hears back.

The advice is raised ON REQUEST, from a button on the submitted source document
(:func:`raise_for_document`), and never from inside the source document's own
``on_submit``. Inserting and submitting a second submittable document inside another
document's submit transaction is exactly the pattern that failed a payroll run here
once: whatever the advice refuses — a missing reference, an approval workflow — takes
the document that raised it down too. Asking for it afterwards costs one click and
cannot roll anything back.

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
		# travel out of the source document's on_submit. Leave it for the approver —
		# and say on the document itself that this is what it is waiting for, since a
		# draft advice is otherwise indistinguishable from one somebody abandoned.
		advice.db_set("status", "Pending Approval")
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


# The HR documents that can put a claim to finance, and how each describes itself.
# `amount_field` is the money to claim, `link_field` is where the advice's name is
# written back (with `link_type_field` for a Dynamic Link), and `paid_state` is the
# status the document reaches once finance confirms — see :func:`paid_status_field`.
SOURCE_DOCUMENTS = {
	"Annual Leave Disbursement": {
		# The ticket is an entitlement and the leave pay is an advance, but finance pays
		# both in one transfer, so both are claimed — and only the leave pay is ever
		# recovered at payroll. Claimed as the two PARTS, never as total_leave_pay, which
		# already includes the ticket: claiming the total and the ticket asked finance to
		# pay the air fare twice.
		"lines": (
			("leave_salary_recovery_amount", "Leave salary paid in advance"),
			("ticket_amount", "Annual air ticket", "ticket_entitled"),
		),
	},
	"Salary Settlement": {
		"lines": (("net_payable", "Mid-month salary settlement"),),
		"link_field": "payment_advice",
		"link_type_field": "payment_advice_type",
	},
	"End of Service Benefit": {
		"lines": (("net_eosb", "End of service benefit"),),
	},
}


def _claim_lines(doc, spec: dict) -> list:
	"""What this document is asking finance to pay, one line per figure it carries.

	A line may name a third field that gates it — an air ticket is only claimed where
	the document says the employee is entitled to one.
	"""
	meta = frappe.get_meta(doc.doctype)
	rows = []
	for line in spec["lines"]:
		field, label = line[0], line[1]
		gate = line[2] if len(line) > 2 else ""
		if not meta.has_field(field):
			continue
		if gate and not doc.get(gate):
			continue
		amount = flt(doc.get(field))
		if amount > 0:
			rows.append({"amount": amount, "description": _(label)})
	return rows


@frappe.whitelist()
def raise_for_document(doctype: str, name: str) -> dict:
	"""Raise the payment advice for one submitted HR document, on request.

	Deliberately a separate action rather than a hook: see the module docstring. The
	answer is the same whether it is the first click or the fifth — an advice already
	raised is returned, never duplicated.
	"""
	spec = SOURCE_DOCUMENTS.get(doctype)
	if not spec:
		frappe.throw(
			_("{0} does not raise payment advices.").format(_(doctype)), title=_("Payment Advice")
		)

	frappe.has_permission(doctype, "read", doc=name, throw=True)
	assert_doctype_permissions(ADVICE_DOCTYPE, ("create",))

	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 1:
		frappe.throw(
			_("{0} {1} is not submitted, so there is nothing to ask finance to pay yet.").format(
				_(doctype), name
			),
			title=_("Not Submitted"),
		)

	existing = get_payment_advice_for(doctype, name)
	if existing:
		return {"advice": existing, "created": False}

	lines = _claim_lines(doc, spec)
	if not lines:
		frappe.throw(
			_("{0} {1} owes nothing, so no payment advice can be raised for it.").format(
				_(doctype), name
			),
			title=_("Nothing to Pay"),
		)

	advice = create_payment_advice_for(
		doc, lines=lines, description=_("{0} {1}").format(_(doctype), name)
	)

	_write_back_advice_link(doc, spec, advice.name)
	return {"advice": advice.name, "created": True}


def _write_back_advice_link(doc, spec: dict, advice_name: str) -> None:
	"""Record the advice on the source document, where the document has a field for it.

	``frappe.db.set_value`` and not ``doc.save()``: the source document is submitted,
	and saving it would re-validate every child row against fields that are not
	``allow_on_submit``.
	"""
	link_field = spec.get("link_field")
	if not link_field or not frappe.get_meta(doc.doctype).has_field(link_field):
		return

	values = {link_field: advice_name}
	type_field = spec.get("link_type_field")
	if type_field and frappe.get_meta(doc.doctype).has_field(type_field):
		values[type_field] = ADVICE_DOCTYPE

	frappe.db.set_value(doc.doctype, doc.name, values, update_modified=False)


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
