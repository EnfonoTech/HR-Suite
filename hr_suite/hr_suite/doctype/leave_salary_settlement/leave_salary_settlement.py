# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

"""Leave Salary Settlement: pay an employee going on annual leave, in advance.

Built from the approved Leave Application. It prices, from the country policy and the employee's
ledger, what is owed before the leave starts:

  * the leave salary for the earned leave-salary days - sum of the policy's salary components
    / 30 x days - but only once BOTH minimums are met (earned salary days and service from
    joining). Below the barrier the shortfall is shown and no leave salary is paid; only a user
    with the HR Leave Override role can pay below it, with a reason;
  * the air ticket where one is due, less anything an Annual Leave Disbursement already paid.

Only EARNED salary days are paid. A partial payout is allowed and the balance still due stays on
the document, released by a further settlement once more days are earned.

Only the leave salary (and ticket) is separate from payroll. The salary for the days the employee
works, including the days worked in the month before the leave, stays in normal payroll: nothing
is paid for them here.

The accounts: submitting posts ONE Journal Entry, debit the company's mapped Leave Salary Expense,
credit its mapped Leave Salary Payable, tagged to the Employee (Hr Suite Settings > HR Account
Mappings, per company; nothing is guessed). The HR Payment Advice is the HR request and approval;
Finance clears that payable with a Payment Entry created from the advice, and the advice turns Paid
only when the entries cover it. No bank line is posted here.

Payroll: the leave days are not paid again. The Salary Slip leaves them out of its payment days
(hr_suite.overrides.salary_slip), not as leave without pay and with no Additional Salary rows, and
pays the days after the leave only once the return is confirmed (Record Rejoin) or attendance
exists. Settlements made before this design keep the payroll deductions they booked.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, cstr, date_diff, flt, formatdate, get_first_day, get_last_day, getdate

from hr_suite.hr_suite import leave_payroll as payroll
from hr_suite.hr_suite.leave_accrual import OVERRIDE_ROLE, get_salary_days_balance
from hr_suite.hr_suite.payment_advice import assert_no_live_advice
from hr_suite.hr_suite.policy import LEDGER_ENGINE, get_policy
from hr_suite.hr_suite.utils import (
	compute_leave_salary,
	get_employee_salary_components,
	journal_entry_needs_approval,
	split_days_by_month,
)

MONEY = 3
STANDARD_MONTH = 30.0
ANNUAL = "Annual Leave"
FINAL = "Final Settlement"


# ── pure pricing ──────────────────────────────────────────────────────────────


def price_settlement(
	*,
	leave_days,
	paid_days_before,
	earned_balance,
	min_earned,
	service_days,
	min_service,
	below_barrier_allowed,
	monthly_gross,
	days_worked,
	pays_worked_days,
	is_first,
	leave_monthly,
	days_per_month,
	ticket_due,
	ticket_amount,
	previously_paid,
):
	"""Everything a settlement pays, from plain numbers. Pure.

	Only the first settlement of a leave pays the worked days and the ticket; a later one
	releases salary days earned since.
	"""
	due = max(flt(leave_days) - flt(paid_days_before), 0.0)
	eligible = flt(earned_balance) >= flt(min_earned) and cint(service_days) >= cint(min_service)

	shortfall = []
	if flt(earned_balance) < flt(min_earned):
		shortfall.append(_("earned salary days {0} of the {1} needed").format(flt(earned_balance, 2), flt(min_earned, 2)))
	if cint(service_days) < cint(min_service):
		shortfall.append(_("service {0} of the {1} days needed").format(cint(service_days), cint(min_service)))

	can_pay = eligible or below_barrier_allowed
	paid_days = min(due, max(flt(earned_balance), 0.0)) if can_pay else 0.0

	worked_pay = (
		flt(flt(monthly_gross) * min(flt(days_worked), STANDARD_MONTH) / STANDARD_MONTH, MONEY)
		if (pays_worked_days and is_first)
		else 0.0
	)
	# monthly / days-per-month x days, never a rounded daily rate x days: 4,000 over 30 days for
	# 30 days must come to 4,000.000, not 3,999.999.
	leave_salary = flt(flt(leave_monthly) / (flt(days_per_month) or STANDARD_MONTH) * paid_days, MONEY)
	ticket = flt(ticket_amount, MONEY) if (ticket_due and is_first) else 0.0
	already = flt(previously_paid, MONEY) if is_first else 0.0

	return frappe._dict(
		due=flt(due, 2),
		eligible=int(eligible),
		shortfall=", ".join(shortfall),
		paid_days=flt(paid_days, 2),
		unpaid_days=flt(due - paid_days, 2),
		worked_pay=worked_pay,
		leave_salary=leave_salary,
		ticket=ticket,
		previously_paid=already,
		total=flt(max(worked_pay + leave_salary + ticket - already, 0.0), MONEY),
	)


# ── the document ──────────────────────────────────────────────────────────────


class LeaveSalarySettlement(Document):
	def validate(self):
		self.settlement_type = self.settlement_type or ANNUAL
		if self._is_final():
			self._prepare_final()
		else:
			self._pull_leave_application()
		self._require_ledger_engine()
		self._guard_one_open_draft()
		self._price()

	def before_submit(self):
		if flt(self.total_payable) <= 0 and flt(self.salary_days_due) <= 0:
			frappe.throw(
				_("Nothing to settle: no leave days are left unpaid on this leave, and no salary or ticket is due."),
				title=_("Nothing To Settle"),
			)

	def on_submit(self):
		self.status = "Approved"
		self.db_set("status", "Approved")
		self._post_ledger_row()
		if not self._is_final():
			self._post_accrual()
		refresh_stage(self.name)
		# The payment advice follows on its own, once this submit has committed: raising a second
		# submittable document inside this transaction is how a payroll run died once.
		if flt(self.total_payable) > 0:
			frappe.enqueue(
				"hr_suite.hr_suite.payment_advice.raise_after_submit",
				queue="short",
				enqueue_after_commit=True,
				job_id="hrs_advice_{0}".format(self.name),
				deduplicate=True,
				doctype=self.doctype,
				name=self.name,
			)

	def before_cancel(self):
		assert_no_live_advice(self)

	def on_cancel(self):
		payroll.cancel_deductions(_rejoin_record(self).get("deductions"))
		payroll.cancel_deductions([row["name"] for row in payroll.load_json(self.exclusion_rows)])
		payroll.cancel_deductions([row["name"] for row in payroll.load_json(self.earning_rows)])
		payroll.cancel_deductions([row["name"] for row in payroll.load_json(self.recovery_rows)])
		payroll.cancel_deductions(payroll.load_json(self.reversal_rows))
		self._cancel_accrual()
		self._reverse_ledger_rows()
		self.status = "Cancelled"
		self.db_set(
			{
				"status": "Cancelled", "exclusion_rows": "", "rejoin_rows": "", "earning_rows": "", "recovery_rows": "",
				"reversal_rows": "", "payroll_stage": "Cancelled",
			},
			update_modified=False,
		)

	# ── inputs ────────────────────────────────────────────────────────────────

	def _is_final(self) -> bool:
		return self.settlement_type == FINAL

	def _prepare_final(self):
		"""A Final Settlement has no leave: it pays what is accrued and unused on the last day."""
		for field in ("leave_application", "leave_type", "leave_from_date", "leave_to_date"):
			self.set(field, None)
		if not self.last_working_day:
			self.last_working_day = frappe.db.get_value("Employee", self.employee, "relieving_date")
		if not self.last_working_day:
			frappe.throw(
				_("Enter the last working day: {0} has no relieving date on the Employee.").format(
					self.employee_name or self.employee
				),
				title=_("Last Working Day"),
			)

	def _pull_leave_application(self):
		application = frappe.db.get_value(
			"Leave Application",
			self.leave_application,
			["employee", "leave_type", "from_date", "to_date", "total_leave_days", "docstatus", "status"],
			as_dict=True,
		)
		if not application:
			frappe.throw(_("Leave Application {0} was not found.").format(self.leave_application))
		if application.employee != self.employee:
			frappe.throw(
				_("Leave Application {0} belongs to {1}, not to {2}.").format(
					self.leave_application, application.employee, self.employee
				),
				title=_("Wrong Employee"),
			)
		if application.docstatus != 1 or application.status != "Approved":
			frappe.throw(_("Leave Application {0} is not approved.").format(self.leave_application), title=_("Not Approved"))

		self.leave_type = application.leave_type
		self.leave_from_date = application.from_date
		self.leave_to_date = application.to_date
		self.leave_days = flt(application.total_leave_days)
		if not self.last_working_day:
			self.last_working_day = add_days(application.from_date, -1)
		if getdate(self.last_working_day) >= getdate(application.from_date):
			frappe.throw(
				_("The last working day must be before the leave starts on {0}.").format(application.from_date),
				title=_("Last Working Day"),
			)

	def _require_ledger_engine(self):
		self._policy = get_policy(self.employee, on_date=self.last_working_day)
		if not self._policy.get("has_policy") or self._policy.leave_accrual_engine != LEDGER_ENGINE:
			frappe.throw(
				_("{0}'s country is not on the HR Suite Ledger accrual engine, so there is no earned leave-salary "
				  "balance to settle against. Switch it on in Country Config after importing opening balances.").format(
					self.employee_name or self.employee
				),
				title=_("Ledger Engine Required"),
			)
		self.country = self._policy.country_code
		if not self._is_final() and self.leave_type and self.leave_type != self._policy.annual_leave_type:
			frappe.throw(
				_("A Leave Salary Settlement is for annual leave ({0}). {1} is {2}, which does not advance leave salary.").format(
					self._policy.annual_leave_type, self.leave_application, self.leave_type
				),
				title=_("Not Annual Leave"),
			)

	def _guard_one_open_draft(self):
		if self._is_final():
			scope = {"employee": self.employee, "settlement_type": FINAL}
		else:
			scope = {"leave_application": self.leave_application}
		other = frappe.db.exists(
			"Leave Salary Settlement",
			{**scope, "docstatus": 0, "name": ["!=", self.name or ""]},
		)
		if other:
			frappe.throw(
				_("{0} is already a draft settlement for this {1}. Submit or delete it first.").format(
					other, _("final settlement") if self._is_final() else _("leave")
				),
				title=_("Draft Exists"),
			)

	def _is_first(self, exclude_self=False):
		"""True while no EARLIER submitted settlement covers this leave application."""
		filters = {"leave_application": self.leave_application, "docstatus": 1}
		if exclude_self and self.name:
			filters["name"] = ["!=", self.name]
		return not frappe.db.exists("Leave Salary Settlement", filters)

	# ── pricing ───────────────────────────────────────────────────────────────

	def _price(self):
		policy = self._policy
		final = self._is_final()
		first = False if final else self._is_first(exclude_self=True)
		last_day = getdate(self.last_working_day)
		joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")

		salary = get_employee_salary_components(self.employee) or {}
		self.monthly_gross = flt(salary.get("total_salary"), MONEY)

		month_start = max(get_first_day(last_day), getdate(joining)) if joining else get_first_day(last_day)
		from hr_suite.hr_suite.gratuity import get_unpaid_days

		self.days_worked = flt(
			max(date_diff(last_day, month_start) + 1 - get_unpaid_days(self.employee, month_start, last_day), 0), 2
		)

		# Nothing for the days worked is paid here: they stay in normal payroll, which also means a month
		# that is complete before the leave begins is never touched by the settlement.
		self.pay_worked_days_in_settlement = 0
		self.min_earned_days = flt(policy.leave_salary_min_earned_days)
		self.min_service_days = cint(policy.leave_salary_min_service_days)
		self.earned_salary_days = get_salary_days_balance(self.employee)
		self.service_days = date_diff(last_day, getdate(joining)) if joining else 0

		# On exit the accrued days are paid whatever the service, unless the country says otherwise.
		waived = final and cint(policy.leave_salary_pay_on_exit)
		if final:
			self.leave_days = flt(max(self.earned_salary_days, 0.0), 2)

		per_month = flt(policy.leave_salary_days_per_month) or STANDARD_MONTH
		monthly = compute_leave_salary(self.employee, per_month)
		leave_monthly = flt(monthly["total"], MONEY)
		self.daily_leave_rate = flt(leave_monthly / per_month, 4)
		self.policy_basis = monthly["terms"]["basis"]

		self._default_ticket(policy, first)

		below_ok = self._below_barrier_allowed()
		result = price_settlement(
			leave_days=self.leave_days,
			paid_days_before=0.0 if final else self._salary_days_paid_before(),
			earned_balance=self.earned_salary_days,
			min_earned=0 if waived else self.min_earned_days,
			service_days=self.service_days,
			min_service=0 if waived else self.min_service_days,
			below_barrier_allowed=below_ok,
			monthly_gross=self.monthly_gross,
			days_worked=self.days_worked,
			pays_worked_days=self.pay_worked_days_in_settlement,
			is_first=first,
			leave_monthly=leave_monthly,
			days_per_month=per_month,
			ticket_due=cint(self.ticket_entitled),
			ticket_amount=self.ticket_amount,
			previously_paid=0.0 if final else self._previously_paid_by_disbursement(),
		)

		if not result.eligible and not below_ok:
			frappe.throw(
				_("Leave salary cannot be settled for {0} yet: {1}. It is paid once the minimum service is met"
				  "{2}.").format(
					self.employee_name or self.employee,
					result.shortfall,
					"" if final else _(", or by a user with the {0} role who records a reason").format(OVERRIDE_ROLE),
				),
				title=_("Minimum Service Not Met"),
			)

		self.eligible = result.eligible
		self.shortfall_note = result.shortfall
		self.salary_days_due = result.due
		self.salary_days_paid = result.paid_days
		self.salary_days_unpaid = result.unpaid_days
		self.worked_days_pay = result.worked_pay
		self.leave_salary_amount = result.leave_salary
		self.previously_paid = result.previously_paid
		self.total_payable = result.total

		self.set("pay_lines", [])
		if result.worked_pay:
			self.append("pay_lines", {"line_type": "Worked Days Salary", "amount": result.worked_pay,
				"description": _("{0} days worked this month of 30").format(flt(self.days_worked, 2))})
		if result.paid_days:
			self.append("pay_lines", {"line_type": "Leave Salary", "amount": result.leave_salary,
				"description": _("{0} earned salary days at {1}").format(result.paid_days, flt(self.daily_leave_rate, 2))})
		if result.ticket:
			self.append("pay_lines", {"line_type": "Air Ticket", "amount": result.ticket, "description": _("Annual air ticket")})
		if result.previously_paid:
			self.append("pay_lines", {"line_type": "Previously Paid", "amount": -result.previously_paid,
				"description": _("Already paid by Annual Leave Disbursement")})

	def _below_barrier_allowed(self) -> bool:
		if not cint(self.pay_below_barrier):
			return False
		if OVERRIDE_ROLE not in frappe.get_roles():
			frappe.throw(
				_("Only users with the {0} role can pay leave salary below the barrier.").format(OVERRIDE_ROLE),
				title=_("Not Permitted"),
			)
		if not (self.barrier_override_reason or "").strip():
			frappe.throw(_("Record the reason for paying below the barrier."), title=_("Reason Required"))
		return True

	def _default_ticket(self, policy, first):
		"""Air ticket from the employee's override block, on a new document only."""
		if not self.is_new() or not first:
			return
		annual = policy.get("annual") or frappe._dict()
		if not cint(annual.get("ticket_entitled")):
			return
		every = cint(annual.get("ticket_every_months"))
		if every:
			previous = frappe.get_all(
				"Leave Salary Settlement",
				filters={"employee": self.employee, "docstatus": 1, "ticket_amount": [">", 0]},
				fields=["leave_from_date"],
				order_by="leave_from_date desc",
				limit=1,
			)
			if previous and date_diff(self.leave_from_date, previous[0].leave_from_date) < every * 30:
				return
		self.ticket_entitled = 1
		self.ticket_amount = flt(annual.get("ticket_amount"), MONEY)

	def _salary_days_paid_before(self) -> float:
		rows = frappe.get_all(
			"Leave Salary Settlement",
			filters={"leave_application": self.leave_application, "docstatus": 1, "name": ["!=", self.name or ""]},
			fields=["salary_days_paid"],
		)
		return flt(sum(flt(r.salary_days_paid) for r in rows), 2)

	def _previously_paid_by_disbursement(self) -> float:
		"""Leave pay an Annual Leave Disbursement already handed over for this very leave."""
		if not frappe.db.exists("DocType", "Annual Leave Disbursement"):
			return 0.0
		rows = frappe.get_all(
			"Annual Leave Disbursement",
			filters={"leave_application": self.leave_application, "docstatus": 1, "status": ["!=", "Cancelled"]},
			fields=["total_leave_pay"],
		)
		return flt(sum(flt(r.total_leave_pay) for r in rows), MONEY)

	# ── ledger ────────────────────────────────────────────────────────────────

	def _post_ledger_row(self):
		if not flt(self.salary_days_paid):
			return
		remark = (
			_("Accrued leave paid on exit on {0}").format(formatdate(self.last_working_day))
			if self._is_final()
			else _("Leave salary settled for leave {0}").format(self.leave_application)
		)
		self._ledger(-flt(self.salary_days_paid), remark)

	def _ledger(self, salary_days, remarks, on_date=None):
		row = frappe.get_doc(
			{
				"doctype": "Leave Accrual Ledger",
				"employee": self.employee,
				"source": "Settlement",
				"period_end": on_date or self.last_working_day,
				"salary_days": flt(salary_days, 2),
				"reference_doctype": self.doctype,
				"reference_name": self.name,
				"remarks": remarks,
			}
		)
		row.flags.skip_hrms_sync = True
		row.insert(ignore_permissions=True)
		return row.name

	def _reverse_ledger_rows(self):
		rows = frappe.get_all(
			"Leave Accrual Ledger",
			filters={"reference_doctype": self.doctype, "reference_name": self.name, "source": "Settlement"},
			fields=["salary_days"],
		)
		net = flt(sum(flt(r.salary_days) for r in rows), 2)
		if net:
			self._ledger(-net, _("Reversal: {0} cancelled").format(self.name))

	# ── payroll ───────────────────────────────────────────────────────────────

	def _leave_days_by_month(self, leave_end):
		"""[(month_start, leave days)] for the leave up to leave_end, counted as the Leave Application counts them.

		The Leave Type's holiday setting decides whether a holiday inside the leave is a leave day, so
		this is the number of days the settlement pays, not the calendar days of the range. When the
		whole leave is covered the months add up to the application's own total (a half day included).
		"""
		from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days

		leave_from, leave_to = getdate(self.leave_from_date), getdate(leave_end)
		chunks = []
		for month_start, calendar_days in split_days_by_month(leave_from, leave_to):
			start = max(getdate(month_start), leave_from)
			end = min(get_last_day(month_start), leave_to)
			try:
				days = flt(get_number_of_leave_days(self.employee, self.leave_type, start, end, 0, None, None))
			except Exception:
				# no holiday list to count against: the calendar days are the best count there is
				days = flt(calendar_days)
			chunks.append([month_start, days])

		if chunks and getdate(leave_end) >= getdate(self.leave_to_date):
			chunks[-1][1] = max(flt(chunks[-1][1]) + flt(self.leave_days) - sum(flt(c[1]) for c in chunks), 0.0)
		return [(month_start, days) for month_start, days in chunks]

	def _desired_exclusions(self, leave_end):
		"""{month_start: (payroll_date, amount)} payroll must NOT pay, given the leave runs to leave_end."""
		policy = get_policy(self.employee, on_date=self.last_working_day)
		per_month = flt(policy.leave_salary_days_per_month) or 30.0
		gross = flt(self.monthly_gross)
		leave_from = getdate(self.leave_from_date)

		entries = {}
		if getdate(leave_end) >= leave_from:
			chunks = self._leave_days_by_month(leave_end)
			for month_start, amount in payroll.month_amounts(gross, per_month, chunks).items():
				entries[month_start] = [max(getdate(month_start), leave_from), amount]

		if flt(self.worked_days_pay) > 0:
			month = get_first_day(getdate(self.last_working_day))
			current = entries.get(month, [getdate(self.last_working_day), 0.0])
			entries[month] = [getdate(self.last_working_day), min(gross, flt(current[1] + flt(self.worked_days_pay), MONEY))]
		return entries

	def _sync_exclusions(self, leave_end=None):
		"""Make the booked payroll deductions match what payroll should skip. Idempotent.

		Only for a settlement made before the Salary Slip learned to leave settled leave days out of its
		payment days: it still carries the deductions it booked. A new one has none, and gets none.
		"""
		existing = {row["month"]: row for row in payroll.load_json(self.exclusion_rows)}
		if not existing:
			return
		desired = self._desired_exclusions(leave_end or self.leave_to_date)
		component, currency = payroll.prepare_component(
			self.employee, self.company, self._expense_account(), component=payroll.exclusion_component()
		)

		kept = []
		for month, row in existing.items():
			want = desired.get(getdate(month))
			if want and abs(flt(want[1]) - flt(row["amount"])) < 0.0005:
				kept.append(row)
				desired.pop(getdate(month))
			else:
				payroll.cancel_deductions([row["name"]])

		for month_start, (payroll_date, amount) in sorted(desired.items()):
			name = payroll.book_deduction(self, component, currency, payroll_date, amount)
			if name:
				kept.append({"name": name, "month": str(month_start), "amount": flt(amount, MONEY)})

		self.db_set("exclusion_rows", payroll.dump_json(kept), update_modified=False)

	def _accrual_accounts(self, kind="leave") -> tuple:
		"""(expense, payable) mapped for this company in Hr Suite Settings, for the leave salary or the air ticket.

		Nothing is guessed: an unmapped company is told what to map, because a guessed account is a wrong ledger
		nobody notices.
		"""
		from hr_suite.hr_suite.utils import (
			ACCOUNT_PURPOSE_AIR_TICKET_EXPENSE,
			ACCOUNT_PURPOSE_AIR_TICKET_PAYABLE,
			ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE,
			ACCOUNT_PURPOSE_LEAVE_SALARY_PAYABLE,
			get_mapped_account,
		)

		if kind == "ticket":
			expense_purpose, payable_purpose = ACCOUNT_PURPOSE_AIR_TICKET_EXPENSE, ACCOUNT_PURPOSE_AIR_TICKET_PAYABLE
			title = _("Air Ticket Accounts Not Mapped")
		else:
			expense_purpose, payable_purpose = ACCOUNT_PURPOSE_LEAVE_SALARY_EXPENSE, ACCOUNT_PURPOSE_LEAVE_SALARY_PAYABLE
			title = _("Leave Salary Accounts Not Mapped")

		expense = get_mapped_account(self.company, expense_purpose, "Expense")
		payable = get_mapped_account(self.company, payable_purpose, "Liability")
		if not expense or not payable:
			frappe.throw(
				_("Map the accounts for {0} first: Hr Suite Settings > HR Account Mappings, purposes '{1}' (an expense "
				  "account of {0}) and '{2}' (a liability account of {0}). Nothing was posted.").format(
					self.company, _(expense_purpose), _(payable_purpose)
				),
				title=title,
			)
		if frappe.get_cached_value("Account", payable, "account_type") != "Payable":
			frappe.throw(
				_("{0} is mapped as the {1} but its Account Type is not Payable, so the employee cannot be tagged on "
				  "it and the payable could not be tracked per employee. Set Account Type = Payable on it (Chart of "
				  "Accounts) and submit again.").format(payable, _(payable_purpose)),
				title=_("Payable Account Cannot Carry The Employee"),
			)
		return expense, payable

	def _accrual_parts(self, amount) -> list:
		"""[(kind, amount)] the total splits into: the air ticket on its own accounts, the rest as leave salary.

		Anything already paid comes off the leave salary first, so the ticket booked is the ticket the employee gets.
		"""
		ticket = sum(flt(row.amount) for row in (self.get("pay_lines") or []) if row.line_type == "Air Ticket")
		ticket = flt(min(max(ticket, 0.0), amount), MONEY)
		leave = flt(amount - ticket, MONEY)
		return [(kind, part) for kind, part in (("leave", leave), ("ticket", ticket)) if part > 0]

	def _post_accrual(self):
		"""Recognise the settlement once: debit expense, credit the employee-tagged payable. No bank line.

		The leave salary goes to the leave salary accounts and the air ticket to the air ticket accounts, so each
		expense shows what it really is. Idempotent: a settlement that already has its Journal Entry never posts a
		second one. Left in Draft where an approval workflow covers Journal Entry, so the settlement itself is never
		blocked.
		"""
		amount = flt(self.total_payable, MONEY)
		if amount <= 0 or self.accrual_journal_entry:
			return

		parts = self._accrual_parts(amount)
		accounts = {kind: self._accrual_accounts(kind) for kind, _part in parts}
		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		remark = _("Annual leave salary - {0} - {1} to {2} ({3} leave day(s)) - {4} {5} ({6})").format(
			self.employee_name or self.employee,
			formatdate(self.leave_from_date),
			formatdate(self.leave_to_date),
			flt(self.leave_days, 2),
			amount,
			currency,
			self.name,
		)
		rows = []
		for kind, part in parts:
			expense, payable = accounts[kind]
			expense_row = {"account": expense, "debit_in_account_currency": part}
			if cost_center:
				expense_row["cost_center"] = cost_center
			rows.append(expense_row)
			rows.append(
				{
					"account": payable,
					"credit_in_account_currency": part,
					# the Employee master ID, so the ledger and the payment follow this employee
					"party_type": "Employee",
					"party": self.employee,
				}
			)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": self.company,
				"posting_date": frappe.utils.nowdate(),
				"user_remark": remark,
				"accounts": rows,
			}
		)
		needs_approval = journal_entry_needs_approval()
		je.insert(ignore_permissions=True)
		if not needs_approval:
			je.submit()
		self.db_set("accrual_journal_entry", je.name, update_modified=False)
		frappe.msgprint(
			_("Journal Entry <b>{0}</b> recognises the leave salary of {1} {2}{3}.").format(
				je.name, amount, currency, _(" and is waiting for approval") if needs_approval else ""
			),
			title=_("Leave Salary Accrued"),
			indicator="orange" if needs_approval else "green",
		)

	def _cancel_accrual(self):
		"""The settlement goes, so does its accrual: cancel it, or delete the draft nobody approved."""
		name = self.accrual_journal_entry
		if not name or not frappe.db.exists("Journal Entry", name):
			return
		docstatus = frappe.db.get_value("Journal Entry", name, "docstatus")
		if docstatus == 1:
			frappe.get_doc("Journal Entry", name).cancel()  # refused by ERPNext while a Payment Entry still clears it
		elif docstatus == 0:
			self.db_set("accrual_journal_entry", None, update_modified=False)
			frappe.delete_doc("Journal Entry", name, ignore_permissions=True)

	def _expense_account(self) -> str:
		from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
			resolve_leave_salary_accounts,
		)

		return resolve_leave_salary_accounts(self.company)[0]


# ── record the return from leave ──────────────────────────────────────────────


@frappe.whitelist()
def record_rejoin(name, rejoin_date):
	"""Record the day the employee came back, and adjust for an early or late return.

	Early: the unused leave-salary days are recovered at payroll and handed back to the
	earned balance, and the days after the rejoin date are no longer kept out of payroll.
	Late: the extra days are covered from the leave balance if there is one (HR records
	the extension as a Leave Application, which payroll then pays as leave) and are
	otherwise unpaid, deducted at payroll. Safe to run again with a corrected date.
	"""
	frappe.has_permission("Leave Salary Settlement", "write", doc=name, throw=True)
	doc = frappe.get_doc("Leave Salary Settlement", name)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the settlement before recording the return."), title=_("Not Submitted"))
	if doc.settlement_type == FINAL:
		frappe.throw(_("A final settlement has no leave to return from."), title=_("Final Settlement"))

	first = frappe.get_all(
		"Leave Salary Settlement",
		filters={"leave_application": doc.leave_application, "docstatus": 1},
		fields=["name", "salary_days_paid"],
		order_by="creation asc",
	)
	if first and first[0].name != doc.name:
		frappe.throw(
			_("Record the return on the first settlement for this leave, {0}: it holds the payroll adjustments.").format(first[0].name),
			title=_("Wrong Settlement"),
		)
	paid_total = flt(sum(flt(r.salary_days_paid) for r in first), 2)

	rejoin = getdate(rejoin_date)
	if rejoin <= getdate(doc.last_working_day):
		frappe.throw(_("The rejoin date must be after the last working day."), title=_("Invalid Date"))

	_undo_rejoin(doc)

	leave_from, leave_to = getdate(doc.leave_from_date), getdate(doc.leave_to_date)
	values = {
		"rejoin_date": rejoin,
		"actual_leave_days": 0,
		"unused_days": 0,
		"recovery_amount": 0,
		"extra_days": 0,
		"extension_days_covered": 0,
		"extra_days_unpaid": 0,
		"rejoin_note": "",
	}
	booked, notes = [], []
	policy = get_policy(doc.employee, on_date=doc.last_working_day)
	per_month = flt(policy.leave_salary_days_per_month) or 30.0
	component, currency = payroll.prepare_component(doc.employee, doc.company, doc._expense_account())

	if rejoin <= leave_to:
		unused = date_diff(leave_to, rejoin) + 1
		taken = max(date_diff(rejoin, leave_from), 0)
		values["actual_leave_days"] = flt(taken, 2)
		values["unused_days"] = flt(unused, 2)
		doc._sync_exclusions(leave_end=add_days(rejoin, -1))

		unused_paid = min(flt(unused), paid_total)
		recovery = flt(unused_paid * flt(doc.daily_leave_rate), MONEY)
		if recovery > 0 and cstr(doc.status) != "Paid" and not payroll.load_json(doc.exclusion_rows):
			# Nothing has left the bank yet, so there is nothing to take back from the payslip: the unused days'
			# share stays accrued until the advice is reduced or cancelled.
			values["unused_days"] = flt(unused, 2)
			notes.append(_("Returned {0} day(s) early. The advance has not been paid, so nothing is recovered at payroll: reduce or cancel the payment advice for the unused {1}.").format(unused, recovery))
			values["_restored"] = flt(unused_paid, 2)
		elif recovery > 0:
			name_ = payroll.book_deduction(doc, component, currency, rejoin, recovery)
			booked.append(name_)
			values["recovery_amount"] = recovery
			notes.append(_("Returned {0} day(s) early: {1} of leave salary recovered at payroll and {2} salary day(s) restored to the balance.").format(unused, recovery, flt(unused_paid, 2)))
			values["_restored"] = flt(unused_paid, 2)
		else:
			notes.append(_("Returned {0} day(s) early; no leave salary had been paid for them.").format(unused))
		notes.append(_("Shorten or cancel-and-amend the Leave Application so the unused leave days return to the balance."))
	else:
		values["actual_leave_days"] = flt(doc.leave_days, 2)
		doc._sync_exclusions(leave_end=leave_to)
		extra = date_diff(rejoin, leave_to) - 1
		if extra > 0:
			from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

			balance = max(flt(get_leave_balance_on(doc.employee, doc.leave_type, leave_to)), 0.0)
			covered = min(flt(extra), balance)
			unpaid = flt(extra) - covered
			values.update(extra_days=flt(extra, 2), extension_days_covered=flt(covered, 2), extra_days_unpaid=flt(unpaid, 2))
			if covered:
				notes.append(_("{0} extra day(s) fall inside the leave balance: record an extension Leave Application so payroll pays them as leave.").format(covered))
			if unpaid:
				start = add_days(leave_to, int(covered) + 1)
				chunks = split_days_by_month(start, add_days(rejoin, -1))
				amounts = payroll.month_amounts(flt(doc.monthly_gross), per_month, chunks)
				for month_start, amount in amounts.items():
					booked.append(payroll.book_deduction(doc, component, currency, max(getdate(month_start), getdate(start)), amount))
				notes.append(_("{0} extra day(s) are beyond the balance and unpaid: deducted at payroll.").format(unpaid))

	restored = values.pop("_restored", 0)
	rows = {"deductions": [b for b in booked if b], "restored": restored}
	if restored:
		doc._ledger(restored, _("Returned early: {0} salary day(s) restored").format(restored), on_date=rejoin)
	values["rejoin_note"] = "\n".join(notes)
	doc.db_set(values, update_modified=False)
	doc.db_set("rejoin_rows", payroll.dump_json(rows), update_modified=False)
	return values


def _undo_rejoin(doc):
	"""Reverse a previous rejoin record so a corrected date starts from a clean slate."""
	rows = _rejoin_record(doc)
	if not rows.get("deductions") and not flt(rows.get("restored")):
		return
	payroll.cancel_deductions(rows.get("deductions"))
	if flt(rows.get("restored")):
		doc._ledger(-flt(rows["restored"]), _("Rejoin corrected: restored days withdrawn"), on_date=doc.rejoin_date)
	doc.db_set("rejoin_rows", "", update_modified=False)


def _rejoin_record(doc) -> dict:
	"""What the last rejoin booked: {"deductions": [names], "restored": salary days}."""
	record = payroll.load_json(doc.rejoin_rows)
	return record if isinstance(record, dict) else {"deductions": record or [], "restored": 0}


# ── where the settlement stands ───────────────────────────────────────────────


def refresh_stage(name):
	"""Write where the settlement stands in: Approved > Accrual Posted > Payment Advice Created >
	Partially Paid > Payment Completed. Plain column write: the document is submitted."""
	row = frappe.db.get_value(
		"Leave Salary Settlement",
		name,
		["docstatus", "status", "payment_advice", "accrual_journal_entry", "payment_advice_type"],
		as_dict=True,
	)
	if not row or row.docstatus == 0:
		return ""
	if row.docstatus == 2:
		stage = "Cancelled"
	elif row.status == "Paid":
		stage = "Payment Completed"
	elif row.payment_advice and row.payment_advice_type == "HR Payment Advice" and flt(
		frappe.db.get_value("HR Payment Advice", row.payment_advice, "amount_paid")
	) > 0:
		stage = "Partially Paid"
	elif row.payment_advice:
		stage = "Payment Advice Created"
	elif row.accrual_journal_entry:
		stage = "Accrual Posted"
	else:
		stage = "Approved"
	frappe.db.set_value("Leave Salary Settlement", name, "payroll_stage", stage, update_modified=False)
	return stage


# ── helpers for the Leave Application button ──────────────────────────────────


@frappe.whitelist()
def make_from_leave_application(leave_application):
	"""A new, unsaved settlement for an approved Leave Application (the form's starting values)."""
	frappe.has_permission("Leave Application", "read", doc=leave_application, throw=True)
	frappe.has_permission("Leave Salary Settlement", "create", throw=True)
	la = frappe.db.get_value(
		"Leave Application", leave_application, ["employee", "employee_name", "company", "from_date"], as_dict=True
	)
	return {
		"doctype": "Leave Salary Settlement",
		"employee": la.employee,
		"employee_name": la.employee_name,
		"company": la.company,
		"leave_application": leave_application,
		"last_working_day": add_days(la.from_date, -1),
	}


def set_leave_application_onload(doc, method=None):
	"""Tell the Leave Application form whether it may start a settlement: approved annual leave only."""
	if doc.docstatus != 1 or doc.status != "Approved":
		return
	policy = get_policy(doc.employee, on_date=doc.from_date)
	doc.set_onload("hrs_can_settle_leave_salary", int(bool(policy.get("has_policy")) and doc.leave_type == policy.annual_leave_type))
