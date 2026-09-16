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
		self._validate_references()
		self._set_totals()
		self._set_draft_status()

	def on_submit(self):
		"""Hand the advice to whoever signs it off.

		Assignments made in ``on_submit`` are not persisted — the row is already
		written by the time this runs — so the status goes through ``db_set``.
		"""
		from hr_suite.hr_suite.payment_advice import payment_advice_needs_approval

		self.db_set("status", "Pending Approval" if payment_advice_needs_approval() else "Approved")

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

	def _set_company(self):
		if not self.company and self.employee:
			self.company = frappe.db.get_value("Employee", self.employee, "company")

		if not self.company:
			frappe.throw(_("Company is required before a payment advice can be raised."))

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
		self.total_amount = flt(sum(flt(row.amount) for row in self.references), self.precision("total_amount"))

		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.amount_in_words = money_in_words(self.total_amount, currency)

	def _set_draft_status(self):
		# validate() also runs on the way through submit, by which time docstatus is
		# already 1 — resetting to Draft there would undo on_submit on every later save.
		if self.docstatus == 0:
			self.status = "Draft"
