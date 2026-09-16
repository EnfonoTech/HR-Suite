# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Salary Settlement — pay an employee what they have earned, on any day of the month.

HRMS v15 has no off-cycle payroll. When somebody flies on the 12th they are paid by
hand, outside the system, and the month's payslip does not know it happened — so the
month's payroll pays those twelve days a second time.

Three rules hold this document together. Breaking any one of them pays somebody twice.

1. **Pro-ration is payroll's, not ours.** Earned salary is
   ``amount x payment_days / total_working_days`` per calendar month, with the days
   counted exactly as ``SalarySlip.get_working_days_details``
   (hrms/payroll/doctype/salary_slip/salary_slip.py:445-510) counts them, honouring
   Payroll Settings → Include Holidays In Total Working Days. Components that are not
   ``depends_on_payment_days`` are not scaled, because the Salary Slip does not scale
   them either (salary_slip.py:1843-1852). The component figures come from the
   Employee salary mirror, which is written by asking HRMS to evaluate the structure,
   so a structure built on formulas cannot drift away from the payslip.

2. **What is advanced is recovered; what payroll already collects is not deducted.**
   The recovery Additional Salary is sized to the GROSS advanced, never to the net.
   Sizing it to the net silently refunds every deduction taken here: the arithmetic
   comes out at ``full month − deductions payroll already had``, and the loan
   instalment or penalty taken out of the cash today reappears on the payslip as if it
   had never been collected. For the same reason the only deductions netted here are
   the ones NO payslip will collect — which is exactly the set Payroll Preview's own
   collectors return. Everything already booked into payroll is listed as Information.

3. **Deductions are read through Payroll Preview, never re-queried.** Two independent
   readings of loans, advances and penalties drift the first time one of them learns a
   new exclusion, and a settlement that disagrees with the Payroll Preview is the
   defect this screen exists to prevent. A transient Payroll Preview is built and its
   collectors are called; it is never saved.

Leave salary is the one figure this document does not advance. A submitted Annual
Leave Disbursement has already posted its own Journal Entry and has already booked its
own per-month recovery (annual_leave_disbursement.py
``_create_recovery_additional_salaries``). Settling it here therefore discharges a
liability that already exists — the Journal Entry DEBITS Salary Payable for it — and
books no second recovery.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_days,
	cint,
	cstr,
	date_diff,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	get_link_to_form,
	getdate,
	nowdate,
	today,
)

from hr_suite.hr_suite.doctype.payroll_preview.payroll_preview import (
	DEDUCTION,
	EARNING,
	INFORMATION,
)
from hr_suite.hr_suite.utils import (
	assert_doctype_permissions,
	assert_employee_access,
	journal_entry_needs_approval,
)

# The deduction that claws a settlement back off the payslip for the month it covered.
SETTLEMENT_RECOVERY_COMPONENT = "Salary Settlement Recovery"

SETTLEMENT_PAYROLL_ERROR_TITLE = "HR Suite: settlement not recovered at payroll"

# BHD and OMR are 3-decimal currencies and this app runs in both, so the day-count
# ratio is carried well past 2 places before it multiplies a salary.
_FACTOR_PRECISION = 6

# Annual Leave Disbursement states that still owe the employee money.
_ALD_UNSETTLED = ("Draft", "Approved")


class SalarySettlement(Document):
	# ── lifecycle ─────────────────────────────────────────────────────────────

	def validate(self):
		self._fill_in_the_blanks()
		self._validate_period()
		self._clamp_to_employment()
		self._validate_salary_structure()
		self._validate_no_overlap()
		self._build_lines()
		self._recalculate_totals()

	def before_submit(self):
		# Set here rather than by db_set in on_submit: a status written after the submit
		# save has already persisted leaves the document reading "Draft" to anyone who
		# looked in between, and a submit that throws later leaves it reading "Draft"
		# for good.
		self.status = "Awaiting Journal Approval" if journal_entry_needs_approval() else "Posted"

	def on_submit(self):
		self._book_payroll_recovery()
		self._create_settlement_journal_entry()
		self._mark_leave_disbursement_settled()

	def before_cancel(self):
		self.status = "Cancelled"

	def on_cancel(self):
		# Recovery rows first, and deliberately. Frappe refuses to cancel an Additional
		# Salary a SUBMITTED Salary Slip has already taken, and that refusal has to stop
		# the whole cancellation: the advance was recovered on a payslip, so the
		# settlement it recovered is no longer something that can be undone here.
		self._cancel_payroll_recovery()
		self._cancel_settlement_journal_entry()
		self._release_leave_disbursement()
		self.db_set("recovery_booked", 0, update_modified=False)

	# ── defaults and refusals ─────────────────────────────────────────────────

	def _fill_in_the_blanks(self):
		"""Named away from _set_defaults on purpose: that is a real Document method
		(frappe/model/document.py:833) which frappe calls before every insert and every
		save, and overriding it stops every field default in the JSON from ever applying.
		"""
		if not self.settlement_date:
			self.settlement_date = today()

		if not self.period_from:
			self.period_from = get_first_day(self.settlement_date)

		if not self.period_to:
			self.period_to = self.settlement_date

		if self.company:
			self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

		# fetch_from fills this on the form, but a settlement raised from the API or a
		# test arrives without it, and it is what every line row and every refusal
		# message names the person by.
		if self.employee and not self.employee_name:
			self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")

	def _validate_period(self):
		period_from = getdate(self.period_from)
		period_to = getdate(self.period_to)
		settlement_date = getdate(self.settlement_date)

		if period_to < period_from:
			frappe.throw(_("Period To cannot fall before Period From."), title=_("Invalid Period"))

		if settlement_date < period_from:
			frappe.throw(
				_("Settlement Date {0} falls before the period starts on {1}. Nothing has been "
				  "earned yet, so there is nothing to settle.").format(
					formatdate(settlement_date), formatdate(period_from)
				),
				title=_("Invalid Settlement Date"),
			)

		if settlement_date > period_to:
			frappe.throw(
				_("Settlement Date {0} falls after Period To {1}. Extend the period, or settle "
				  "on a day inside it.").format(formatdate(settlement_date), formatdate(period_to)),
				title=_("Invalid Settlement Date"),
			)

	def _clamp_to_employment(self):
		"""Never earn salary for a day outside employment.

		Payroll clamps the same window (hrms ``get_payroll_dates_for_employee``,
		payroll_entry.py:1219). Without it a period opening before the joining date pays
		for days nobody worked, and the recovery then takes back more than the payslip for
		that month will ever pay — the employee ends the month owing money.

		The dates the user typed are left alone. It is the EARNING window that moves, and
		the proration basis says so, because a settlement that silently rewrote its own
		period would be impossible to reconcile against the cash that left the bank.
		"""
		self._earned_from = getdate(self.period_from)
		self._earned_to = getdate(self.settlement_date)
		self._clamp_note = ""

		dates = frappe.db.get_value(
			"Employee", self.employee, ["date_of_joining", "relieving_date"], as_dict=True
		) or frappe._dict()

		joining = getdate(dates.date_of_joining) if dates.date_of_joining else None
		relieving = getdate(dates.relieving_date) if dates.relieving_date else None

		notes = []
		if joining and joining > self._earned_from:
			self._earned_from = joining
			notes.append(_("Earning starts on the joining date {0}.").format(formatdate(joining)))

		if relieving and relieving < self._earned_to:
			self._earned_to = relieving
			notes.append(_("Earning stops on the relieving date {0}.").format(formatdate(relieving)))

		if self._earned_to < self._earned_from:
			frappe.throw(
				_("{0} was not employed between {1} and {2}, so nothing was earned to settle.").format(
					self.employee_name or self.employee,
					formatdate(self.period_from),
					formatdate(self.settlement_date),
				),
				title=_("Outside Employment"),
			)

		self._clamp_note = " ".join(notes)

	def _validate_salary_structure(self):
		"""No submitted Salary Structure Assignment means no figure to pro-rate.

		Every amount below is a fraction of what the structure pays. Without an
		assignment the settlement would hand over nothing and still book a recovery, and
		the employee would be short a month's pay on the payslip that followed.
		"""
		from hr_suite.hr_suite.employee_salary import get_current_assignment

		self._assignment = get_current_assignment(self.employee, self.settlement_date)
		if self._assignment:
			self._validate_currency()
			return

		frappe.throw(
			_("{0} has no submitted Salary Structure Assignment in force on {1}, so there is "
			  "no salary to pro-rate. Assign a Salary Structure before settling.").format(
				self.employee_name or self.employee, formatdate(self.settlement_date)
			),
			title=_("No Salary Structure Assignment"),
		)

	def _validate_currency(self):
		"""The payslip and the ledger have to be talking about the same money.

		The recovery Additional Salary is stamped with the employee's PAYROLL currency,
		while the Journal Entry posts in the company's own. Where those differ the
		payslip claws back 400 dollars against a 400-dinar debit and the advance account
		never clears — so the settlement refuses rather than posting a figure that only
		looks right.
		"""
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		payroll_currency = cstr((self._assignment or {}).get("currency")) or company_currency

		if payroll_currency == company_currency:
			return

		frappe.throw(
			_(
				"{0} is paid in {1} while {2} keeps its books in {3}. A settlement across two "
				"currencies would post one figure to the ledger and recover another at payroll. "
				"Settle this by hand, or assign a salary structure in {3}."
			).format(
				self.employee_name or self.employee, payroll_currency, self.company, company_currency
			),
			title=_("Currency Mismatch"),
		)

	def _validate_no_overlap(self):
		"""One period, one settlement.

		Two settlements over the same days pay those days twice and then compete for one
		payslip to recover from — the second recovery finds the net already gone.
		"""
		Settlement = frappe.qb.DocType("Salary Settlement")

		query = (
			frappe.qb.from_(Settlement)
			.select(Settlement.name, Settlement.period_from, Settlement.period_to)
			.where(
				(Settlement.docstatus == 1)
				& (Settlement.employee == self.employee)
				& (Settlement.period_from <= getdate(self.period_to))
				& (Settlement.period_to >= getdate(self.period_from))
			)
			.limit(1)
		)
		if self.name:
			query = query.where(Settlement.name != self.name)

		clash = query.run(as_dict=True)
		if not clash:
			return

		existing = clash[0]
		frappe.throw(
			_("{0} already settles {1} between {2} and {3}. Cancel it before settling the same "
			  "days again.").format(
				get_link_to_form("Salary Settlement", existing.name),
				self.employee_name or self.employee,
				formatdate(existing.period_from),
				formatdate(existing.period_to),
			),
			title=_("Period Already Settled"),
		)

	# ── the lines ─────────────────────────────────────────────────────────────

	def _build_lines(self):
		self.set("lines", [])
		self._add_earned_salary_lines()
		self._add_leave_salary_lines()
		self._add_deduction_lines()

	def _append_line(self, **kwargs):
		row = self.append("lines", {"employee": self.employee, "employee_name": self.employee_name})
		row.update(kwargs)
		return row

	def _add_earned_salary_lines(self):
		"""Salary earned between Period From and Settlement Date, month by month."""
		components = self._salary_components()
		months = self._month_factors()

		self.earned_days = flt(sum(flt(month.payment_days) for month in months), 2)
		basis = [month.basis for month in months]
		if self._clamp_note:
			basis.append(self._clamp_note)
		self.proration_basis = "\n".join(basis)

		assignment = self._assignment or {}
		for month in months:
			for component in components:
				amount = flt(component.amount)
				if amount <= 0:
					continue

				common = dict(
					salary_component=component.salary_component,
					amount=amount,
					posting_date=month.chunk_end,
					source_doctype="Salary Structure Assignment",
					source_name=assignment.get("name"),
					origin_doctype="Salary Structure",
					origin_name=assignment.get("salary_structure"),
				)

				if component.component_type != EARNING:
					# The month's own payslip charges this deduction over the FULL month.
					# Taking it out of the settlement as well would charge it twice, and the
					# recovery is sized to the gross precisely so that it cannot.
					self._append_line(
						entry_type=INFORMATION,
						payable_amount=0,
						description=_(
							"Structure deduction. The payslip for {0} charges it on the full "
							"month, so it is not taken out of this settlement."
						).format(formatdate(month.month_start, "MMM yyyy")),
						**common,
					)
					continue

				scaled = cint(component.depends_on_payment_days)
				payable = amount * flt(month.factor) if scaled else amount

				if scaled:
					description = _("{0}: {1} of {2} days.").format(
						formatdate(month.month_start, "MMM yyyy"),
						flt(month.payment_days, 2),
						flt(month.total_working_days, 2),
					)
				else:
					description = _(
						"{0}: paid in full, this component does not depend on payment days."
					).format(formatdate(month.month_start, "MMM yyyy"))

				self._append_line(
					entry_type=EARNING,
					payable_amount=flt(payable, self.precision("net_payable")),
					description=description,
					**common,
				)

	def _salary_components(self) -> list:
		"""The employee's evaluated salary components, from the Employee mirror.

		The mirror is written by asking HRMS to build a throwaway Salary Slip
		(hr_suite/employee_salary.py), which is the only way a structure carrying
		formulas or conditions can be read without re-implementing payroll's arithmetic
		here — and re-implementing it is how a settlement starts disagreeing with the
		payslip that recovers it.
		"""
		fields = ["salary_component", "component_type", "amount", "depends_on_payment_days"]
		filters = {"parenttype": "Employee", "parent": self.employee}

		from hr_suite.hr_suite.employee_salary import sync_employee_salary

		# The mirror is only refreshed when an assignment is submitted, cancelled or
		# deleted, and always as at THAT day. A future-dated assignment therefore leaves
		# the mirror on the old rate until someone touches an assignment again — so a
		# settlement dated after the new rate took effect would pro-rate the old one and
		# pay the employee at a rate nobody is on. Rebuild whenever the mirror was not
		# written from the assignment that is in force on the settlement date.
		mirrored_from = frappe.db.get_value("Employee", self.employee, "custom_salary_effective_from")
		in_force_from = (self._assignment or {}).get("from_date")
		stale = bool(in_force_from) and getdate(mirrored_from) != getdate(in_force_from) if mirrored_from else True

		rows = (
			[]
			if stale
			else frappe.get_all(
				"Employee Salary Component", filters=filters, fields=fields, order_by="idx asc"
			)
		)
		if rows:
			return rows

		# Either the mirror is stale, or an employee whose structure was assigned before
		# the mirror existed has an empty one. Rebuilding it costs one throwaway slip and
		# keeps the settlement on the same figures as the Salary tab and Payroll Preview.
		sync_employee_salary(self.employee, self.settlement_date)
		rows = frappe.get_all(
			"Employee Salary Component", filters=filters, fields=fields, order_by="idx asc"
		)
		if rows:
			return rows

		frappe.throw(
			_("The salary structure assigned to {0} evaluates to no components, so there is "
			  "nothing to settle. Open the Employee and use Refresh Salary Snapshot to see "
			  "what the structure produces.").format(self.employee_name or self.employee),
			title=_("No Salary Components"),
		)

	def _month_factors(self) -> list:
		"""Payment days over total working days, per calendar month, payroll's way.

		``total_working_days`` is the WHOLE month and ``payment_days`` is the part of it
		this settlement claims — the same two numbers ``get_working_days_details``
		produces, so the recovery on the month's payslip lands on the same divisor.
		"""
		include_holidays = cint(
			frappe.db.get_single_value("Payroll Settings", "include_holidays_in_total_working_days")
		)

		from hr_suite.hr_suite.utils import split_days_by_month

		out = []
		chunk_start = getdate(self._earned_from)
		for month_start, days in split_days_by_month(self._earned_from, self._earned_to):
			chunk_end = add_days(chunk_start, cint(days) - 1)
			month_end = get_last_day(month_start)

			total_working_days = date_diff(month_end, month_start) + 1
			payment_days = date_diff(chunk_end, chunk_start) + 1

			if not include_holidays:
				total_working_days -= len(self._holiday_dates(month_start, month_end))
				payment_days -= len(self._holiday_dates(chunk_start, chunk_end))

			if total_working_days <= 0:
				# Mirrors the refusal in get_working_days_details (salary_slip.py:480): with
				# no working days there is no divisor, and no payslip either.
				frappe.throw(
					_("{0} has more holidays than working days, so no salary can be pro-rated "
					  "for it.").format(formatdate(month_start, "MMM yyyy")),
					title=_("No Working Days"),
				)

			payment_days = max(payment_days, 0)
			factor = flt(flt(payment_days) / flt(total_working_days), _FACTOR_PRECISION)

			basis = _(
				"{0}: {1} of {2} days ({3} to {4}). Holidays {5} in total working days."
			).format(
				formatdate(month_start, "MMM yyyy"),
				flt(payment_days, 2),
				flt(total_working_days, 2),
				formatdate(chunk_start),
				formatdate(chunk_end),
				_("counted") if include_holidays else _("not counted"),
			)

			out.append(
				frappe._dict(
					month_start=month_start,
					chunk_start=chunk_start,
					chunk_end=chunk_end,
					total_working_days=total_working_days,
					payment_days=payment_days,
					factor=factor,
					basis=basis,
				)
			)
			chunk_start = add_days(chunk_end, 1)

		return out

	def _holiday_dates(self, start_date, end_date) -> set:
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
		from hrms.utils.holiday_list import get_holiday_dates_between

		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=False)
		if not holiday_list:
			return set()

		return {getdate(date) for date in get_holiday_dates_between(holiday_list, start_date, end_date)}

	# ── leave salary ──────────────────────────────────────────────────────────

	def _add_leave_salary_lines(self):
		"""Leave salary already disbursed but not yet handed over.

		A submitted Annual Leave Disbursement posts its own Journal Entry to Salary
		Payable and books its own per-month recovery. So this settlement neither prices
		the leave nor recovers it — it discharges a liability that already exists, which
		is why the Journal Entry DEBITS Salary Payable for this part instead of the
		advance account. Booking a second recovery here would take the same leave off
		the payslip twice.
		"""
		self.annual_leave_disbursement = None

		disbursements = self._unsettled_leave_disbursements()
		if not disbursements:
			return

		first = disbursements[0]
		self.annual_leave_disbursement = first.name
		self._append_line(
			entry_type=EARNING,
			amount=flt(first.total_leave_pay),
			payable_amount=flt(first.total_leave_pay),
			posting_date=first.leave_from_date,
			source_doctype="Annual Leave Disbursement",
			source_name=first.name,
			description=_(
				"Leave salary for {0} to {1}, already booked to Salary Payable by the "
				"disbursement. Its own recovery is already on the payslips for those months, "
				"so this settlement books none."
			).format(formatdate(first.leave_from_date), formatdate(first.leave_to_date)),
		)

		for extra in disbursements[1:]:
			self._append_line(
				entry_type=INFORMATION,
				amount=flt(extra.total_leave_pay),
				payable_amount=0,
				posting_date=extra.leave_from_date,
				source_doctype="Annual Leave Disbursement",
				source_name=extra.name,
				description=_(
					"A second unsettled leave disbursement ({0} to {1}). One settlement "
					"discharges one disbursement — raise another for this."
				).format(formatdate(extra.leave_from_date), formatdate(extra.leave_to_date)),
			)

	def _unsettled_leave_disbursements(self) -> list:
		"""Submitted disbursements nobody has handed over or claimed yet."""
		rows = frappe.get_all(
			"Annual Leave Disbursement",
			filters={
				"docstatus": 1,
				"employee": self.employee,
				"company": self.company,
				"status": ("in", _ALD_UNSETTLED),
			},
			fields=["name", "leave_from_date", "leave_to_date", "total_leave_pay"],
			order_by="leave_from_date asc",
		)
		if not rows:
			return []

		claimed = self._leave_disbursements_claimed_elsewhere([row.name for row in rows])
		return [row for row in rows if row.name not in claimed and flt(row.total_leave_pay) > 0]

	def _leave_disbursements_claimed_elsewhere(self, names: list) -> set:
		Settlement = frappe.qb.DocType("Salary Settlement")

		query = (
			frappe.qb.from_(Settlement)
			.select(Settlement.annual_leave_disbursement)
			.where(
				(Settlement.docstatus == 1) & (Settlement.annual_leave_disbursement.isin(names))
			)
		)
		if self.name:
			query = query.where(Settlement.name != self.name)

		return set(query.run(pluck=True))

	# ── deductions, read through Payroll Preview ──────────────────────────────

	def _preview_reader(self):
		"""A transient Payroll Preview, used purely as the collector of record.

		Never saved, never inserted. Its collectors read only company / start_date /
		end_date off the document, and calling them is what guarantees a settlement and
		a Payroll Preview over the same window can never disagree about what this
		employee owes.
		"""
		preview = frappe.new_doc("Payroll Preview")
		preview.company = self.company
		preview.start_date = getdate(self.period_from)
		preview.end_date = getdate(self.settlement_date)
		return preview

	def _add_deduction_lines(self):
		preview = self._preview_reader()
		employee_ids = [self.employee]

		additional_salaries = preview._get_additional_salaries(employee_ids)
		self._add_additional_salary_lines(additional_salaries)
		self._add_loan_lines(preview._get_loan_installments(employee_ids), additional_salaries)
		self._add_penalty_lines(preview._get_employee_penalties(employee_ids, additional_salaries))
		self._add_advance_lines(preview._get_employee_advances(employee_ids, additional_salaries))
		self._add_salary_adjustment_lines(preview._get_salary_adjustments(employee_ids))

	def _add_additional_salary_lines(self, additional_salaries: list):
		"""Everything already booked into the month's payroll, as Information only.

		These rows reach the Salary Slip on their own. Taking a booked deduction out of
		the settlement cash as well charges it twice, and adding a booked earning to the
		settlement pays it twice — the payslip still carries both either way.
		"""
		for entry in additional_salaries:
			self._append_line(
				entry_type=INFORMATION,
				salary_component=entry.salary_component,
				amount=flt(entry.amount),
				payable_amount=0,
				posting_date=entry.payroll_date or entry.from_date,
				source_doctype="Additional Salary",
				source_name=entry.name,
				origin_doctype=entry.ref_doctype,
				origin_name=entry.ref_docname,
				description=_(
					"{0} already booked into payroll, so the payslip carries it. Not settled here."
				).format(cstr(entry.type) or _("Additional Salary")),
			)

	def _add_loan_lines(self, installments: list, additional_salaries: list):
		if not installments:
			return

		from hr_suite.hr_suite.doctype.employee_loan.employee_loan import (
			get_loan_salary_component_name,
		)

		booked_here = {cstr(row.name) for row in additional_salaries}
		component = get_loan_salary_component_name()
		account = self._component_account(component)

		for installment in installments:
			amount = flt(installment.outstanding_amount or installment.installment_amount)
			if amount <= 0:
				continue

			number = cint(installment.installment_number)
			common = dict(
				salary_component=component,
				amount=amount,
				posting_date=installment.due_date,
				source_doctype="Employee Loan",
				source_name=installment.loan,
				origin_doctype="Employee Loan Installment",
				origin_name=installment.installment,
			)

			if cstr(installment.additional_salary) in booked_here:
				self._append_line(
					entry_type=INFORMATION,
					payable_amount=0,
					description=_(
						"Instalment {0} due {1} is already booked into this period's payroll, so "
						"the payslip deducts it. Not settled here."
					).format(number, formatdate(installment.due_date)),
					**common,
				)
			elif not account:
				self._append_line(
					entry_type=INFORMATION,
					payable_amount=0,
					description=_(
						"Instalment {0} due {1} is not booked into payroll, and Salary Component "
						"{2} has no account for {3} — so it cannot be recovered from this "
						"settlement either. Map the account and settle again."
					).format(number, formatdate(installment.due_date), component, self.company),
					**common,
				)
			else:
				self._append_line(
					entry_type=DEDUCTION,
					payable_amount=amount,
					description=_(
						"Instalment {0} due {1} is not booked into payroll, so nothing else will "
						"collect it. Recovered from this settlement."
					).format(number, formatdate(installment.due_date)),
					**common,
				)

	def _add_penalty_lines(self, penalties: list):
		"""Penalties with no Additional Salary — the collector already dropped the rest."""
		if not penalties:
			return

		component = self._penalty_component()
		account = self._component_account(component)

		for penalty in penalties:
			amount = self._penalty_amount(penalty)
			if amount <= 0:
				continue

			common = dict(
				salary_component=component,
				amount=amount,
				posting_date=penalty.posting_date,
				source_doctype="Employee Penalty",
				source_name=penalty.name,
			)

			if not account:
				self._append_line(
					entry_type=INFORMATION,
					payable_amount=0,
					description=_(
						"Penalty {0} has no Additional Salary, and Salary Component {1} has no "
						"account for {2} — so it cannot be recovered here either."
					).format(cstr(penalty.penalty_type), component, self.company),
					**common,
				)
			else:
				self._append_line(
					entry_type=DEDUCTION,
					payable_amount=amount,
					description=_(
						"Penalty {0} ({1} day(s)) is not booked into payroll, so nothing else "
						"will collect it. Recovered from this settlement."
					).format(cstr(penalty.penalty_type), flt(penalty.penalty_value)),
					**common,
				)

	def _penalty_component(self) -> str:
		from hr_suite.hr_suite.doctype.employee_penalty.employee_penalty import (
			PENALTY_DEDUCTION_COMPONENT,
		)

		return (
			cstr(frappe.db.get_single_value("Hr Suite Settings", "penalty_salary_component")).strip()
			or PENALTY_DEDUCTION_COMPONENT
		)

	def _penalty_amount(self, penalty) -> float:
		"""A penalty is priced in days of pay — the arithmetic employee_penalty.py uses.

		employee_penalty.py prices its own Additional Salary as ``base / 30 x
		penalty_value`` (``_create_additional_salary``). Pricing it any other way here
		would make the settlement and the payslip disagree about the same penalty.
		"""
		base = flt((self._assignment or {}).get("base"))
		if base <= 0:
			return 0.0

		return flt(base / 30 * flt(penalty.penalty_value), self.precision("net_payable"))

	def _add_advance_lines(self, advances: list):
		if not advances:
			return

		accounts = {
			row.name: row.advance_account
			for row in frappe.get_all(
				"Employee Advance",
				filters={"name": ("in", [advance.name for advance in advances])},
				fields=["name", "advance_account"],
			)
		}

		for advance in advances:
			amount = flt(advance.pending_amount)
			if amount <= 0:
				continue

			account = cstr(accounts.get(advance.name))
			common = dict(
				amount=amount,
				posting_date=advance.posting_date,
				source_doctype="Employee Advance",
				source_name=advance.name,
			)

			if not account:
				self._append_line(
					entry_type=INFORMATION,
					payable_amount=0,
					description=_(
						"Employee Advance {0} has {1} outstanding but no advance account, so it "
						"cannot be recovered from this settlement."
					).format(advance.name, amount),
					**common,
				)
			else:
				self._append_line(
					entry_type=DEDUCTION,
					payable_amount=amount,
					description=_(
						"Outstanding employee advance ({0}), not yet booked into payroll. "
						"Recovered from this settlement."
					).format(cstr(advance.purpose) or advance.name),
					**common,
				)

	def _add_salary_adjustment_lines(self, adjustments: list):
		"""Always Information: an adjustment changes the Salary Structure Assignment.

		It is never a cash line, so netting it here would take money off the employee
		that nobody is owed.
		"""
		for adjustment in adjustments:
			self._append_line(
				entry_type=INFORMATION,
				amount=flt(adjustment.adjustment_amount),
				payable_amount=0,
				posting_date=adjustment.effective_date,
				source_doctype="Salary Adjustment",
				source_name=adjustment.name,
				description=_(
					"{0} effective {1} (status {2}). It changes the Salary Structure "
					"Assignment, not this settlement."
				).format(
					cstr(adjustment.adjustment_type),
					formatdate(adjustment.effective_date),
					cstr(adjustment.status),
				),
			)

	# ── totals ────────────────────────────────────────────────────────────────

	def _recalculate_totals(self):
		precision = self.precision("net_payable")

		self.leave_salary_amount = flt(
			sum(
				flt(line.payable_amount)
				for line in self.lines
				if line.entry_type == EARNING and line.source_doctype == "Annual Leave Disbursement"
			),
			precision,
		)
		self.earned_amount = flt(
			sum(
				flt(line.payable_amount)
				for line in self.lines
				if line.entry_type == EARNING and line.source_doctype != "Annual Leave Disbursement"
			),
			precision,
		)
		self.total_earnings = flt(self.earned_amount + self.leave_salary_amount, precision)
		self.total_deductions = flt(
			sum(flt(line.payable_amount) for line in self.lines if line.entry_type == DEDUCTION),
			precision,
		)
		self.net_payable = flt(self.total_earnings - self.total_deductions, precision)

		if self.net_payable < 0:
			# A negative net is not a payment, it is a claim on the employee — and nothing
			# here can collect it. The Journal Entry would balance itself by debiting
			# Salary Payable, i.e. the company would book money as owed to itself, while
			# the recovery still claws back only the gross earned and the deduction rows
			# would be marked collected against cash that never changed hands. Refusing is
			# the only honest answer: those deductions belong on the next payslip.
			frappe.throw(
				_(
					"{0} owes more over this period ({1}) than it earned ({2}), so the "
					"settlement would pay {3}. Nothing here can collect the difference — "
					"settle a longer period, or leave these deductions to payroll."
				).format(
					self.employee_name or self.employee,
					flt(self.total_deductions, precision),
					flt(self.total_earnings, precision),
					flt(self.net_payable, precision),
				),
				title=_("Nothing Left To Pay"),
			)

	# ── recovery at payroll ───────────────────────────────────────────────────

	def _book_payroll_recovery(self):
		"""One Additional Salary deduction per month this settlement advanced salary for.

		Sized to the GROSS advanced, never to the net. Sizing it to the net refunds every
		deduction taken here on the very next payslip — the employee ends up paying no
		loan instalment and no penalty at all, and both documents still add up.
		"""
		by_month = {}
		for line in self.lines:
			if line.entry_type != EARNING or line.source_doctype == "Annual Leave Disbursement":
				continue
			month_start = get_first_day(line.posting_date)
			by_month[month_start] = flt(by_month.get(month_start)) + flt(line.payable_amount)

		precision = self.precision("net_payable")
		by_month = {
			month: flt(amount, precision)
			for month, amount in by_month.items()
			if flt(amount, precision) > 0
		}
		if not by_month:
			return

		component, reason = self._prepare_recovery_component()
		if reason:
			# Refusing the submit is the safe failure. Handing over an advance without
			# booking its recovery pays the month twice, and nothing downstream catches it.
			frappe.throw(reason, title=_("Settlement Cannot Be Recovered"))

		from hr_suite.hr_suite.integrations.hrms import get_employee_payroll_currency

		currency = get_employee_payroll_currency(self.employee, self.settlement_date, self.company)
		if not currency:
			frappe.throw(
				_("{0} has no submitted Salary Structure Assignment, so the payroll currency is "
				  "unknown and the settlement cannot be recovered.").format(
					self.employee_name or self.employee
				),
				title=_("No Salary Structure"),
			)

		relieving = frappe.db.get_value("Employee", self.employee, "relieving_date")
		relieving = getdate(relieving) if relieving else None

		created = []
		for month_start, amount in sorted(by_month.items()):
			# The deduction has to land on the payslip for the month it advanced, so the
			# month end is the natural date — except for someone who has left, whose final
			# payslip is dated on their relieving date. Additional Salary refuses a payroll
			# date after that date outright (hrms additional_salary.py validate_dates), so
			# a final settlement could not be submitted at all without this clamp.
			payroll_date = get_last_day(month_start)
			if relieving and relieving < getdate(payroll_date):
				payroll_date = max(relieving, getdate(month_start))

			self._refuse_if_payroll_already_ran(payroll_date, amount)

			additional_salary = frappe.get_doc({
				"doctype": "Additional Salary",
				"employee": self.employee,
				"company": self.company,
				"currency": currency,
				"salary_component": component,
				"amount": amount,
				"payroll_date": payroll_date,
				"is_recurring": 0,
				# Never overwrite: the recovery is charged ON TOP of whatever the structure
				# already carries for this component.
				"overwrite_salary_structure_amount": 0,
				"deduct_full_tax_on_selected_payroll_date": 0,
				"ref_doctype": self.doctype,
				"ref_docname": self.name,
			})
			additional_salary.insert(ignore_permissions=True)
			additional_salary.submit()
			created.append(additional_salary.name)

		self.db_set("recovery_booked", 1, update_modified=False)
		frappe.msgprint(
			_("Booked {0} payroll deduction(s) so the month(s) this settlement covers net it "
			  "out: {1}.").format(len(created), ", ".join(created)),
			title=_("Recovery Booked"),
			indicator="green",
		)

	def _refuse_if_payroll_already_ran(self, payroll_date, amount):
		"""A month whose payslip is already submitted can never read this deduction.

		hrms only picks an Additional Salary up while building a Salary Slip. Booking a
		recovery into a month payroll has closed books an advance that is never taken
		back: the employee keeps both the settlement cash and the full payslip for that
		month, and no report anywhere flags it. Refusing the submit is the safe failure —
		the settlement can be raised against an open month instead, or the deduction
		entered on the next payroll by hand.
		"""
		slip = frappe.db.get_value(
			"Salary Slip",
			{
				"employee": self.employee,
				"docstatus": 1,
				"start_date": ["<=", payroll_date],
				"end_date": [">=", payroll_date],
			},
			["name", "start_date", "end_date"],
			as_dict=True,
		)
		if not slip:
			return

		frappe.throw(
			_(
				"Payroll for {0} has already been run — Salary Slip {1} covers {2} to {3} and "
				"is submitted, so a deduction of {4} dated {5} would never be taken. Settle a "
				"month payroll has not closed, or recover this by hand on the next payslip."
			).format(
				formatdate(payroll_date, "MMM yyyy"),
				slip.name,
				formatdate(slip.start_date),
				formatdate(slip.end_date),
				flt(amount, self.precision("net_payable")),
				formatdate(payroll_date),
			),
			title=_("Payroll Already Run"),
		)

	def _prepare_recovery_component(self) -> tuple:
		"""(component_name, reason). An empty `reason` means it is safe to post."""
		from hr_suite.hr_suite.integrations.hrms import ensure_salary_component_account

		ok, reason = ensure_salary_component_account(
			SETTLEMENT_RECOVERY_COMPONENT,
			self.company,
			component_type="Deduction",
			fallback_account=self._settlement_advance_account(),
			# The advance was a fixed sum of money. Scaling the recovery by the month's
			# payment days would take back less than was handed over — and a settled month
			# is by definition a month with unusual payment days.
			depends_on_payment_days=0,
			error_title=SETTLEMENT_PAYROLL_ERROR_TITLE,
		)
		return SETTLEMENT_RECOVERY_COMPONENT, ("" if ok else reason)

	def _cancel_payroll_recovery(self):
		for name in frappe.get_all(
			"Additional Salary",
			filters={"ref_doctype": self.doctype, "ref_docname": self.name, "docstatus": 1},
			pluck="name",
		):
			frappe.get_doc("Additional Salary", name).cancel()

		for name in frappe.get_all(
			"Additional Salary",
			filters={"ref_doctype": self.doctype, "ref_docname": self.name, "docstatus": 0},
			pluck="name",
		):
			# A draft recovery would still be submittable next week, taking money off a
			# payslip for a settlement that no longer exists.
			frappe.delete_doc("Additional Salary", name, ignore_permissions=True)

	# ── the Journal Entry ─────────────────────────────────────────────────────

	def _create_settlement_journal_entry(self):
		"""Post the settlement, under the same rules as Overtime Request.

		The debit is the ADVANCE, not an expense: the month's payroll accrual books the
		salary expense in full, and debiting it here as well would state the cost twice.
		The advance sits on the recovery component's own account until the payslip's
		deduction credits it away, which is why that account is read from the component
		rather than guessed out of the Chart of Accounts.
		"""
		if self.journal_entry:
			return

		if flt(self.total_earnings) <= 0 and flt(self.total_deductions) <= 0:
			return

		company = self.company
		currency = frappe.get_cached_value("Company", company, "default_currency")

		payable_account = self._payroll_payable_account()
		if not payable_account:
			# Throw, never warn. _book_payroll_recovery has already run by this point and
			# has an Additional Salary submitted against the next payslip: returning here
			# would leave a settlement marked Posted, with a deduction waiting at payroll,
			# for an advance the ledger never recorded. Throwing rolls the whole submit
			# back, recovery included.
			frappe.throw(
				_("Could not find a Salary Payable account for {0}. Set Default Payroll Payable "
				  "Account on the Company, or add a Payable account to the Chart of Accounts. "
				  "Nothing was posted.").format(company),
				title=_("Account Not Found"),
			)

		accounts = self._journal_entry_rows(payable_account)
		if not accounts:
			return

		# NOTE: do NOT set reference_type/reference_name on the accounts. `Journal Entry
		# Account.reference_type` is a Select with a fixed option list that does not include
		# "Salary Settlement", so setting it makes the Journal Entry unsubmittable:
		#   "Row #1: Reference Type cannot be 'Salary Settlement'."
		# The link back to this document is kept on `journal_entry` below, and the document
		# name is written into user_remark for the audit trail.
		remark = _("Salary Settlement — {0} — {1} to {2} ({3}) — net {4} {5} ({6})").format(
			self.employee_name or self.employee,
			formatdate(self.period_from),
			formatdate(self.settlement_date),
			cstr(self.reason),
			flt(self.net_payable),
			currency,
			self.name,
		)

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": self.settlement_date or nowdate(),
			"user_remark": remark,
			"accounts": accounts,
		})

		needs_approval = journal_entry_needs_approval()
		assert_doctype_permissions(
			"Journal Entry", ("create",) if needs_approval else ("create", "submit")
		)
		je.insert()

		# Submitting here while an approval workflow covers Journal Entry is refused, and
		# the refusal propagates out of on_submit — so the settlement itself could not be
		# submitted at all. Leave the entry in Draft for its approver instead; the
		# settlement is still recorded and still reaches the accounts once approved.
		if not needs_approval:
			je.submit()

		self.db_set("journal_entry", je.name, update_modified=False)
		if needs_approval:
			frappe.msgprint(
				_("Journal Entry <b>{0}</b> was created for a net settlement of {1} {2} and is "
				  "waiting for approval. It reaches the accounts once approved.").format(
					je.name, flt(self.net_payable), currency
				),
				title=_("Journal Entry awaiting approval"),
				indicator="orange",
			)
		else:
			frappe.msgprint(
				_("Journal Entry <b>{0}</b> created for a net settlement of {1} {2}.").format(
					je.name, flt(self.net_payable), currency
				),
				title=_("Journal Entry Created"),
				indicator="green",
			)

	def _journal_entry_rows(self, payable_account: str) -> list:
		"""Debit what was advanced, credit what was recovered, credit the net payable."""
		accounts = []

		if flt(self.earned_amount) > 0:
			advance_account = self._component_account(
				SETTLEMENT_RECOVERY_COMPONENT
			) or self._settlement_advance_account()
			if not advance_account:
				# Same reasoning as the payable account above: the payroll recovery is
				# already booked, so a silent return would strand it.
				frappe.throw(
					_("Salary Component {0} has no account for {1} and no salary advance account "
					  "could be found, so nothing was posted.").format(
						SETTLEMENT_RECOVERY_COMPONENT, self.company
					),
					title=_("Account Not Found"),
				)

			accounts.append(
				dict(
					account=advance_account,
					debit_in_account_currency=flt(self.earned_amount),
					**self._party_fields(advance_account),
				)
			)

		if flt(self.leave_salary_amount) > 0:
			# The disbursement already credited Salary Payable for this. Settling it moves
			# that liability into today's payout rather than creating a second one.
			accounts.append(
				dict(
					account=payable_account,
					debit_in_account_currency=flt(self.leave_salary_amount),
					**self._party_fields(payable_account),
				)
			)

		for account, amount in self._deduction_credit_rows().items():
			accounts.append(
				dict(
					account=account,
					credit_in_account_currency=flt(amount),
					**self._party_fields(account),
				)
			)

		if flt(self.net_payable) > 0:
			accounts.append(
				dict(
					account=payable_account,
					credit_in_account_currency=flt(self.net_payable),
					**self._party_fields(payable_account),
				)
			)
		elif flt(self.net_payable) < 0:
			# Unreachable from the desk: _recalculate_totals refuses a settlement whose
			# deductions exceed its earnings, because nothing here can collect the
			# difference. Kept as the balancing row so a document built in code — a test,
			# a migration — still produces an entry that balances rather than failing on
			# an accounting error nobody can read.
			accounts.append(
				dict(
					account=payable_account,
					debit_in_account_currency=abs(flt(self.net_payable)),
					**self._party_fields(payable_account),
				)
			)

		return accounts

	def _deduction_credit_rows(self) -> dict:
		"""{account: amount} for every netted deduction, keyed so one account posts once.

		Every Deduction line resolved an account during validate — that is precisely why
		a line whose account could not be found was demoted to Information there. A
		deduction arriving here without one would post an unbalanced entry, so it stops
		the submit instead.
		"""
		rows = {}
		for line in self.lines:
			if line.entry_type != DEDUCTION or flt(line.payable_amount) <= 0:
				continue

			account = self._deduction_account_for(line)
			if not account:
				frappe.throw(
					_("No account could be resolved for {0} {1}, so the settlement cannot be "
					  "posted. Save the settlement again and submit.").format(
						cstr(line.source_doctype), cstr(line.source_name)
					),
					title=_("Account Not Found"),
				)

			rows[account] = flt(rows.get(account)) + flt(line.payable_amount)

		return rows

	def _deduction_account_for(self, line) -> str:
		if line.source_doctype == "Employee Advance":
			return cstr(frappe.db.get_value("Employee Advance", line.source_name, "advance_account"))

		return self._component_account(line.salary_component)

	def _component_account(self, component: str) -> str:
		"""Strictly read-only: the Salary Component Account for this company, or "".

		It creates nothing, because validate() has to be able to ask the question without
		leaving a half-configured Salary Component behind on every draft save.
		"""
		if not component:
			return ""

		return cstr(
			frappe.db.get_value(
				"Salary Component Account",
				{"parent": component, "parenttype": "Salary Component", "company": self.company},
				"account",
			)
		)

	def _settlement_advance_account(self) -> str:
		"""An asset account the advance can sit on until payroll recovers it."""
		for filters in (
			{"company": self.company, "account_name": ["like", "%Salary Advance%"],
			 "root_type": "Asset", "is_group": 0},
			{"company": self.company, "account_name": ["like", "%Employee Advance%"],
			 "root_type": "Asset", "is_group": 0},
			{"company": self.company, "account_type": "Receivable", "is_group": 0},
		):
			account = frappe.db.get_value("Account", filters, "name")
			if account:
				return account

		return ""

	def _payroll_payable_account(self) -> str:
		return (
			cstr(frappe.db.get_value("Company", self.company, "default_payroll_payable_account"))
			or frappe.db.get_value(
				"Account",
				{"company": self.company, "account_name": ["like", "%Salary Payable%"],
				 "root_type": "Liability", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": self.company, "account_type": "Payable", "is_group": 0},
				"name",
			)
			or ""
		)

	def _party_fields(self, account: str) -> dict:
		"""Party only where the account type asks for it.

		A Receivable or Payable row with no party is refused outright by
		``JournalEntry.validate_party``; on any other account a party is noise that lands
		the employee in an AR/AP ageing they never traded in.
		"""
		account_type = frappe.db.get_value("Account", account, "account_type")
		if account_type in ("Receivable", "Payable"):
			return {"party_type": "Employee", "party": self.employee}

		return {}

	def _cancel_settlement_journal_entry(self):
		if not self.journal_entry:
			return
		if not frappe.db.exists("Journal Entry", self.journal_entry):
			self.db_set("journal_entry", None, update_modified=False)
			return

		je = frappe.get_doc("Journal Entry", self.journal_entry)
		if je.docstatus == 1:
			je.cancel()
			return

		if je.docstatus == 0:
			# A draft waiting for its approver has posted nothing yet, but an approver who
			# submits it next week would pay out a settlement that no longer exists. The
			# draft goes with the settlement, and the link goes with the draft: a Link field
			# pointing at a deleted document breaks every later save of this one.
			frappe.delete_doc("Journal Entry", je.name, ignore_permissions=True)
			self.db_set("journal_entry", None, update_modified=False)
			frappe.msgprint(
				_("The draft Journal Entry for this settlement was deleted, so it cannot be "
				  "approved after the settlement was cancelled."),
				indicator="orange",
			)

	# ── the leave disbursement this settlement discharged ─────────────────────

	def _mark_leave_disbursement_settled(self):
		if not self.annual_leave_disbursement:
			return
		if not self._leave_disbursement_has_paid_state():
			return

		frappe.db.set_value(
			"Annual Leave Disbursement",
			self.annual_leave_disbursement,
			"status",
			"Paid",
			update_modified=False,
		)

	def _release_leave_disbursement(self):
		if not self.annual_leave_disbursement:
			return
		if not frappe.db.exists("Annual Leave Disbursement", self.annual_leave_disbursement):
			return

		current = frappe.db.get_value(
			"Annual Leave Disbursement", self.annual_leave_disbursement, "status"
		)
		if current != "Paid":
			return

		frappe.db.set_value(
			"Annual Leave Disbursement",
			self.annual_leave_disbursement,
			"status",
			"Approved",
			update_modified=False,
		)

	def _leave_disbursement_has_paid_state(self) -> bool:
		"""Annual Leave Disbursement is owned elsewhere; never assume its option list."""
		field = frappe.get_meta("Annual Leave Disbursement").get_field("status")
		return bool(field) and "Paid" in cstr(field.options).split("\n")


# ── whitelisted helpers for the form ──────────────────────────────────────────


@frappe.whitelist()
def get_settlement_defaults(employee: str, settlement_date: str = None) -> dict:
	"""What the form should propose the moment an employee is picked."""
	assert_employee_access(employee)

	settlement_date = getdate(settlement_date or today())
	company = frappe.db.get_value("Employee", employee, "company")

	from hr_suite.hr_suite.employee_salary import get_current_assignment

	assignment = get_current_assignment(employee, settlement_date)

	return {
		"period_from": get_first_day(settlement_date),
		"period_to": settlement_date,
		"company": company,
		"currency": (
			frappe.get_cached_value("Company", company, "default_currency") if company else None
		),
		"has_salary_structure": bool(assignment),
		"salary_structure": (assignment or {}).get("salary_structure"),
	}
