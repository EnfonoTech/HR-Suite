import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, money_in_words


class HRPaymentAdvice(Document):
	"""One claim on the company's bank, raised by HR and confirmed by finance.

	HR money documents — a leave disbursement, a settlement, an end of service
	benefit, a loan payout — all end in the same place: someone in finance has to
	move the money and someone in HR has to learn that it moved. This document is
	that handshake. It is never the ledger entry and never the payslip; it is the
	instruction and the receipt.

	Nothing here decides *what* is owed. The source document does that and hands the
	figures over through
	:func:`hr_suite.hr_suite.payment_advice.create_payment_advice_for`.
	"""

	def validate(self):
		self._set_company()
		self._set_defaults()
		self._validate_references()
		self._set_totals()
		self._lock_amounts_while_pending()
		self._set_draft_status()

	def before_submit(self):
		"""Where approvers are configured the only way in is the approval, never a bare Submit."""
		from hr_suite.hr_suite.payment_advice_flow import approvals_configured

		if approvals_configured(self.company) and not self.flags.approval_complete:
			frappe.throw(
				_("This company's payment advices need approval. Use Send for Approval; the advice is "
				  "submitted automatically by the last approver."),
				title=_("Approval Required"),
			)
		if flt(self.total_amount) <= 0:
			frappe.throw(_("Nothing is sanctioned, so there is nothing for finance to pay."), title=_("Nothing Sanctioned"))

	def on_submit(self):
		"""Submitting IS the approval — from here the advice is finance's to pay.

		It used to ask ``payment_advice_needs_approval()`` here, but that predicate is
		site-level: it answers "does a workflow cover this doctype", not "has THIS
		document been signed", so it read the same before and after the approver acted.
		On any site with that workflow every signed advice stayed "Pending Approval"
		for ever and the Awaiting Payment queue was permanently empty. The pending
		state belongs on the draft, which is where it is set now.

		Assignments made in ``on_submit`` are not persisted — the row is already
		written by the time this runs — so the status goes through ``db_set``.
		"""
		self.db_set("status", "Approved")

	def before_cancel(self):
		"""The source document points back at this advice and stays submitted; that link must not block the cancel.

		Without this the advice and its source lock each other: frappe refuses to cancel the advice while a submitted
		Leave Salary Settlement or Gratuity Finalisation links to it, and the source refuses to cancel while the
		advice is live. The order is payment entry, then advice, then source.
		"""
		from hr_suite.hr_suite.payment_advice import SOURCE_DOCUMENTS

		ignore = list(self.get("ignore_linked_doctypes") or [])
		self.ignore_linked_doctypes = tuple(ignore + [d for d in SOURCE_DOCUMENTS if d not in ignore])

	def on_cancel(self):
		if self.status == "Paid":
			frappe.throw(
				_(
					"Payment Advice {0} has already been paid on {1} against reference {2}. "
					"Cancelling it would leave the documents it settled marked as paid with "
					"nothing behind them. Reverse the payment in the accounts first."
				).format(self.name, self.payment_date, self.payment_reference or "—"),
				title=_("Already Paid"),
			)

		self.db_set("status", "Cancelled")

		from hr_suite.hr_suite.payment_advice import release_source_links

		release_source_links(self)

	def _set_company(self):
		if not self.company and self.employee:
			self.company = frappe.db.get_value("Employee", self.employee, "company")

		if not self.company:
			frappe.throw(_("Company is required before a payment advice can be raised."))

	def _set_defaults(self):
		"""Payment type from the source document, and the approvers from the settings."""
		from hr_suite.hr_suite.payment_advice import PAYMENT_TYPE_BY_SOURCE
		from hr_suite.hr_suite.payment_advice_flow import get_approvers

		# A document built in code gets no field defaults, so a blank type is filled here, before the
		# mandatory check, rather than relying on the DocType default.
		if not self.payment_type or self.payment_type == "Other":
			self.payment_type = PAYMENT_TYPE_BY_SOURCE.get(self.source_doctype, self.payment_type or "Other")
		if self.is_new() and not (self.approver_l1 and self.approver_l2):
			l1, l2 = get_approvers(self.company)
			self.approver_l1 = self.approver_l1 or l1
			self.approver_l2 = self.approver_l2 or l2

	def _lock_amounts_while_pending(self):
		"""An approver signs a figure; changing it underneath them is how a control is bypassed."""
		if self.status != "Pending Approval" or self.flags.approval_action or self.is_new():
			return
		before = self.get_doc_before_save()
		if before and (
			flt(before.total_amount) != flt(self.total_amount) or flt(before.total_claimed) != flt(self.total_claimed)
		):
			frappe.throw(
				_("The amounts cannot change while the advice waits for approval. Recall it, correct it and send it again."),
				title=_("Locked For Approval"),
			)

	def _validate_references(self):
		if not self.references:
			frappe.throw(
				_("Add at least one reference. A payment advice with no reference asks finance to pay for nothing."),
				title=_("No References"),
			)

		# Company currency lands on every row so the grid formats amounts in the
		# company's currency — this app runs in BH/AE/OM/SA/IN, and the system
		# default currency is not the company's.
		currency = frappe.get_cached_value("Company", self.company, "default_currency")

		seen = set()
		by_doctype = {}
		for row in self.references:
			if not row.reference_doctype or not row.reference_name:
				frappe.throw(
					_("Row #{0}: both a reference document type and a reference name are required.").format(row.idx)
				)

			if flt(row.amount) <= 0:
				frappe.throw(
					_("Row #{0}: amount must be greater than zero.").format(row.idx),
					title=_("Nothing to Pay"),
				)

			# Unset means "sanction what was claimed". HR may sanction less, down to nothing.
			if row.sanctioned_amount is None:
				row.sanctioned_amount = row.amount
			if flt(row.sanctioned_amount) < 0 or flt(row.sanctioned_amount) > flt(row.amount):
				frappe.throw(
					_("Row #{0}: the sanctioned amount must be between 0 and the claimed {1}.").format(
						row.idx, flt(row.amount)
					),
					title=_("Invalid Sanctioned Amount"),
				)

			key = (row.reference_doctype, row.reference_name)
			if key in seen:
				frappe.throw(
					_("Row #{0}: {1} {2} is already on this advice, and paying it twice is exactly what this advice exists to prevent.").format(
						row.idx, _(row.reference_doctype), row.reference_name
					),
					title=_("Duplicate Reference"),
				)
			seen.add(key)

			row.currency = currency
			by_doctype.setdefault(row.reference_doctype, []).append(row)

		self._assert_references_exist_and_belong_to_employee(by_doctype)

	def _assert_references_exist_and_belong_to_employee(self, by_doctype: dict):
		"""One query per referenced doctype, never one per row.

		Also refuses a reference that belongs to a different employee: an advice
		names one person and pays into one account, so a row pointing at somebody
		else's settlement would pay the wrong human being.
		"""
		for reference_doctype, rows in by_doctype.items():
			meta = frappe.get_meta(reference_doctype)
			has_employee = bool(meta.get_field("employee"))

			fields = ["name"] + (["employee"] if has_employee else [])
			# get_all, not get_list: an advice raised by HR may reference a document the
			# user who opens the advice cannot read, and an existence check must not
			# turn into "this document does not exist".
			found = frappe.get_all(
				reference_doctype,
				filters={"name": ["in", [row.reference_name for row in rows]]},
				fields=fields,
			)
			found_map = {record["name"]: record for record in found}

			for row in rows:
				record = found_map.get(row.reference_name)
				if not record:
					frappe.throw(
						_("Row #{0}: {1} {2} does not exist.").format(
							row.idx, _(reference_doctype), row.reference_name
						)
					)

				row_employee = cstr(record.get("employee")) if has_employee else ""
				if row_employee and row_employee != cstr(self.employee):
					frappe.throw(
						_("Row #{0}: {1} {2} belongs to employee {3}, not {4}.").format(
							row.idx, _(reference_doctype), row.reference_name, row_employee, self.employee
						),
						title=_("Wrong Employee"),
					)

	def _set_totals(self):
		# total_amount is what Finance pays: the SANCTIONED total.
		self.total_claimed = flt(sum(flt(row.amount) for row in self.references), self.precision("total_claimed"))
		self.total_amount = flt(sum(flt(row.sanctioned_amount) for row in self.references), self.precision("total_amount"))

		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.amount_in_words = money_in_words(self.total_amount, currency)

	def _set_draft_status(self):
		# validate() also runs on the way through submit, by which time docstatus is
		# already 1 — resetting to Draft there would undo on_submit on every later save.
		#
		# "Pending Approval" is a draft state too: an advice raised while an approval
		# workflow covers this doctype waits, unsubmitted, for its approver. Resetting
		# that to Draft on the approver's first save would erase the one signal telling
		# them the document is theirs to act on.
		if self.docstatus == 0 and self.status not in ("Pending Approval", "Rejected"):
			self.status = "Draft"
