import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, cstr, flt, get_link_to_form, getdate, today

from hr_suite.hr_suite.utils import assert_doctype_permissions

# Fallback name for the Salary Component that carries a loan instalment onto the
# Salary Slip. Overridden per site by Hr Suite Settings -> loan_salary_component.
LOAN_DEDUCTION_COMPONENT = "Loan Repayment"

# Error Log title, so a site can filter `Error Log` and see exactly which instalments
# were not booked into payroll and why.
LOAN_PAYROLL_ERROR_TITLE = "HR Suite: loan instalment not booked into payroll"

# An instalment is claimed by exactly ONE payroll engine, and `deduction_status` is the
# lock that says which:
#   Pending    nobody has claimed it. Monthly Payroll may take it; so may this module.
#   Scheduled  an `Additional Salary` exists and a real Salary Slip will deduct it.
#              `get_due_loan_deduction` does not return it, so Monthly Payroll cannot
#              touch it, which is what stops the same instalment being taken twice.
#   Deducted   money has been taken, by either engine.
#   Deferred   deliberately postponed by a human.
#   Cancelled  the loan was cancelled.
INSTALLMENT_PENDING = "Pending"
INSTALLMENT_SCHEDULED = "Scheduled"
INSTALLMENT_DEDUCTED = "Deducted"
INSTALLMENT_DEFERRED = "Deferred"
INSTALLMENT_CANCELLED = "Cancelled"


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
		self._book_installments_into_payroll()

	def on_cancel(self):
		cancel_loan_additional_salaries(self)
		self.db_set("status", "Cancelled")

	def _book_installments_into_payroll(self):
		"""Materialise the schedule as `Additional Salary` rows, reporting any it could not.

		Wrapped, because the schedule is the loan's own record and must survive even when
		payroll is not yet configured to carry it. Whatever is skipped here is reported to
		the user now, logged for the audit trail, and re-offered by the
		`Book Payroll Deductions` button and by Payroll Preview.
		"""
		try:
			result = ensure_installment_additional_salaries(self)
		except Exception:
			frappe.log_error(title=LOAN_PAYROLL_ERROR_TITLE, message=frappe.get_traceback())
			frappe.msgprint(
				_(
					"The loan was submitted, but its instalments could not be booked into payroll. "
					"See the Error Log, then use {0} on this loan."
				).format(frappe.bold(_("Book Payroll Deductions"))),
				title=_("Loan Instalments Not Booked"),
				indicator="orange",
			)
			return

		if result.get("skipped"):
			frappe.msgprint(
				_("{0} of {1} instalment(s) were not booked into payroll:").format(
					len(result["skipped"]), len(self.installments or [])
				)
				+ "<ul>"
				+ "".join("<li>{0}</li>".format(row["reason"]) for row in result["skipped"])
				+ "</ul>",
				title=_("Loan Instalments Not Booked"),
				indicator="orange",
			)

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

		# Derived from installment_amount - deducted_amount, NOT from `outstanding_amount`.
		# The previous form was `flt(row.outstanding_amount or row.installment_amount)`, and
		# a fully recovered instalment has `outstanding_amount == 0`, which is falsy — so it
		# fell back to the full instalment and the balance never moved. A loan could be paid
		# off in full and still report its whole principal outstanding, and `status` could
		# never reach Closed.
		outstanding = sum(
			max(0.0, flt(row.installment_amount) - flt(row.deducted_amount))
			for row in self.installments
			if row.deduction_status != INSTALLMENT_CANCELLED
		)

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
		  AND (child.additional_salary IS NULL OR child.additional_salary = '')
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
			deduction_status, payroll_reference, payroll_deducted_amount,
			additional_salary, salary_slip, due_date, installment_number
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
			# The instalment is already booked onto a real Salary Slip through an
			# Additional Salary. Deducting it here as well would take the money twice.
			# `get_due_loan_deduction` already filters these out, so reaching this point
			# means the Monthly Payroll row was fetched BEFORE the booking and then
			# submitted after it.
			if cstr(state.additional_salary).strip():
				frappe.throw(
					_(
						"Loan installment {0} is already booked into payroll as Additional Salary {1}. "
						"Re-fetch the employees on this Monthly Payroll so it is not deducted twice."
					).format(cint(state.installment_number), state.additional_salary),
					title=_("Duplicate Loan Deduction"),
				)
			# NOTE: no "already Deducted -> skip" here. A settled instalment claimed by a
			# DIFFERENT Monthly Payroll must still raise the conflict below; skipping it
			# early would swallow exactly the duplicate this function exists to catch.
			# The `outstanding <= 0` check further down already no-ops a settled row.
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
	doc.check_permission("write")
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

# ── Employee Loan → Additional Salary → the real Salary Slip ──────────────────
#
# WHY `Additional Salary`, and WHY at submit time.
#
# `apply_payroll_loan_deductions` above is reached from exactly one place —
# `monthly_payroll.py:185`, hr_suite's parallel payroll engine. Run payroll the
# supported way (Payroll Entry -> Salary Slip) and it is never called, so the
# instalment is never deducted and the net pay on the payslip is wrong.
#
# The route taken here is the one hrms itself uses for every "an event owes the
# employee, or the employee owes the company, money this month" case — Employee
# Incentive, Retention Bonus, Leave Encashment, Gratuity and Employee Advance all
# materialise AS an `Additional Salary` carrying ref_doctype / ref_docname. hr_suite's
# own `Employee Penalty` already does the same. The Salary Slip picks them up in
# `add_additional_salary_components` (salary_slip.py:1331-1349) and records the
# Additional Salary name on the `Salary Detail` row it creates, which is the exact
# back-reference this module reconciles against.
#
# WHEN: one Additional Salary per instalment, created when the loan is SUBMITTED.
#
#   * The schedule is frozen at submit — `_rebuild_schedule` returns early once
#     `docstatus == 1` — so booking every instalment up front cannot be invalidated by
#     a later reschedule of the same loan. A rescheduled loan is a cancel + amend, and
#     `on_cancel` withdraws the bookings.
#   * Creating them on demand during a payroll run would mean inserting documents from
#     inside another document's validate/submit. `PayrollEntry.submit_salary_slips_for_employees`
#     (payroll_entry.py:1570-1608) wraps the whole submission in one try/except that
#     rolls back on ANY error, so a booking failure there would destroy the payroll run.
#     Booking at loan submit puts the failure where it belongs — on the loan, months
#     before payroll — and leaves payroll to read documents that already exist.
#   * A period can be re-run safely because the Additional Salary, not a counter, is the
#     idempotency token: it stays live until cancelled, and hrms refuses a second Salary
#     Slip for the same employee and period.
#
# DOUBLE DEDUCTION is prevented by `deduction_status` acting as a lock (see the constants
# at the top of this file). Booking flips Pending -> Scheduled;
# `get_due_loan_deduction` only ever returns Pending / Deferred rows, so Monthly Payroll
# stops seeing an instalment the moment a payslip owns it, and `apply_payroll_loan_deductions`
# throws outright if it is handed one anyway.


def get_loan_salary_component_name() -> str:
	"""Configured loan-recovery Salary Component, or the shipped default name."""
	return (
		cstr(frappe.db.get_single_value("Hr Suite Settings", "loan_salary_component")).strip()
		or LOAN_DEDUCTION_COMPONENT
	)


def _find_loan_recovery_account(company: str) -> str:
	"""The account a loan instalment must credit when it is recovered.

	Deliberately the SAME account `create_disbursement_journal_entry` DEBITS on
	disbursement, and the same one `monthly_payroll._build_payroll_journal_entry`
	credits, so a loan opened by one route and recovered by another still nets to zero
	on one ledger instead of two.
	"""
	return (
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
		or ""
	)


def prepare_loan_salary_component(company: str) -> tuple:
	"""(component_name, reason). An empty `reason` means it is safe to post."""
	from hr_suite.hr_suite.integrations.hrms import ensure_salary_component_account

	component = get_loan_salary_component_name()
	ok, reason = ensure_salary_component_account(
		component,
		company,
		component_type="Deduction",
		fallback_account=_find_loan_recovery_account(company),
		# A loan instalment is a fixed sum owed, not a rate of pay: it must not shrink
		# because the employee took unpaid leave.
		depends_on_payment_days=0,
		error_title=LOAN_PAYROLL_ERROR_TITLE,
	)
	return component, ("" if ok else reason)


def get_loan_component_setup_gap(company: str) -> str:
	"""Why a loan instalment could not be posted for `company` right now, or "".

	STRICTLY READ-ONLY — unlike `prepare_loan_salary_component` it creates nothing, so
	Payroll Preview can explain a blocking issue without becoming a writer. It answers the
	one question `PayrollEntry.get_salary_component_account` will ask at accrual time:
	can this component name resolve to an account of this company?
	"""
	from hr_suite.hr_suite.integrations.hrms import _get_configured_deduction_account

	component = get_loan_salary_component_name()

	if frappe.db.get_value(
		"Salary Component Account",
		{"parent": component, "parenttype": "Salary Component", "company": company},
		"account",
	):
		return ""

	if _get_configured_deduction_account(company, component):
		return ""

	if _find_loan_recovery_account(company):
		return ""

	return _(
		"Salary Component {0} has no account for {1}, and no employee loan receivable could be "
		"found in its Chart of Accounts. Map one under HR Suite Settings \u2192 Deduction Accounts."
	).format(component, company)


def _live_additional_salary(name: str) -> bool:
	"""True when `name` is a submitted Additional Salary that still carries an amount."""
	if not cstr(name).strip():
		return False
	return frappe.db.get_value("Additional Salary", name, "docstatus") == 1


def ensure_installment_additional_salaries(loan, recover_arrears_from=None) -> dict:
	"""Book every still-payable, unbooked instalment of `loan` as an Additional Salary.

	Idempotent: an instalment that already carries a submitted Additional Salary, or has
	already been deducted, or has been deliberately deferred, is left alone. Each
	instalment is booked inside its own savepoint, so one employee's missing Salary
	Structure Assignment cannot stop the rest of the schedule being booked.

	`recover_arrears_from` is the first day of the payroll period the caller is preparing.
	An instalment that fell due BEFORE it is in arrears, and booking it on its own due
	date would put it in a period that has already run — where no Salary Slip will ever
	look for it, so the money would silently never be recovered. Such an instalment is
	booked on `recover_arrears_from` instead. Only the Additional Salary moves; the
	instalment keeps its contractual `due_date`, so the schedule still records when the
	money was owed and the loan ledger stays honest.

	Returns ``{"created": [...], "skipped": [{"installment": name, "reason": str}]}``.
	"""
	if isinstance(loan, str):
		loan = frappe.get_doc("Employee Loan", loan)

	created, skipped = [], []
	if loan.docstatus != 1 or loan.status == INSTALLMENT_CANCELLED:
		return {"created": created, "skipped": skipped}

	component, reason = prepare_loan_salary_component(loan.company)
	currency = _resolve_loan_currency(loan)
	employee = frappe.db.get_value(
		"Employee",
		loan.employee,
		["status", "date_of_joining", "relieving_date"],
		as_dict=True,
	) or frappe._dict()

	for row in loan.installments or []:
		state = _get_locked_installment_state(row.name)

		if state.deduction_status not in (INSTALLMENT_PENDING,):
			continue
		if _live_additional_salary(state.additional_salary):
			continue
		amount = flt(state.outstanding_amount or state.installment_amount)
		if amount <= 0:
			continue

		payroll_date = state.due_date
		if payroll_date and recover_arrears_from and getdate(payroll_date) < getdate(recover_arrears_from):
			payroll_date = getdate(recover_arrears_from)

		blocker = reason or _installment_blocker(loan, state, employee, currency, payroll_date)
		if blocker:
			skipped.append({"installment": row.name, "reason": blocker})
			continue

		savepoint = "hrsuite_loan_booking"
		frappe.db.savepoint(savepoint)
		try:
			additional_salary = frappe.get_doc({
				"doctype": "Additional Salary",
				"employee": loan.employee,
				"company": loan.company,
				"currency": currency,
				"salary_component": component,
				"amount": amount,
				"payroll_date": payroll_date,
				"is_recurring": 0,
				# Never overwrite: a loan instalment is charged ON TOP of whatever the
				# Salary Structure already carries for this component.
				"overwrite_salary_structure_amount": 0,
				"deduct_full_tax_on_selected_payroll_date": 0,
				"ref_doctype": loan.doctype,
				"ref_docname": loan.name,
			})
			additional_salary.insert(ignore_permissions=True)
			additional_salary.submit()
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			message = _("Instalment {0} due {1}: {2}").format(
				cint(state.installment_number), state.due_date, cstr(exc)
			)
			skipped.append({"installment": row.name, "reason": message})
			frappe.log_error(title=LOAN_PAYROLL_ERROR_TITLE, message=f"{loan.name} / {row.name}\n{message}")
			continue
		else:
			frappe.db.release_savepoint(savepoint)

		frappe.db.set_value(
			"Employee Loan Installment",
			row.name,
			{
				"additional_salary": additional_salary.name,
				"deduction_status": INSTALLMENT_SCHEDULED,
			},
			update_modified=False,
		)
		created.append(additional_salary.name)

	return {"created": created, "skipped": skipped}


def _resolve_loan_currency(loan) -> str:
	from hr_suite.hr_suite.integrations.hrms import get_employee_payroll_currency

	on_date = None
	for row in loan.installments or []:
		due = getdate(row.due_date) if row.due_date else None
		if due and (on_date is None or due < on_date):
			on_date = due
	return get_employee_payroll_currency(loan.employee, on_date, loan.company)


def _installment_blocker(loan, state, employee, currency: str, payroll_date=None) -> str:
	"""Why THIS instalment cannot be booked, or "".

	Every check mirrors a validation `Additional Salary` would raise anyway
	(additional_salary.py:37-127). Doing them here turns an exception into a sentence a
	payroll officer can act on, and keeps the loan submit itself clean.
	"""
	number = cint(state.installment_number)

	if not state.due_date:
		return _("Instalment {0} has no due date, so it cannot be given a payroll date.").format(number)

	if employee.get("status") == "Inactive":
		return _("Instalment {0}: Employee {1} is Inactive, so no payroll document can be raised.").format(
			number, loan.employee
		)

	if not currency:
		return _(
			"Instalment {0}: {1} has no submitted Salary Structure Assignment, so the payroll "
			"currency is unknown. Assign a Salary Structure, then use {2}."
		).format(number, loan.employee, frappe.bold(_("Book Payroll Deductions")))

	# Everything below is checked against the date the Additional Salary will actually
	# carry, which is the due date unless the instalment is in arrears and is being
	# recovered in a later period.
	payroll_date = getdate(payroll_date or state.due_date)

	date_of_joining = employee.get("date_of_joining")
	if date_of_joining and payroll_date < getdate(date_of_joining):
		return _("Instalment {0} would be recovered on {1}, before the employee joined on {2}.").format(
			number, payroll_date, date_of_joining
		)

	relieving_date = employee.get("relieving_date")
	if relieving_date and payroll_date > getdate(relieving_date):
		return _(
			"Instalment {0} would be recovered on {1}, after the employee was relieved on {2}. "
			"Recover it through the Full and Final Statement instead."
		).format(number, payroll_date, relieving_date)

	if not frappe.db.exists(
		"Salary Structure Assignment",
		{"employee": loan.employee, "docstatus": 1, "from_date": ["<=", payroll_date]},
	):
		return _(
			"Instalment {0}: no Salary Structure Assignment is in force on {1}, so no Salary Slip "
			"will carry it."
		).format(number, payroll_date)

	return ""


def cancel_loan_additional_salaries(loan) -> None:
	"""Withdraw the payroll bookings a cancelled loan leaves behind.

	An instalment already DEDUCTED is left exactly as it is: the money has been taken
	and the payslip that took it is the record of it. Everything still merely Scheduled
	is unbooked, so nothing is deducted for a loan that no longer exists.
	"""
	if isinstance(loan, str):
		loan = frappe.get_doc("Employee Loan", loan)

	deducted = []
	for row in loan.installments or []:
		state = _get_locked_installment_state(row.name)
		if state.deduction_status == INSTALLMENT_DEDUCTED:
			deducted.append(cint(state.installment_number))
			continue

		if _live_additional_salary(state.additional_salary):
			# `on_cancel` on Additional Salary calls back into
			# `release_installment_for_additional_salary`, which clears the link.
			frappe.get_doc("Additional Salary", state.additional_salary).cancel()

		frappe.db.set_value(
			"Employee Loan Installment",
			row.name,
			{
				"additional_salary": None,
				"deduction_status": INSTALLMENT_CANCELLED,
			},
			update_modified=False,
		)

	if deducted:
		frappe.msgprint(
			_(
				"Instalment(s) {0} had already been deducted from a submitted Salary Slip and were "
				"left untouched. Refund them through a Journal Entry if the loan is being reversed."
			).format(", ".join(cstr(number) for number in deducted)),
			title=_("Already Deducted"),
			indicator="orange",
		)


def release_installment_for_additional_salary(additional_salary: str) -> None:
	"""Free any instalment booked by `additional_salary` so a later period can take it."""
	rows = frappe.get_all(
		"Employee Loan Installment",
		filters={"additional_salary": additional_salary, "parenttype": "Employee Loan"},
		fields=["name", "parent", "deduction_status"],
	)
	for row in rows:
		if row.deduction_status not in (INSTALLMENT_SCHEDULED, INSTALLMENT_PENDING):
			continue
		frappe.db.set_value(
			"Employee Loan Installment",
			row.name,
			{"additional_salary": None, "deduction_status": INSTALLMENT_PENDING},
			update_modified=False,
		)


def _loan_installments_on_salary_slip(slip) -> dict:
	"""{installment row name: amount} for the loan instalments this slip actually carries.

	Keyed off `Salary Detail.additional_salary`, which hrms writes on every deduction row
	it builds from an Additional Salary (salary_slip.py:1518+). That is an exact
	document-to-document link, not a date-and-amount guess.
	"""
	amounts = {}
	for row in slip.get("deductions") or []:
		if row.get("additional_salary"):
			amounts[row.additional_salary] = flt(amounts.get(row.additional_salary, 0)) + flt(row.amount)

	if not amounts:
		return {}

	installments = frappe.get_all(
		"Employee Loan Installment",
		filters={"additional_salary": ("in", list(amounts)), "parenttype": "Employee Loan"},
		fields=["name", "parent", "additional_salary"],
	)
	return {row.name: flt(amounts.get(row.additional_salary)) for row in installments}


def mark_installments_deducted_from_salary_slip(slip) -> None:
	"""Record on the loan that a submitted Salary Slip has actually taken the instalment."""
	parents = set()
	for installment_name, amount in _loan_installments_on_salary_slip(slip).items():
		state = _get_locked_installment_state(installment_name)
		if state.deduction_status == INSTALLMENT_DEDUCTED:
			continue
		frappe.db.set_value(
			"Employee Loan Installment",
			installment_name,
			{
				"deducted_amount": flt(state.deducted_amount) + amount,
				"outstanding_amount": max(0, flt(state.outstanding_amount) - amount),
				"deduction_status": INSTALLMENT_DEDUCTED,
				"deduction_date": slip.get("posting_date") or slip.get("end_date"),
				"salary_slip": slip.name,
				"payroll_deducted_amount": amount,
			},
			update_modified=False,
		)
		parents.add(state.parent)

	for parent in parents:
		_update_parent_loan_summary(parent)


def release_installments_from_salary_slip(slip) -> None:
	"""Undo `mark_installments_deducted_from_salary_slip` when the slip is cancelled.

	The instalment goes back to Scheduled while its Additional Salary is still live, so a
	re-run of the same period deducts it exactly once more and no manual repair is needed.
	"""
	rows = frappe.get_all(
		"Employee Loan Installment",
		filters={"salary_slip": slip.name, "parenttype": "Employee Loan"},
		fields=["name"],
	)
	parents = set()
	for row in rows:
		state = _get_locked_installment_state(row.name)
		amount = flt(state.payroll_deducted_amount)
		still_booked = _live_additional_salary(state.additional_salary)
		frappe.db.set_value(
			"Employee Loan Installment",
			row.name,
			{
				"deducted_amount": max(0, flt(state.deducted_amount) - amount),
				"outstanding_amount": flt(state.outstanding_amount) + amount,
				"deduction_status": INSTALLMENT_SCHEDULED if still_booked else INSTALLMENT_PENDING,
				"deduction_date": None,
				"salary_slip": None,
				"payroll_deducted_amount": 0,
			},
			update_modified=False,
		)
		parents.add(state.parent)

	for parent in parents:
		_update_parent_loan_summary(parent)


@frappe.whitelist()
def book_payroll_deductions(doc_name: str) -> dict:
	"""Retry the payroll booking for one loan (the `Book Payroll Deductions` button)."""
	doc = frappe.get_doc("Employee Loan", cstr(doc_name))
	doc.check_permission("write")
	result = ensure_installment_additional_salaries(doc)
	return {
		"created": result["created"],
		"skipped": [row["reason"] for row in result["skipped"]],
	}


@frappe.whitelist()
def book_loan_deductions_for_period(company: str, start_date: str, end_date: str) -> dict:
	"""Book every unbooked instalment falling due on or before `end_date` for `company`.

	Called from Payroll Preview, which is read-only and therefore never books anything of
	its own accord — this runs only when a person presses the button.
	"""
	frappe.only_for(("HR Manager", "System Manager"))
	if not frappe.has_permission("Employee Loan", "write"):
		frappe.throw(_("Not permitted to book Employee Loan deductions."), frappe.PermissionError)

	company = cstr(company).strip()
	start_date = getdate(start_date)
	end_date = getdate(end_date)
	if start_date > end_date:
		frappe.throw(_("Start Date cannot be after End Date."))
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("A valid Company is required."))

	loans = frappe.db.sql(
		"""
		SELECT DISTINCT loan.name
		FROM `tabEmployee Loan` loan
		INNER JOIN `tabEmployee Loan Installment` child ON child.parent = loan.name
		WHERE loan.docstatus = 1
		  AND loan.company = %(company)s
		  AND loan.status = 'Active'
		  AND child.parenttype = 'Employee Loan'
		  AND child.deduction_status = %(pending)s
		  AND (child.additional_salary IS NULL OR child.additional_salary = '')
		  AND child.due_date <= %(end_date)s
		""",
		{"company": company, "pending": INSTALLMENT_PENDING, "end_date": end_date},
		pluck=True,
	)

	created, skipped = [], []
	for loan_name in loans:
		result = ensure_installment_additional_salaries(loan_name, recover_arrears_from=start_date)
		created.extend(result["created"])
		skipped.extend(
			_("{0}: {1}").format(get_link_to_form("Employee Loan", loan_name), row["reason"])
			for row in result["skipped"]
		)

	return {"created": created, "skipped": skipped}
