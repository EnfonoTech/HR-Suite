import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, cstr, flt, getdate, today

from hr_suite.hr_suite.utils import assert_doctype_permissions


class EmployeeLoan(Document):
	def validate(self):
		self._set_defaults()
		self._validate_inputs()
		self._validate_approval_state()
		self._rebuild_schedule()
		self._update_summary()

	def on_submit(self):
		if self.approval_status != "Approved":
			frappe.throw(_("Loan must be approved before submission"))
		self.db_set("status", "Active")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def _set_defaults(self):
		if not self.status:
			self.status = "Draft"
		if not self.approval_status:
			self.approval_status = "Draft"
		if not self.loan_date:
			self.loan_date = today()
		if not self.repayment_method:
			self.repayment_method = "Equal Installments"

	def _validate_inputs(self):
		if flt(self.loan_amount) <= 0:
			frappe.throw(_("Loan Amount must be greater than zero"))
		if self.repayment_method == "Equal Installments" and (self.installment_count or 0) <= 0:
			frappe.throw(_("Installment Count is required for equal installments"))
		if self.repayment_method == "Fixed Installment Amount" and flt(self.monthly_installment_amount) <= 0:
			frappe.throw(_("Monthly Installment Amount is required for fixed installment loans"))
		if self.repayment_start_date and getdate(self.repayment_start_date) < getdate(self.loan_date):
			frappe.throw(_("Repayment Start Date cannot be before Loan Date"))

	def _validate_approval_state(self):
		if self.disbursement_journal_entry and self.approval_status != "Disbursed":
			self.approval_status = "Disbursed"
		if self.approval_status == "Ready for Disbursement" and self.docstatus != 1:
			frappe.throw(_("Loan must be submitted before disbursement approval"))

	def _rebuild_schedule(self):
		if self.docstatus == 1:
			return
		start_date = getdate(self.repayment_start_date or self.loan_date or today())
		installments = _build_installment_plan(
			flt(self.loan_amount),
			self.repayment_method,
			self.installment_count,
			flt(self.monthly_installment_amount),
			start_date,
		)
		self.set("installments", [])
		for idx, row in enumerate(installments, start=1):
			self.append(
				"installments",
				{
					"installment_number": idx,
					"due_date": row["due_date"],
					"installment_amount": row["installment_amount"],
					"deducted_amount": 0,
					"outstanding_amount": row["installment_amount"],
					"deduction_status": "Pending",
					"payroll_deducted_amount": 0,
				},
			)

	def _update_summary(self):
		deducted = sum(flt(row.deducted_amount) for row in self.installments)
		outstanding = sum(flt(row.outstanding_amount or row.installment_amount) for row in self.installments)
		self.total_deducted = round(deducted, 2)
		self.outstanding_balance = round(outstanding, 2)
		if self.docstatus == 1:
			self.status = "Closed" if self.outstanding_balance <= 0 else "Active"

	def create_disbursement_journal_entry(self):
		if self.disbursement_journal_entry:
			return self.disbursement_journal_entry
		if self.docstatus != 1:
			frappe.throw(_("Loan must be submitted before disbursement"))
		if self.approval_status != "Ready for Disbursement":
			frappe.throw(_("Disbursement approval is required before creating the journal entry"))

		company = self.company
		loan_receivable_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Loan%"], "root_type": "Asset", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Receivable", "is_group": 0},
				"name",
			)
		)
		disbursement_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Bank", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Cash", "is_group": 0},
				"name",
			)
		)

		if not loan_receivable_account or not disbursement_account:
			frappe.throw(
				_("Could not find accounts for loan disbursement entry. Please configure Loan Receivable and Bank/Cash accounts."),
				title=_("Account Not Found"),
			)

		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": self.disbursement_date or self.loan_date,
				"user_remark": f"Employee Loan Disbursement — {self.employee_name} — {flt(self.loan_amount):.2f} SAR",
				"accounts": [
					{
						"account": loan_receivable_account,
						"debit_in_account_currency": flt(self.loan_amount),
						"party_type": "Employee",
						"party": self.employee,
					},
					{
						"account": disbursement_account,
						"credit_in_account_currency": flt(self.loan_amount),
					},
				],
			}
		)
		assert_doctype_permissions("Journal Entry", ("create", "submit"))
		je.insert()
		je.submit()

		self.db_set("disbursement_journal_entry", je.name)
		self.db_set("disbursement_date", self.disbursement_date or self.loan_date)
		self.db_set("approval_status", "Disbursed")
		return je.name


def _assert_loan_approver():
	frappe.only_for(("System Manager", "HR Manager"))


def _touch_if_missing(doc, fieldname, value):
	if not doc.get(fieldname):
		doc.db_set(fieldname, value, update_modified=False)


def _build_installment_plan(loan_amount, repayment_method, installment_count, monthly_installment_amount, start_date):
	planned = []
	remaining = flt(loan_amount)
	installment_count = cint(installment_count or 0)
	if repayment_method == "Equal Installments":
		base_amount = round(remaining / installment_count, 2)
		for idx in range(installment_count):
			amount = base_amount if idx < installment_count - 1 else round(remaining, 2)
			planned.append({"due_date": add_months(start_date, idx), "installment_amount": amount})
			remaining = round(remaining - amount, 2)
	else:
		idx = 0
		while remaining > 0:
			amount = min(flt(monthly_installment_amount), remaining)
			planned.append({"due_date": add_months(start_date, idx), "installment_amount": round(amount, 2)})
			remaining = round(remaining - amount, 2)
			idx += 1
	return planned


def resolve_legacy_approval_status(docstatus: int, current_status: str | None = None, disbursement_journal_entry: str | None = None) -> str:
	if disbursement_journal_entry:
		return "Disbursed"
	if docstatus == 1:
		return "Approved"
	if current_status in ("Rejected", "Pending Approval"):
		return current_status
	return "Draft"


def reconcile_legacy_employee_loans():
	rows = frappe.get_all(
		"Employee Loan",
		fields=["name", "docstatus", "approval_status", "disbursement_journal_entry", "status"],
	)
	for row in rows:
		resolved_status = resolve_legacy_approval_status(
			row.docstatus,
			row.approval_status,
			row.disbursement_journal_entry,
		)
		updates = {}
		if row.approval_status != resolved_status:
			updates["approval_status"] = resolved_status

		resolved_loan_status = row.status
		if row.docstatus == 2:
			resolved_loan_status = "Cancelled"
		elif row.docstatus == 1 and row.status == "Draft":
			resolved_loan_status = "Active"
		if resolved_loan_status != row.status:
			updates["status"] = resolved_loan_status

		if updates:
			frappe.db.set_value("Employee Loan", row.name, updates, update_modified=False)


def get_due_loan_deduction(employee: str, month: int, year: int) -> dict:
	rows = frappe.db.sql(
		"""
		SELECT
			loan.name AS loan_name,
			child.name AS installment_name,
			child.installment_amount,
			child.outstanding_amount,
			child.due_date
		FROM `tabEmployee Loan` loan
		INNER JOIN `tabEmployee Loan Installment` child ON child.parent = loan.name
		WHERE loan.employee = %(employee)s
		  AND loan.docstatus = 1
		  AND loan.status = 'Active'
		  AND child.deduction_status IN ('Pending', 'Deferred')
		  AND YEAR(child.due_date) = %(year)s
		  AND MONTH(child.due_date) = %(month)s
		ORDER BY child.due_date, child.idx
		""",
		{"employee": employee, "month": month, "year": year},
		as_dict=True,
	)
	amount = sum(flt(row.outstanding_amount or row.installment_amount) for row in rows)
	return {
		"loan_deduction": round(amount, 2),
		"installment_names": [row.installment_name for row in rows],
		"loan_names": sorted({row.loan_name for row in rows}),
	}


def _update_parent_loan_summary(loan_name: str):
	parent = frappe.get_doc("Employee Loan", loan_name)
	parent._update_summary()
	parent.db_set("total_deducted", parent.total_deducted, update_modified=False)
	parent.db_set("outstanding_balance", parent.outstanding_balance, update_modified=False)
	parent.db_set("status", "Closed" if parent.outstanding_balance <= 0 else "Active", update_modified=False)


def _get_locked_installment_state(installment_name: str):
	rows = frappe.db.sql(
		"""
		SELECT name, parent, installment_amount, deducted_amount, outstanding_amount,
			deduction_status, payroll_reference, payroll_deducted_amount
		FROM `tabEmployee Loan Installment`
		WHERE name = %s
		FOR UPDATE
		""",
		(installment_name,),
		as_dict=True,
	)
	if not rows:
		frappe.throw(_("Loan installment {0} was not found.").format(installment_name))
	return rows[0]


def apply_payroll_loan_deductions(payroll_doc):
	for row in payroll_doc.employees:
		for installment_name in (row.get("loan_installments") or "").split(","):
			installment_name = installment_name.strip()
			if not installment_name:
				continue
			state = _get_locked_installment_state(installment_name)
			if state.payroll_reference == payroll_doc.name and flt(state.payroll_deducted_amount) > 0:
				continue
			if cstr(state.payroll_reference).strip() and state.payroll_reference != payroll_doc.name:
				frappe.throw(
					_(
						"Loan installment {0} was already deducted by payroll {1}.<br>"
						"Loan installment {0} has already been deducted through payroll {1}."
					).format(installment_name, state.payroll_reference),
					title=_("Duplicate Loan Deduction"),
				)
			installment = frappe.get_doc("Employee Loan Installment", installment_name)
			current_outstanding = flt(state.outstanding_amount or state.installment_amount)
			if current_outstanding <= 0:
				continue
			installment.db_set("deducted_amount", flt(installment.deducted_amount) + current_outstanding, update_modified=False)
			installment.db_set("outstanding_amount", 0, update_modified=False)
			installment.db_set("deduction_status", "Deducted", update_modified=False)
			installment.db_set("deduction_date", payroll_doc.posting_date, update_modified=False)
			installment.db_set("payroll_reference", payroll_doc.name, update_modified=False)
			installment.db_set("payroll_deducted_amount", current_outstanding, update_modified=False)
			_update_parent_loan_summary(installment.parent)


def revert_payroll_loan_deductions(payroll_doc):
	rows = frappe.get_all(
		"Employee Loan Installment",
		filters={"payroll_reference": payroll_doc.name},
		fields=["name", "parent", "installment_amount", "payroll_deducted_amount"],
	)
	for row in rows:
		installment = frappe.get_doc("Employee Loan Installment", row.name)
		payroll_deducted_amount = flt(row.payroll_deducted_amount)
		if payroll_deducted_amount <= 0:
			payroll_deducted_amount = min(flt(installment.installment_amount), flt(installment.deducted_amount or installment.installment_amount))
		installment.db_set("deducted_amount", max(0, flt(installment.deducted_amount) - payroll_deducted_amount), update_modified=False)
		installment.db_set("outstanding_amount", flt(installment.outstanding_amount) + payroll_deducted_amount, update_modified=False)
		installment.db_set("deduction_status", "Pending", update_modified=False)
		installment.db_set("deduction_date", None, update_modified=False)
		installment.db_set("payroll_reference", None, update_modified=False)
		installment.db_set("payroll_deducted_amount", 0, update_modified=False)
		_update_parent_loan_summary(installment.parent)


@frappe.whitelist()
def create_disbursement_journal_entry(doc_name: str):
	doc = frappe.get_doc("Employee Loan", doc_name)
	journal_entry = doc.create_disbursement_journal_entry()
	return {"journal_entry": journal_entry}


@frappe.whitelist()
def request_loan_approval(doc_name: str):
	doc = frappe.get_doc("Employee Loan", doc_name)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft loans can be submitted for approval"))
	doc.db_set("approval_status", "Pending Approval")
	_touch_if_missing(doc, "requested_by", frappe.session.user)
	_touch_if_missing(doc, "requested_on", today())
	return {"approval_status": "Pending Approval"}


@frappe.whitelist()
def approve_loan(doc_name: str):
	_assert_loan_approver()
	doc = frappe.get_doc("Employee Loan", doc_name)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft loans can be approved"))
	doc.db_set("approval_status", "Approved")
	doc.db_set("approved_by", frappe.session.user, update_modified=False)
	doc.db_set("approved_on", today(), update_modified=False)
	return {"approval_status": "Approved"}


@frappe.whitelist()
def reject_loan(doc_name: str):
	_assert_loan_approver()
	doc = frappe.get_doc("Employee Loan", doc_name)
	if doc.docstatus != 0:
		frappe.throw(_("Only draft loans can be rejected"))
	doc.db_set("approval_status", "Rejected")
	return {"approval_status": "Rejected"}


@frappe.whitelist()
def approve_loan_disbursement(doc_name: str):
	_assert_loan_approver()
	doc = frappe.get_doc("Employee Loan", doc_name)
	if doc.docstatus != 1:
		frappe.throw(_("Loan must be submitted before disbursement approval"))
	if doc.approval_status not in ("Approved", "Ready for Disbursement", "Disbursed"):
		frappe.throw(_("Loan approval is required before disbursement approval"))
	doc.db_set("approval_status", "Ready for Disbursement")
	doc.db_set("disbursement_approved_by", frappe.session.user, update_modified=False)
	doc.db_set("disbursement_approved_on", today(), update_modified=False)
	return {"approval_status": "Ready for Disbursement"}