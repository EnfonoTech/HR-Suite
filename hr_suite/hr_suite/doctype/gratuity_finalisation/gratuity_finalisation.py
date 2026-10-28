# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Gratuity at exit: compare what was provided with the final gratuity and post only the difference.

Final gratuity is the Country Config calculation for the exit reason (resignation factors, dismissal
forfeiture). Provided to date is the Gratuity Accrual ledger (opening + monthly). On submit one Journal Entry:
    difference > 0   Dr Gratuity Expense / Cr monthly credit account (employee)
    difference < 0   Dr monthly credit account (employee) / Cr Gratuity Expense   (the excess reversed)
    Provision used   Dr Gratuity Provision (employee) / Cr Gratuity Payable (employee), the final amount
and an HR Payment Advice for the final gratuity; Finance pays it from Gratuity Payable to the bank.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate

from hr_suite.hr_suite import gratuity_provision as gp

MONEY = gp.MONEY


class GratuityFinalisation(Document):
	def validate(self):
		if not self.relieving_date:
			frappe.throw(
				_("{0} has no Relieving Date. Enter it on the Employee first.").format(self.employee),
				title=_("Relieving Date Missing"),
			)
		other = frappe.db.exists("Gratuity Finalisation", {"employee": self.employee, "docstatus": 1, "name": ["!=", self.name]})
		if other:
			frappe.throw(_("Gratuity for {0} is already finalised in {1}.").format(self.employee, other), title=_("Already Finalised"))
		self.compute()

	def compute(self):
		from hr_suite.hr_suite.gratuity import calculate_for_employee

		result = calculate_for_employee(self.employee, self.relieving_date, self.exit_reason)
		self.final_amount = flt(result.net_entitlement, MONEY)
		self.years_of_service = result.years_of_service
		self.calculation_notes = result.notes
		self.accrued_to_date = gp.accrued_to_date(self.employee)
		self.difference = flt(self.final_amount - self.accrued_to_date, MONEY)
		self.pending_items = "\n".join(pending_items(self.employee, self.relieving_date)) or _("Nothing pending.")

	def on_submit(self):
		acc = gp.accounts(self.company)
		self.db_set({"credit_account": acc.credit, "payable_account": acc.payable}, update_modified=False)
		lines = []
		diff = flt(self.difference, MONEY)
		if diff:
			expense = {"account": acc.expense, ("debit_in_account_currency" if diff > 0 else "credit_in_account_currency"): abs(diff)}
			cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
			if cost_center:
				expense["cost_center"] = cost_center
			lines.append(expense)
			lines.append(self._party(acc.credit, abs(diff), "credit" if diff > 0 else "debit"))
		if acc.credit != acc.payable and flt(self.final_amount) > 0:
			lines.append(self._party(acc.credit, flt(self.final_amount, MONEY), "debit"))
			lines.append(self._party(acc.payable, flt(self.final_amount, MONEY), "credit"))
		if lines:
			je = frappe.get_doc(
				{
					"doctype": "Journal Entry",
					"voucher_type": "Journal Entry",
					"company": self.company,
					"posting_date": getdate(self.relieving_date),
					"user_remark": _("Gratuity finalisation {0} - {1} - final {2}, provided {3}, difference {4}").format(
						self.name, self.employee_name or self.employee, self.final_amount, self.accrued_to_date, diff
					),
					"accounts": lines,
				}
			)
			je.insert(ignore_permissions=True)
			if not gp.journal_entry_needs_approval():
				je.submit()
			self.db_set("journal_entry", je.name, update_modified=False)
		if diff:
			row = frappe.get_doc(
				{
					"doctype": gp.LEDGER,
					"employee": self.employee,
					"source": gp.FINALISATION,
					"posting_date": getdate(self.relieving_date),
					"amount": diff,
					"credit_account": acc.credit,
					"journal_entry": self.journal_entry,
					"gratuity_finalisation": self.name,
				}
			)
			row.flags.from_hr_suite = True
			row.insert(ignore_permissions=True)
		# The HR Payment Advice follows once this submit has committed (as for a leave salary settlement):
		# a second submittable document raised inside this transaction can take the finalisation down with it.
		if flt(self.final_amount) > 0:
			frappe.enqueue(
				"hr_suite.hr_suite.payment_advice.raise_after_submit",
				queue="short",
				enqueue_after_commit=True,
				job_id="hrs_advice_{0}".format(self.name),
				deduplicate=True,
				doctype=self.doctype,
				name=self.name,
			)

	def _party(self, account, amount, side):
		return {"account": account, side + "_in_account_currency": amount, "party_type": "Employee", "party": self.employee}

	def on_cancel(self):
		from hr_suite.hr_suite.payment_advice import assert_no_live_advice

		assert_no_live_advice(self)
		for name in frappe.get_all(gp.LEDGER, filters={"gratuity_finalisation": self.name}, pluck="name"):
			row = frappe.get_doc(gp.LEDGER, name)
			row.flags.from_hr_suite = True
			row.delete(ignore_permissions=True)
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			frappe.get_doc("Journal Entry", self.journal_entry).cancel()


def pending_items(employee, relieving_date) -> list:
	"""What HR should clear before paying: months not provided, open settlements and advices, draft entries."""
	from frappe.utils import get_first_day, get_last_day

	out = []
	relieving = getdate(relieving_date)
	cfg = gp.settings()
	last = frappe.get_all(gp.LEDGER, filters={"employee": employee, "source": gp.MONTHLY}, pluck="period_end", order_by="period_end desc", limit=1)
	if cfg.start_date and (not last or getdate(last[0]) < get_first_day(relieving)):
		out.append(
			_("Monthly provision not posted after {0}; the difference covers it.").format(formatdate(last[0]) if last else _("the start date"))
		)
	drafts = frappe.db.sql(
		"""select distinct ga.journal_entry from `tabGratuity Accrual` ga join `tabJournal Entry` je on je.name = ga.journal_entry
		where ga.employee = %s and je.docstatus = 0""",
		employee,
	)
	if drafts:
		out.append(_("Provision Journal Entries still in draft: {0}").format(", ".join(d[0] for d in drafts)))
	for dt, label in (("Leave Salary Settlement", _("Leave Salary Settlement")), ("HR Payment Advice", _("HR Payment Advice"))):
		open_docs = frappe.get_all(dt, filters={"employee": employee, "docstatus": 0}, pluck="name")
		if open_docs:
			out.append(_("{0} in draft: {1}").format(label, ", ".join(open_docs)))
	unpaid = frappe.get_all("HR Payment Advice", filters={"employee": employee, "docstatus": 1, "status": ["not in", ("Paid", "Cancelled")]}, pluck="name")
	if unpaid:
		out.append(_("HR Payment Advice not yet paid: {0}").format(", ".join(unpaid)))
	return out


@frappe.whitelist()
def preview(employee: str, exit_reason: str = "Termination") -> dict:
	"""The review screen's figures, without saving anything."""
	frappe.has_permission("Gratuity Finalisation", "create", throw=True)
	doc = frappe.new_doc("Gratuity Finalisation")
	doc.employee = employee
	doc.exit_reason = exit_reason
	for field in ("employee_name", "company", "date_of_joining", "relieving_date"):
		doc.set(field, frappe.db.get_value("Employee", employee, field))
	if not doc.relieving_date:
		frappe.throw(_("{0} has no Relieving Date. Enter it on the Employee first.").format(employee), title=_("Relieving Date Missing"))
	doc.compute()
	acc_error = ""
	try:
		acc = gp.accounts(doc.company)
		accounts = {"credit": acc.credit, "payable": acc.payable, "expense": acc.expense}
	except frappe.ValidationError as exc:
		accounts, acc_error = {}, frappe.utils.strip_html(str(exc))
	existing = frappe.db.get_value("Gratuity Finalisation", {"employee": employee, "docstatus": ["<", 2]}, ["name", "docstatus"], as_dict=True)
	return {
		"employee": employee,
		"employee_name": doc.employee_name,
		"company": doc.company,
		"date_of_joining": doc.date_of_joining,
		"relieving_date": doc.relieving_date,
		"exit_reason": exit_reason,
		"accrued_to_date": doc.accrued_to_date,
		"final_amount": doc.final_amount,
		"difference": doc.difference,
		"years_of_service": doc.years_of_service,
		"calculation_notes": doc.calculation_notes,
		"pending_items": doc.pending_items,
		"accounts": accounts,
		"accounts_error": acc_error,
		"existing": existing,
	}


@frappe.whitelist()
def confirm(employee: str, exit_reason: str) -> str:
	"""HR confirms the review: the finalisation is created and submitted, posting only the difference."""
	frappe.has_permission("Gratuity Finalisation", "submit", throw=True)
	doc = frappe.get_doc({"doctype": "Gratuity Finalisation", "employee": employee, "exit_reason": exit_reason})
	for field in ("employee_name", "company", "date_of_joining", "relieving_date"):
		doc.set(field, frappe.db.get_value("Employee", employee, field))
	doc.insert()
	doc.submit()
	return doc.name
