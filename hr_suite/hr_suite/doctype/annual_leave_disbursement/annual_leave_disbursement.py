# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

"""Annual leave paid before the employee travels — and taken back when payroll runs.

Leave salary is an ADVANCE of the salary the employee would have been paid at month
end for the very same days. Handing it over and doing nothing else pays those days
twice: once here, once on the payslip. So a submitted disbursement does three things
and none of them is optional —

  * prices the leave through ``compute_leave_salary``, i.e. from Country Config, so a
    30-day divisor and a Basic+Housing+Transport split stop being facts of the code;
  * posts the money with a Journal Entry, Draft where a PM Workflow covers Journal
    Entry (submitting it there is refused, and the refusal used to take the whole
    parent operation down with it);
  * books one Additional Salary DEDUCTION per calendar month the leave falls in, which
    is what payroll and Payroll Preview already read.

The entitlement is read from the HRMS Leave Allocation the rest of the system uses —
not from this app's own counters, which no payslip and no leave dashboard consults.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, formatdate, getdate, nowdate

from hr_suite.hr_suite.utils import (
	assert_doctype_permissions,
	assert_employee_access,
	compute_leave_salary,
	get_employee_salary_components,
	get_leave_salary_recovery_component,
	get_leave_salary_terms,
	journal_entry_needs_approval,
	split_days_by_month,
)

LEAVE_SALARY_ERROR_TITLE = "HR Suite: leave salary not recovered at payroll"

# `disbursement_type` now reports what Country Config says leave salary covers instead
# of asking HR. Its two older values ("Basic Salary Only", "Full Salary") stay in the
# field's option list so amending a disbursement submitted back then still saves.

# BHD and OMR are 3-decimal currencies and this app runs in both, so every money figure
# here is carried at 3 places — the same precision compute_leave_salary returns.
_MONEY_PRECISION = 3

_PAY_LINE_FIELDS = {
	"basic_salary": "basic_leave_pay",
	"housing_allowance": "housing_allowance_pay",
	"transport_allowance": "transport_allowance_pay",
	"other_allowances": "other_allowances_pay",
}


class AnnualLeaveDisbursement(Document):

	def validate(self):
		self._pull_from_leave_application()
		self._validate_leave_period()
		self._read_allocation_balance()
		self._guard_duplicate_period()
		self._price_the_leave()

	def on_submit(self):
		if flt(self.total_leave_pay) <= 0:
			frappe.throw(
				_("Nothing to disburse: the leave pay for {0} works out to zero. Check the "
				  "Salary Structure Assignment and Country Config before submitting.").format(
					self.employee_name or self.employee
				),
				title=_("No Leave Pay"),
			)

		self.status = "Approved"
		self.db_set("status", self.status)
		self._create_leave_salary_journal_entry()
		self._create_recovery_additional_salaries()

	def on_cancel(self):
		# Deduction rows first, and deliberately. Frappe refuses to cancel an Additional
		# Salary that a SUBMITTED Salary Slip has already taken, and that refusal has to
		# stop the whole cancellation: the money was recovered on a payslip, so the
		# disbursement it recovered is no longer something that can be undone here.
		self._cancel_recovery_additional_salaries()
		self._cancel_leave_salary_journal_entry()
		self.status = "Cancelled"
		self.db_set("status", self.status, update_modified=False)

	# ── Leave period ──────────────────────────────────────────────────────────

	def _pull_from_leave_application(self):
		"""Dates and day count come from the linked Leave Application, not from retyping.

		Retyping is how a disbursement ends up covering a different period from the leave
		it pays for, and the recovery then lands on a month the employee was at work.
		"""
		if not self.leave_application:
			return

		application = frappe.db.get_value(
			"Leave Application",
			self.leave_application,
			["employee", "leave_type", "from_date", "to_date", "total_leave_days"],
			as_dict=True,
		)
		if not application:
			return

		if application.employee != self.employee:
			frappe.throw(
				_("Leave Application {0} belongs to {1}, not to {2}.").format(
					self.leave_application, application.employee, self.employee
				),
				title=_("Wrong Employee"),
			)

		self.leave_type = application.leave_type
		self.leave_from_date = application.from_date
		self.leave_to_date = application.to_date
		self.leave_days_to_pay = flt(application.total_leave_days)

	def _validate_leave_period(self):
		if not (self.leave_from_date and self.leave_to_date):
			return

		if getdate(self.leave_to_date) < getdate(self.leave_from_date):
			frappe.throw(_("Leave To cannot fall before Leave From."), title=_("Invalid Leave Period"))

		span = date_diff(self.leave_to_date, self.leave_from_date) + 1
		if not flt(self.leave_days_to_pay):
			self.leave_days_to_pay = span

		if flt(self.leave_days_to_pay) > span:
			# The recovery is split across the months the period touches, so more days than
			# the period holds could not be attributed to any payslip.
			frappe.throw(
				_("Days to disburse ({0}) cannot exceed the {1} day(s) between {2} and {3}.").format(
					flt(self.leave_days_to_pay), span,
					formatdate(self.leave_from_date), formatdate(self.leave_to_date),
				),
				title=_("Invalid Leave Period"),
			)

		if not self.leave_year:
			self.leave_year = getdate(self.leave_from_date).year

	def _read_allocation_balance(self):
		"""Balance comes from the HRMS Leave Allocation, never from a parallel count.

		Leave Application, the leave dashboard and payroll all consume the Leave Ledger.
		A disbursement priced against this app's own counters can therefore hand over
		days the employee does not have left, and nothing downstream would notice.
		"""
		if not (self.employee and self.leave_type and self.leave_from_date):
			return

		allocation = get_leave_allocation(self.employee, self.leave_type, self.leave_from_date)
		if not allocation:
			frappe.throw(
				_("{0} has no submitted Leave Allocation for {1} covering {2}. Allocate the "
				  "leave before disbursing it.").format(
					self.employee_name or self.employee, self.leave_type,
					formatdate(self.leave_from_date),
				),
				title=_("No Leave Allocation"),
			)

		self.leave_allocation = allocation.name
		self.leave_days_entitled = flt(allocation.total_leaves_allocated)

		balance = get_allocation_balance(
			self.employee, self.leave_type, self.leave_from_date, allocation, exclude=self.name
		)
		self.leave_days_balance = balance
		self.leave_days_taken = flt(allocation.total_leaves_allocated) - balance

		if flt(self.leave_days_to_pay) > balance:
			frappe.throw(
				_("Cannot disburse {0} day(s) of {1}: {2} has {3} day(s) left on Leave "
				  "Allocation {4}.").format(
					flt(self.leave_days_to_pay), self.leave_type,
					self.employee_name or self.employee, balance, allocation.name,
				),
				title=_("Not Enough Leave Balance"),
			)

	def _guard_duplicate_period(self):
		"""One period, one disbursement.

		A second document over the same dates pays the same days a second time, and the
		two recoveries then compete for one payslip. A cancelled disbursement is not in
		the way — it is docstatus 2 and its deduction was cancelled along with it.
		"""
		if not (self.employee and self.leave_from_date and self.leave_to_date):
			return

		filters = {
			"employee": self.employee,
			"docstatus": 1,
			"leave_from_date": ["<=", self.leave_to_date],
			"leave_to_date": [">=", self.leave_from_date],
		}
		if self.name:
			filters["name"] = ["!=", self.name]

		existing = frappe.get_all(
			"Annual Leave Disbursement", filters=filters, pluck="name", limit=1
		)
		if existing:
			frappe.throw(
				_("{0} already covers leave for {1} between {2} and {3}. Cancel it before "
				  "disbursing the same period again.").format(
					existing[0], self.employee_name or self.employee,
					formatdate(self.leave_from_date), formatdate(self.leave_to_date),
				),
				title=_("Leave Period Already Disbursed"),
			)

	# ── Money ─────────────────────────────────────────────────────────────────

	def _price_the_leave(self):
		"""Every figure comes from Country Config through compute_leave_salary().

		The divisor used to be a literal 30 and the split a literal basic + housing +
		transport. Both were right for one country and wrong for the next: Bahrain, Oman
		and India each disagree about the length of a salary month and about which
		allowances travel with the employee.
		"""
		if not self.employee:
			return

		terms = get_leave_salary_terms(self.employee)
		self.leave_salary_basis = terms["basis"]
		self.disbursement_type = terms["covers"] or self.disbursement_type

		salary = get_employee_salary_components(self.employee) or {}
		self.monthly_basic_salary = flt(salary.get("basic_salary"))
		self.monthly_gross_salary = flt(salary.get("total_salary"))

		leave_salary = compute_leave_salary(self.employee, flt(self.leave_days_to_pay))
		self.daily_basic_rate = flt(leave_salary["daily_rate"])

		for component_field, target_field in _PAY_LINE_FIELDS.items():
			self.set(target_field, flt(leave_salary["lines"].get(component_field), _MONEY_PRECISION))

		# Only the pay is an advance. The ticket is an entitlement in its own right, so it
		# is added to what is handed over and left out of what payroll takes back.
		self.leave_salary_recovery_amount = flt(leave_salary["total"], _MONEY_PRECISION)
		ticket = flt(self.ticket_amount) if self.ticket_entitled else 0.0
		self.total_leave_pay = flt(self.leave_salary_recovery_amount + ticket, _MONEY_PRECISION)

	# ── Journal Entry ─────────────────────────────────────────────────────────

	def _create_leave_salary_journal_entry(self):
		"""Post the disbursement, under the same rules as Overtime Request."""
		if self.linked_payroll_entry:
			return

		if not flt(self.total_leave_pay) > 0:
			return

		company = self.company

		expense_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Leave Salary%"],
				 "root_type": "Expense", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Salary%"],
				 "root_type": "Expense", "is_group": 0},
				"name",
			)
		)
		# Deliberately no third "any expense account" fallback. frappe.db.get_value orders
		# by `modified`, so the account it picked was effectively arbitrary — leave salary
		# was landing in Depreciation or Cost of Goods Sold on any chart that does not use
		# the English word "Salary", and the entry still msgprinted green. Refusing is the
		# honest answer: name the account and the site can fix it in a minute.

		payable_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Salary Payable%"],
				 "root_type": "Liability", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Payable", "is_group": 0},
				"name",
			)
		)

		if not expense_account or not payable_account:
			# Throw, never warn. on_submit goes on to book and submit the payroll recovery
			# after this, so returning here would deduct the advance from the next payslip
			# for money the ledger never recorded — and the orange msgprint is invisible to
			# an API or background submit.
			frappe.throw(
				_("Could not find the accounts this Journal Entry needs for {0}: a leave-salary "
				  "or salary EXPENSE account, and a Salary Payable account. Add them to the "
				  "Chart of Accounts (or set Default Payroll Payable Account on the Company) "
				  "and submit again. Nothing was posted.").format(company),
				title=_("Account Not Found"),
			)

		# Currency must follow the company — this app runs in BH/AE/OM/IN as well as SA.
		currency = frappe.get_cached_value("Company", company, "default_currency")

		# NOTE: do NOT set reference_type/reference_name on the accounts. `Journal Entry
		# Account.reference_type` is a Select with a fixed option list that does not include
		# "Annual Leave Disbursement", so setting it makes the Journal Entry unsubmittable:
		#   "Row #1: Reference Type cannot be 'Annual Leave Disbursement'."
		# The link back to this document is kept on `linked_payroll_entry` below, and the
		# document name is written into user_remark for the audit trail.
		remark = _("Annual Leave Salary — {0} — {1} to {2} ({3} day(s)) — {4} {5} ({6})").format(
			self.employee_name or self.employee,
			formatdate(self.leave_from_date),
			formatdate(self.leave_to_date),
			flt(self.leave_days_to_pay),
			flt(self.total_leave_pay),
			currency,
			self.name,
		)

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": nowdate(),
			"user_remark": remark,
			"accounts": [
				# The party belongs on the PAYABLE row and nowhere else. erpnext refuses a
				# Receivable/Payable account row with no party, and refuses a party on a row
				# whose account is neither — so party on the expense row broke the entry at
				# insert on one chart and at submit on another.
				{
					"account": expense_account,
					"debit_in_account_currency": flt(self.total_leave_pay),
				},
				{
					"account": payable_account,
					"credit_in_account_currency": flt(self.total_leave_pay),
					"party_type": "Employee",
					"party": self.employee,
				},
			],
		})

		needs_approval = journal_entry_needs_approval()
		assert_doctype_permissions("Journal Entry", ("create",) if needs_approval else ("create", "submit"))
		je.insert()

		# Submitting here while an approval workflow covers Journal Entry is refused, and
		# the refusal propagates out of on_submit — so the disbursement itself could not be
		# approved at all. Leave the entry in Draft for its approver instead; the leave pay
		# is still recorded and still reaches the accounts once approved.
		if not needs_approval:
			je.submit()

		self.db_set("linked_payroll_entry", je.name)
		if needs_approval:
			frappe.msgprint(
				_("Journal Entry <b>{0}</b> was created for leave salary of {1} {2} and is "
				  "waiting for approval. It reaches the accounts once approved.").format(
					je.name, flt(self.total_leave_pay), currency
				),
				title=_("Journal Entry awaiting approval"),
				indicator="orange",
			)
		else:
			frappe.msgprint(
				_("Journal Entry <b>{0}</b> created for leave salary of {1} {2}.").format(
					je.name, flt(self.total_leave_pay), currency
				),
				title=_("Journal Entry Created"),
				indicator="green",
			)

	def _cancel_leave_salary_journal_entry(self):
		if not self.linked_payroll_entry:
			return
		if not frappe.db.exists("Journal Entry", self.linked_payroll_entry):
			return

		je = frappe.get_doc("Journal Entry", self.linked_payroll_entry)
		if je.docstatus == 1:
			je.cancel()
			return

		if je.docstatus == 0:
			# A draft waiting for its approver has posted nothing yet, but an approver who
			# submits it next week would pay out a disbursement that no longer exists. The
			# draft goes with the disbursement, and the link goes with the draft: a Link
			# field pointing at a deleted document breaks every later save of this one.
			# Clear the link FIRST. frappe.delete_doc runs check_if_doc_is_linked, which
			# sees this document's own linked_payroll_entry still pointing at the draft and
			# raises LinkExistsError — taking the whole cancellation down with it.
			self.db_set("linked_payroll_entry", None, update_modified=False)
			frappe.delete_doc("Journal Entry", je.name, ignore_permissions=True)
			frappe.msgprint(
				_("The draft Journal Entry for this disbursement was deleted, so it cannot be "
				  "approved after the disbursement was cancelled."),
				indicator="orange",
			)

	# ── Recovery at payroll ───────────────────────────────────────────────────

	def _create_recovery_additional_salaries(self):
		"""One Additional Salary deduction per calendar month the leave falls in.

		Only the leave PAY is recovered. The annual ticket is an entitlement in its own
		right — the employee is not being paid it early, they are being given it — so
		deducting it at payroll would take back money they are owed outright.

		A 21-day leave beginning on the 12th is partly one month and partly the next, and
		each part has to come off its own payslip; a single deduction on the first month
		would leave the second month paying days that were already handed over.
		"""
		recovery_total = flt(self.leave_salary_recovery_amount)
		if recovery_total <= 0:
			return

		from hr_suite.hr_suite.integrations.hrms import (
			ensure_salary_component_account,
			get_employee_payroll_currency,
		)

		terms = get_leave_salary_terms(self.employee)
		component = get_leave_salary_recovery_component(self.company, terms.get("recovery_component"))

		ok, reason = ensure_salary_component_account(
			component,
			self.company,
			component_type="Deduction",
			# The advance was a fixed sum of money. Scaling the recovery by the month's
			# payment days would give back less than was handed over — and the months a
			# leave spans are exactly the months with unusual payment days.
			depends_on_payment_days=0,
			error_title=LEAVE_SALARY_ERROR_TITLE,
		)
		if not ok:
			# Refusing the whole submit is the safe failure here, unlike a penalty that
			# merely goes undeducted: paying leave salary without booking its recovery pays
			# the employee twice for the same days, and nothing downstream catches it.
			frappe.throw(reason, title=_("Leave Salary Cannot Be Recovered"))

		currency = get_employee_payroll_currency(self.employee, self.leave_from_date, self.company)
		if not currency:
			frappe.throw(
				_("{0} has no submitted Salary Structure Assignment, so the leave salary "
				  "cannot be recovered at payroll and was not disbursed.").format(
					self.employee_name or self.employee
				),
				title=_("No Salary Structure"),
			)

		# Weighted by the calendar days each month holds, not by the days paid: HR may pay
		# fewer days than the period spans, and there is nothing on the document saying
		# which of those days were dropped.
		chunks = split_days_by_month(self.leave_from_date, self.leave_to_date)
		total_days = sum(days for _month_start, days in chunks)
		if not total_days:
			return

		booked = 0.0
		for index, (month_start, days) in enumerate(chunks):
			is_last_month = index == len(chunks) - 1
			# The last month takes whatever is left rather than its own rounded share, so
			# the deductions add up to exactly the sum advanced instead of to a few fils
			# either side of it.
			amount = (
				flt(recovery_total - booked, _MONEY_PRECISION)
				if is_last_month
				else flt(recovery_total * days / total_days, _MONEY_PRECISION)
			)
			if amount <= 0:
				continue
			booked += amount

			# The payroll date only has to land inside that month's payroll period, and the
			# first day of the leave is safely inside it — the 1st of the month can precede
			# the employee's joining date or their Salary Structure Assignment, either of
			# which Additional Salary refuses outright.
			payroll_date = max(getdate(month_start), getdate(self.leave_from_date))

			additional_salary = frappe.get_doc({
				"doctype": "Additional Salary",
				"employee": self.employee,
				"company": self.company,
				"currency": currency,
				"salary_component": component,
				"amount": amount,
				"payroll_date": payroll_date,
				"is_recurring": 0,
				"ref_doctype": self.doctype,
				"ref_docname": self.name,
				# Never overwrite: the recovery is an extra deduction alongside whatever the
				# structure holds, and two disbursements touching one month would collide on
				# hrms's duplicate-overwrite check instead of both being deducted.
				"overwrite_salary_structure_amount": 0,
				"deduct_full_tax_on_selected_payroll_date": 0,
			})
			self._refuse_if_payroll_already_ran(payroll_date, amount, currency)

			additional_salary.insert(ignore_permissions=True)
			additional_salary.submit()

		frappe.msgprint(
			_("Leave salary of {0} {1} will be recovered across {2} payroll month(s) through "
			  "salary component {3}.").format(
				flt(recovery_total), currency, len(chunks), component
			),
			title=_("Recovery Booked"),
			indicator="green",
		)

	def _refuse_if_payroll_already_ran(self, payroll_date, amount, currency):
		"""A month already paid can never read this deduction, so do not book one.

		hrms only reads an Additional Salary while it is building a Salary Slip
		(``get_additional_salaries`` matches payroll_date between the slip's start and end
		dates). A recovery aimed at a month whose payslip is already submitted is
		therefore never taken: the employee keeps both the advance and a full payslip for
		that month, and no report anywhere flags it. This used to warn AFTER inserting the
		row, which recorded the problem and created it in the same breath.
		"""
		slip = frappe.db.get_value(
			"Salary Slip",
			{
				"employee": self.employee,
				"docstatus": 1,
				"start_date": ["<=", payroll_date],
				"end_date": [">=", payroll_date],
			},
			"name",
		)
		if not slip:
			return

		frappe.throw(
			_("Salary Slip {0} for {1} is already submitted, so the {2} {3} this disbursement "
			  "would recover from that month can never be taken back. Cancel and re-run that "
			  "payslip, or recover this by hand and record it outside payroll.").format(
				slip, formatdate(payroll_date), flt(amount), currency
			),
			title=_("Payroll Already Run"),
		)

	def _cancel_recovery_additional_salaries(self):
		"""A cancelled disbursement must not leave a deduction on a future payslip."""
		booked = frappe.get_all(
			"Additional Salary",
			filters={"ref_doctype": self.doctype, "ref_docname": self.name, "docstatus": 1},
			pluck="name",
		)
		for name in booked:
			frappe.get_doc("Additional Salary", name).cancel()


# ── Module helpers ────────────────────────────────────────────────────────────


def get_leave_allocation(employee: str, leave_type: str, on_date):
	"""The submitted Leave Allocation in force for this employee, type and date."""
	rows = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": employee,
			"leave_type": leave_type,
			"docstatus": 1,
			"from_date": ["<=", getdate(on_date)],
			"to_date": [">=", getdate(on_date)],
		},
		fields=["name", "from_date", "to_date", "total_leaves_allocated"],
		order_by="from_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_allocation_balance(employee: str, leave_type: str, on_date, allocation=None, exclude: str = "") -> float:
	"""Days left on the HRMS allocation, less days this app has already disbursed.

	``get_leave_balance_on`` reads the Leave Ledger, and only a Leave Application writes
	to it. A disbursement made WITHOUT a Leave Application therefore leaves the ledger
	untouched, so those days are subtracted here too — otherwise one balance can be
	handed over twice across two periods that never overlap.
	"""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	allocation = allocation or get_leave_allocation(employee, leave_type, on_date)
	if not allocation:
		return 0.0

	balance = flt(
		get_leave_balance_on(
			employee,
			leave_type,
			getdate(on_date),
			to_date=getdate(allocation.to_date),
			consider_all_leaves_in_the_allocation_period=True,
		)
	)

	filters = {
		"employee": employee,
		"leave_type": leave_type,
		"docstatus": 1,
		"leave_application": ["is", "not set"],
		"leave_from_date": ["between", [allocation.from_date, allocation.to_date]],
	}
	if exclude:
		filters["name"] = ["!=", exclude]

	already_disbursed = frappe.get_all(
		"Annual Leave Disbursement", filters=filters, pluck="leave_days_to_pay"
	)
	return flt(balance - sum(flt(days) for days in already_disbursed), 2)


# ── Whitelisted endpoints ─────────────────────────────────────────────────────


@frappe.whitelist()
def get_leave_balance(employee, leave_type, on_date=None):
	"""Real HRMS allocation figures for the form, so HR sees what payroll sees."""
	assert_employee_access(employee)

	on_date = getdate(on_date) if on_date else getdate()
	allocation = get_leave_allocation(employee, leave_type, on_date)
	if not allocation:
		return {"allocation": None, "entitled": 0.0, "taken": 0.0, "balance": 0.0}

	balance = get_allocation_balance(employee, leave_type, on_date, allocation)
	return {
		"allocation": allocation.name,
		"entitled": flt(allocation.total_leaves_allocated),
		"taken": flt(allocation.total_leaves_allocated) - balance,
		"balance": balance,
		"from_date": allocation.from_date,
		"to_date": allocation.to_date,
	}


@frappe.whitelist()
def get_leave_salary_preview(employee, days):
	"""Priced breakdown for the form: which components, over how long a month, and why."""
	assert_employee_access(employee)
	return compute_leave_salary(employee, flt(days))


@frappe.whitelist()
def get_leave_application_details(leave_application):
	"""Dates and days of a Leave Application, so HR picks it instead of retyping it."""
	details = frappe.db.get_value(
		"Leave Application",
		leave_application,
		["employee", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
		as_dict=True,
	)
	if not details:
		return {}

	assert_employee_access(details.employee)
	return details
