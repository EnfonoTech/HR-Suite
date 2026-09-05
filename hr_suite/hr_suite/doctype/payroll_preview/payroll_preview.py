# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Payroll Preview - the pre-payroll allocation review screen.

READ-ONLY BY DESIGN.  This DocType never creates, posts or stores a salary figure of
its own.  Every amount on it is a read of an underlying document (Salary Structure
Assignment, Additional Salary, Employee Advance, Salary Withholding, Attendance and the
hr_suite sources).  The moment it computes and stores its own payroll amounts it becomes
a third payroll engine alongside Payroll Entry and hr_suite's Monthly Payroll, which is
exactly the defect this screen exists to expose.  Keep it a mirror.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Count
from frappe.utils import (
	add_days,
	cint,
	cstr,
	date_diff,
	escape_html,
	flt,
	get_link_to_form,
	getdate,
	now_datetime,
)

# Entry types on Payroll Preview Allocation.
# Earning / Deduction  -> the item reaches the Salary Slip produced by Payroll Entry.
# Information          -> the item is booked but is settled outside Payroll Entry
#                         (Monthly Payroll, a Journal Entry, a Salary Structure change)
#                         or is not yet booked into payroll at all.
EARNING = "Earning"
DEDUCTION = "Deduction"
INFORMATION = "Information"

# Attendance statuses that carry LWP / absence, mirroring
# hrms/payroll/doctype/salary_slip/salary_slip.py :: get_employee_attendance
UNPAID_ATTENDANCE_STATUSES = ("Absent", "Half Day", "On Leave")

# The Employee identity number is a per-country custom field; hr_suite ships none.
# Probe the Employee meta for the first of these that exists and only then check it,
# so a bench without any of them does not raise a false blocking issue.
IDENTITY_FIELD_CANDIDATES = (
	"custom_cpr_number",
	"custom_cpr_no",
	"custom_cpr",
	"cpr_number",
	"custom_national_id",
	"national_id",
	"custom_personal_id",
	"custom_id_number",
)

# Changing any of these changes WHICH employees and WHICH period the mirror covers, so
# the previously read rows stop describing this document. They are cleared rather than
# left behind, otherwise a preview refreshed clean for one period could be edited onto
# another and still present itself as checked.
SCOPE_FIELDS = (
	"company",
	"payroll_frequency",
	"start_date",
	"end_date",
	"branch",
	"department",
	"designation",
	"employee_grade",
)


class PayrollPreview(Document):
	# -- document lifecycle ----------------------------------------------------

	def validate(self):
		self.validate_period()
		self.set_currency()
		self.clear_results_if_scope_changed()
		self.recalculate_totals()

	def clear_results_if_scope_changed(self):
		"""Drop the mirrored rows when the scope they were read for has changed.

		Without this a preview refreshed for a clean period keeps `has_issues = 0` on
		every row while the period underneath it is edited to one that was never read,
		and `make_payroll_entry` would then wave through employees nobody checked.
		"""
		if self.is_new() or self.flags.rebuilding_preview:
			return

		previous = frappe.db.get_value("Payroll Preview", self.name, SCOPE_FIELDS, as_dict=True)
		if not previous:
			return

		if not any(cstr(previous.get(field)) != cstr(self.get(field)) for field in SCOPE_FIELDS):
			return

		self.set("employees", [])
		self.set("allocations", [])
		self.last_refreshed_on = None

	def validate_period(self):
		if not (self.start_date and self.end_date):
			return

		if getdate(self.start_date) > getdate(self.end_date):
			frappe.throw(_("Start Date cannot be after End Date."), title=_("Invalid Period"))

	def set_currency(self):
		if not self.company:
			return

		self.currency = frappe.db.get_value("Company", self.company, "default_currency")

	def recalculate_totals(self):
		"""Aggregate the child rows. Pure summation of values already read from source."""
		precision = self.precision("total_earnings")

		self.number_of_employees = len(self.employees)
		self.employees_with_issues = sum(1 for row in self.employees if cint(row.has_issues))
		self.employees_with_notes = sum(
			1 for row in self.employees if cstr(row.advisory_notes).strip() and not cint(row.has_issues)
		)
		self.total_base = flt(sum(flt(row.base) for row in self.employees), precision)
		self.total_earnings = flt(sum(flt(row.earnings) for row in self.employees), precision)
		self.total_deductions = flt(sum(flt(row.deductions) for row in self.employees), precision)
		self.net_estimate = flt(sum(flt(row.net_estimate) for row in self.employees), precision)

	# -- refresh ---------------------------------------------------------------

	@frappe.whitelist()
	def refresh_allocations(self):
		"""Rebuild the employee and allocation tables from the source documents.

		One query per source; never a query per employee.
		"""
		self.check_permission("write")
		self.validate_period()

		if not (self.company and self.start_date and self.end_date):
			frappe.throw(_("Set Company, Start Date and End Date before refreshing."))

		self.set("employees", [])
		self.set("allocations", [])
		self.set_currency()

		employees = self._get_employees()
		if not employees:
			self.recalculate_totals()
			self.last_refreshed_on = now_datetime()
			self._save_mirror()
			frappe.msgprint(
				_("No active employees match Company {0} and the selected filters for this period.").format(
					frappe.bold(self.company)
				),
				title=_("Nothing to Preview"),
				indicator="orange",
			)
			return

		employee_ids = list(employees.keys())

		assignments = self._get_salary_structure_assignments(employee_ids)
		timesheet_based = self._get_timesheet_based_employees(assignments)
		additional_salaries = self._get_additional_salaries(employee_ids)
		benefit_claims = self._get_employee_benefit_claims(employee_ids)
		advances = self._get_employee_advances(employee_ids, additional_salaries)
		withholdings = self._get_salary_withholdings(employee_ids)
		attendance = self._get_attendance_summary(employees)
		self._attach_payment_day_factor(employees, attendance)
		timesheets = self._get_timesheets(timesheet_based)
		loan_installments = self._get_loan_installments(employee_ids)
		penalties = self._get_employee_penalties(employee_ids, additional_salaries)
		overtime = self._get_overtime_requests(employee_ids)
		adjustments = self._get_salary_adjustments(employee_ids)

		self._add_additional_salary_rows(employees, additional_salaries)
		self._add_benefit_claim_rows(employees, benefit_claims)
		self._add_advance_rows(employees, advances)
		self._add_withholding_rows(employees, withholdings)
		self._add_timesheet_rows(employees, timesheets)
		self._add_loan_installment_rows(employees, loan_installments)
		self._add_penalty_rows(employees, penalties)
		self._add_overtime_rows(employees, overtime)
		self._add_salary_adjustment_rows(employees, adjustments)

		structure_components = self._get_structure_components(assignments)
		unmapped_components = self._get_components_without_account(structure_components)

		self._build_employee_rows(
			employees,
			assignments,
			attendance,
			withholdings,
			unmapped_components,
			timesheet_based,
			structure_components,
		)

		self.recalculate_totals()
		self.last_refreshed_on = now_datetime()
		self._save_mirror()

		self._warn_about_lending_app()
		self._warn_if_payroll_not_attendance_based()

	def _save_mirror(self) -> None:
		"""Persist the rows this refresh just read.

		`rebuilding_preview` tells `clear_results_if_scope_changed` that the scope on the
		document IS the scope the rows were read for, so it must not wipe them; it is
		cleared straight afterwards or a later edit of the period would keep them.

		`ignore_links` skips one `SELECT name FROM tab<Source>` per allocation row. Every
		`source_name` was returned by a query against that same table moments ago, so
		re-checking it only costs one query per row on a large run.
		"""
		self.flags.rebuilding_preview = True
		self.flags.ignore_links = True
		try:
			self.save()
		finally:
			self.flags.rebuilding_preview = False
			self.flags.ignore_links = False
		self._warn_about_company_payroll_setup()

	# -- sources ---------------------------------------------------------------

	def _get_employees(self) -> dict:
		"""Active employees for the company + filters.

		Deliberately NOT joined to Salary Structure Assignment, unlike hrms
		`get_filtered_employees` (payroll_entry.py:1274). An employee with no assignment
		must be VISIBLE here as a blocking issue instead of being silently dropped.
		"""
		Employee = frappe.qb.DocType("Employee")

		query = (
			frappe.qb.from_(Employee)
			.select(
				Employee.name,
				Employee.employee_name,
				Employee.department,
				Employee.designation,
				Employee.branch,
				Employee.date_of_joining,
				Employee.relieving_date,
				Employee.holiday_list,
				Employee.iban,
				Employee.bank_ac_no,
			)
			.where(
				(Employee.status != "Inactive")
				& (Employee.company == self.company)
				& ((Employee.date_of_joining <= self.end_date) | (Employee.date_of_joining.isnull()))
				& ((Employee.relieving_date >= self.start_date) | (Employee.relieving_date.isnull()))
			)
			.orderby(Employee.employee_name)
		)

		employee_meta = frappe.get_meta("Employee")
		for fieldname, value in (
			("branch", self.branch),
			("department", self.department),
			("designation", self.designation),
			# `grade` is an hrms Custom Field on Employee (hrms/setup.py:197), not core.
			("grade", self.employee_grade),
		):
			if value and employee_meta.has_field(fieldname):
				query = query.where(Employee[fieldname] == value)

		rows = query.run(as_dict=True)
		employees = {row.name: row for row in rows}

		for row in employees.values():
			row.identity_number = None
			row.has_identity_field = False
			row.earnings = 0.0
			row.deductions = 0.0

		self._attach_identity_numbers(employees, employee_meta)
		return employees

	def _attach_identity_numbers(self, employees: dict, employee_meta) -> None:
		identity_field = next(
			(f for f in IDENTITY_FIELD_CANDIDATES if employee_meta.has_field(f)),
			None,
		)
		if not identity_field:
			return

		rows = frappe.get_all(
			"Employee",
			filters={"name": ("in", list(employees.keys()))},
			fields=["name", identity_field],
		)
		for row in rows:
			employees[row.name].identity_number = row.get(identity_field)
			employees[row.name].has_identity_field = True

	def _get_salary_structure_assignments(self, employee_ids: list) -> dict:
		"""Latest submitted assignment per employee on or before the period end."""
		SSA = frappe.qb.DocType("Salary Structure Assignment")

		rows = (
			frappe.qb.from_(SSA)
			.select(
				SSA.name,
				SSA.employee,
				SSA.base,
				SSA.salary_structure,
				SSA.from_date,
				SSA.currency,
			)
			.where(
				(SSA.docstatus == 1)
				& (SSA.employee.isin(employee_ids))
				& (SSA.company == self.company)
				& (SSA.from_date <= self.end_date)
			)
			.orderby(SSA.employee)
			.orderby(SSA.from_date)
			.orderby(SSA.creation)
		).run(as_dict=True)

		# ordered ascending, so the last row seen per employee is the latest one
		return {row.employee: row for row in rows}

	def _get_timesheet_based_employees(self, assignments: dict) -> dict:
		"""Employees whose assigned Salary Structure pays from Timesheets.

		`SalarySlip.set_salary_structure_assignment` copies
		`Salary Structure.salary_slip_based_on_timesheet` onto the slip
		(salary_slip.py:359), and the slip then values the period from the Timesheets
		instead of the structure, so `base` alone does not describe those employees.
		One query for every structure in play.
		"""
		structures = {row.salary_structure for row in assignments.values() if row.salary_structure}
		if not structures:
			return {}

		timesheet_structures = set(
			frappe.get_all(
				"Salary Structure",
				filters={"name": ("in", list(structures)), "salary_slip_based_on_timesheet": 1},
				pluck="name",
			)
		)
		if not timesheet_structures:
			return {}

		return {
			employee_id: assignment.salary_structure
			for employee_id, assignment in assignments.items()
			if assignment.salary_structure in timesheet_structures
		}

	def _get_timesheets(self, timesheet_based: dict) -> list:
		"""Submitted Timesheets overlapping the period for timesheet-paid employees."""
		if not timesheet_based:
			return []

		Timesheet = frappe.qb.DocType("Timesheet")

		return (
			frappe.qb.from_(Timesheet)
			.select(
				Timesheet.name,
				Timesheet.employee,
				Timesheet.start_date,
				Timesheet.end_date,
				Timesheet.total_hours,
				Timesheet.salary_slip,
			)
			.where(
				(Timesheet.docstatus == 1)
				& (Timesheet.employee.isin(list(timesheet_based.keys())))
				& (Timesheet.company == self.company)
				& (Timesheet.start_date <= self.end_date)
				& (Timesheet.end_date >= self.start_date)
			)
			.orderby(Timesheet.employee)
			.orderby(Timesheet.start_date)
		).run(as_dict=True)

	def _get_employee_benefit_claims(self, employee_ids: list) -> list:
		"""Flexible benefit claims that fall in the period.

		A claim with `pay_against_benefit_claim = 1` is added to its earning component on
		the slip by `get_benefit_claim_amount`
		(hrms/payroll/doctype/employee_benefit_claim/employee_benefit_claim.py:138), so it
		is a real earning. A claim without that flag is dispensed pro rata through the
		flexible benefit component itself and adds nothing on top, so it is information.
		"""
		return frappe.get_all(
			"Employee Benefit Claim",
			filters={
				"docstatus": 1,
				"employee": ("in", employee_ids),
				"company": self.company,
				"claim_date": ("between", [self.start_date, self.end_date]),
			},
			fields=[
				"name",
				"employee",
				"employee_name",
				"earning_component",
				"claimed_amount",
				"claim_date",
				"pay_against_benefit_claim",
				"salary_slip",
			],
			order_by="employee asc, claim_date asc",
		)

	def _get_additional_salaries(self, employee_ids: list) -> list:
		"""Mirrors the period criteria of hrms `get_additional_salaries`
		(hrms/payroll/doctype/additional_salary/additional_salary.py:252) exactly, but for
		every employee at once and for both component types.
		"""
		AdditionalSalary = frappe.qb.DocType("Additional Salary")

		return (
			frappe.qb.from_(AdditionalSalary)
			.select(
				AdditionalSalary.name,
				AdditionalSalary.employee,
				AdditionalSalary.employee_name,
				AdditionalSalary.salary_component,
				AdditionalSalary.amount,
				AdditionalSalary.type,
				AdditionalSalary.payroll_date,
				AdditionalSalary.from_date,
				AdditionalSalary.to_date,
				AdditionalSalary.is_recurring,
				AdditionalSalary.overwrite_salary_structure_amount,
				AdditionalSalary.ref_doctype,
				AdditionalSalary.ref_docname,
			)
			.where(
				(AdditionalSalary.docstatus == 1)
				& (AdditionalSalary.disabled == 0)
				& (AdditionalSalary.employee.isin(employee_ids))
				& (AdditionalSalary.company == self.company)
			)
			.where(
				Criterion.any(
					[
						Criterion.all(
							[
								AdditionalSalary.is_recurring == 1,
								AdditionalSalary.from_date <= self.end_date,
								AdditionalSalary.to_date >= self.end_date,
							]
						),
						Criterion.all(
							[
								AdditionalSalary.is_recurring == 0,
								AdditionalSalary.payroll_date[self.start_date : self.end_date],
							]
						),
					]
				)
			)
			.orderby(AdditionalSalary.employee)
			.orderby(AdditionalSalary.payroll_date)
		).run(as_dict=True)

	def _get_employee_advances(self, employee_ids: list, additional_salaries: list) -> list:
		"""Advances flagged for salary recovery that still carry a pending amount.

		An advance is recovered by creating an Additional Salary from it (hrms
		`create_return_through_additional_salary`), so any advance that already has one for
		this period is dropped here rather than being counted twice.
		"""
		already_booked = {
			row.ref_docname
			for row in additional_salaries
			if row.ref_doctype == "Employee Advance" and row.ref_docname
		}

		rows = frappe.get_all(
			"Employee Advance",
			filters={
				"docstatus": 1,
				"employee": ("in", employee_ids),
				"company": self.company,
				"repay_unclaimed_amount_from_salary": 1,
				"pending_amount": (">", 0),
			},
			fields=[
				"name",
				"employee",
				"employee_name",
				"posting_date",
				"advance_amount",
				"pending_amount",
				"purpose",
			],
			order_by="employee asc, posting_date asc",
		)

		return [row for row in rows if row.name not in already_booked]

	def _get_salary_withholdings(self, employee_ids: list) -> list:
		"""Withholding cycles overlapping the period and not yet released.

		hrms `get_salary_withholdings` (payroll_entry.py:1689) matches the cycle dates
		EXACTLY against the payroll period; an overlap test is used here so a preview built
		over a slightly different window still surfaces the withholding.
		"""
		Withholding = frappe.qb.DocType("Salary Withholding")
		Cycle = frappe.qb.DocType("Salary Withholding Cycle")

		return (
			frappe.qb.from_(Withholding)
			.join(Cycle)
			.on(Cycle.parent == Withholding.name)
			.select(
				Withholding.name,
				Withholding.employee,
				Withholding.employee_name,
				Withholding.reason_for_withholding_salary,
				Cycle.from_date,
				Cycle.to_date,
			)
			.where(
				(Withholding.docstatus == 1)
				& (Cycle.docstatus == 1)
				& (Cycle.is_salary_released != 1)
				& (Withholding.employee.isin(employee_ids))
				& (Withholding.company == self.company)
				& (Cycle.from_date <= self.end_date)
				& (Cycle.to_date >= self.start_date)
			)
			.orderby(Withholding.employee)
		).run(as_dict=True)

	def _get_attendance_summary(self, employees: dict) -> dict:
		"""Working days, LWP, absent, unmarked and PAYMENT DAYS per employee.

		The whole point of this screen is that its numbers are the numbers the Salary Slip
		will use.  hrms `get_working_days_details` (salary_slip.py:445-531) takes LWP from
		Attendance ONLY when `Payroll Settings.payroll_based_on == "Attendance"`, and from
		approved Leave Applications otherwise, and it never charges absent days on a
		Leave based payroll.  So the source is chosen the same way here; reading Attendance
		regardless would print an LWP and an absent figure that no Salary Slip ever applies.

		Mirrors `calculate_lwp_ppl_and_absent_days_based_on_attendance` (salary_slip.py:727),
		`calculate_lwp_or_ppl_based_on_leave_application` (:656), `get_payment_days` (:621)
		and `get_employees_with_unmarked_attendance` (payroll_entry.py:1149). All of those
		are SalarySlip / PayrollEntry INSTANCE methods reading `self.employee`, so none can
		be called from here; the logic is reproduced against the same fieldnames, batched
		across every employee instead of one query per employee.
		"""
		employee_ids = list(employees.keys())
		Attendance = frappe.qb.DocType("Attendance")

		unpaid_rows = (
			frappe.qb.from_(Attendance)
			.select(
				Attendance.employee,
				Attendance.attendance_date,
				Attendance.status,
				Attendance.leave_type,
				Attendance.half_day_status,
			)
			.where(
				(Attendance.docstatus == 1)
				& (Attendance.employee.isin(employee_ids))
				& (Attendance.attendance_date[self.start_date : self.end_date])
				& (Attendance.status.isin(list(UNPAID_ATTENDANCE_STATUSES)))
			)
		).run(as_dict=True)

		marked_counts = dict(
			(
				frappe.qb.from_(Attendance)
				.select(Attendance.employee, Count(Attendance.name))
				.where(
					(Attendance.docstatus == 1)
					& (Attendance.employee.isin(employee_ids))
					& (Attendance.attendance_date[self.start_date : self.end_date])
				)
				.groupby(Attendance.employee)
			).run()
		)

		leave_type_map = self._get_leave_type_map()
		settings = frappe.get_cached_doc("Payroll Settings")
		half_day_fraction = flt(settings.daily_wages_fraction_for_half_day) or 0.5
		include_holidays = cint(settings.include_holidays_in_total_working_days)
		# hrms ANDs the two flags (salary_slip.py:459-462): marked attendance on a holiday
		# only counts when holidays are inside total working days in the first place.
		# Reading `consider_marked_attendance_on_holidays` alone diverges from the slip.
		count_on_holidays = include_holidays and cint(settings.consider_marked_attendance_on_holidays)
		attendance_driven = settings.payroll_based_on == "Attendance"
		unmarked_as_absent = (settings.consider_unmarked_attendance_as or "Present") == "Absent"

		holidays_by_list = self._get_holidays_by_list(employees)
		default_holiday_list = frappe.db.get_value(
			"Company", self.company, "default_holiday_list", cache=True
		)

		periods = {}
		summary = {}
		for employee_id, employee in employees.items():
			start_date, end_date = self._get_period_for_employee(employee)
			periods[employee_id] = (start_date, end_date)

			holiday_list = employee.holiday_list or default_holiday_list
			all_holidays = holidays_by_list.get(holiday_list, set())
			holidays = {
				holiday_date for holiday_date in all_holidays if start_date <= holiday_date <= end_date
			}

			payroll_days = date_diff(end_date, start_date) + 1
			unmarked_days = payroll_days - (len(holidays) + cint(marked_counts.get(employee_id)))

			# total_working_days is measured over the FULL period (salary_slip.py:466-478),
			# payment days over the joining / relieving clamped period (:621-643).
			period_days = date_diff(self.end_date, self.start_date) + 1
			period_holidays = {
				holiday_date
				for holiday_date in all_holidays
				if getdate(self.start_date) <= holiday_date <= getdate(self.end_date)
			}
			total_working_days = period_days if include_holidays else period_days - len(period_holidays)
			base_payment_days = payroll_days if include_holidays else payroll_days - len(holidays)

			if employee.date_of_joining and getdate(employee.date_of_joining) > getdate(self.end_date):
				# joined after the period: hrms returns 0 payment days outright
				base_payment_days = 0

			summary[employee_id] = frappe._dict(
				{
					"lwp_days": 0.0,
					"absent_days": 0.0,
					"unmarked_days": max(unmarked_days, 0),
					"total_working_days": max(total_working_days, 0),
					"base_payment_days": max(base_payment_days, 0),
					"payment_days": max(base_payment_days, 0),
				}
			)

		if not attendance_driven:
			# Payroll Settings is Leave based: LWP comes from approved Leave Applications
			# and absent days never reduce pay. Attendance is still read above, but only to
			# report unmarked days as advisory information.
			self._apply_leave_application_lwp(
				employees, summary, periods, holidays_by_list, default_holiday_list,
				include_holidays, half_day_fraction,
			)
			self._apply_payment_days(summary, attendance_driven, unmarked_as_absent)
			return summary

		for row in unpaid_rows:
			bucket = summary.get(row.employee)
			if not bucket:
				continue

			employee = employees[row.employee]
			start_date, end_date = periods[row.employee]
			attendance_date = getdate(row.attendance_date)
			if not (start_date <= attendance_date <= end_date):
				continue

			leave_type = leave_type_map.get(row.leave_type) if row.leave_type else None
			if row.status in ("Half Day", "On Leave") and row.leave_type and not leave_type:
				# a fully paid leave type: no LWP impact
				continue

			holiday_list = employee.holiday_list or default_holiday_list
			on_holiday = attendance_date in holidays_by_list.get(holiday_list, set())
			if not count_on_holidays and on_holiday:
				if row.status in ("Absent", "Half Day") or (
					leave_type and not cint(leave_type.include_holiday)
				):
					continue

			fraction = flt(leave_type.fraction_of_daily_salary_per_leave) if leave_type else 0.0

			if row.status == "Half Day" and leave_type:
				equivalent_lwp = 1 - half_day_fraction
				if cint(leave_type.is_ppl):
					equivalent_lwp *= fraction or 1
				bucket.lwp_days += equivalent_lwp
			elif row.status == "On Leave" and leave_type:
				equivalent_lwp = 1.0
				if cint(leave_type.is_ppl):
					equivalent_lwp *= fraction or 1
				bucket.lwp_days += equivalent_lwp
			elif row.status == "Absent":
				bucket.absent_days += 1

		self._add_half_absent_days(
			employees, summary, periods, holidays_by_list, default_holiday_list,
			count_on_holidays, half_day_fraction, unpaid_rows,
		)

		self._apply_payment_days(summary, attendance_driven, unmarked_as_absent)
		return summary

	def _add_half_absent_days(
		self,
		employees: dict,
		summary: dict,
		periods: dict,
		holidays_by_list: dict,
		default_holiday_list,
		count_on_holidays: bool,
		half_day_fraction: float,
		unpaid_rows: list,
	) -> None:
		"""Charge half days whose OTHER half is marked absent.

		hrms does this in a SEPARATE query, `get_half_absent_days` (salary_slip.py:548-566):
		it counts every submitted Attendance with status "Half Day" and
		`half_day_status = "Absent"` in the period, with no regard at all to the leave type
		behind it, and `get_working_days_details` (:527-530) then adds
		`half_absent_days * daily_wages_fraction_for_half_day` to absent days and takes the
		same off payment days.

		It therefore has to be a second pass here too. Folding it into the LWP branch above
		would skip every half day that already contributed LWP - and a Half Day on Leave
		Without Pay with the other half marked Absent is precisely the row that costs the
		employee a whole day on the Salary Slip: 0.5 LWP plus 0.5 absent.

		Holidays are excluded on the same condition hrms uses.
		"""
		for row in unpaid_rows:
			if row.status != "Half Day" or row.half_day_status != "Absent":
				continue

			bucket = summary.get(row.employee)
			if not bucket:
				continue

			start_date, end_date = periods[row.employee]
			attendance_date = getdate(row.attendance_date)
			if not (start_date <= attendance_date <= end_date):
				continue

			if not count_on_holidays:
				holiday_list = employees[row.employee].holiday_list or default_holiday_list
				if attendance_date in holidays_by_list.get(holiday_list, set()):
					continue

			bucket.absent_days += half_day_fraction

	def _apply_payment_days(self, summary: dict, attendance_driven: bool, unmarked_as_absent: bool) -> None:
		"""Reduce payment days by LWP and absence exactly as hrms does (salary_slip.py:509-531).

		hrms zeroes payment days outright when LWP alone would consume them, rather than
		letting them go negative; the same guard is applied here so the two agree at the
		edge as well as in the middle.
		"""
		for bucket in summary.values():
			base_payment_days = flt(bucket.base_payment_days)
			lwp = flt(bucket.lwp_days)

			if base_payment_days <= lwp:
				bucket.payment_days = 0.0
				continue

			payment_days = base_payment_days - lwp
			if attendance_driven:
				payment_days -= flt(bucket.absent_days)
				if unmarked_as_absent:
					payment_days -= flt(bucket.unmarked_days)

			bucket.payment_days = max(payment_days, 0.0)

	def _apply_leave_application_lwp(
		self,
		employees: dict,
		summary: dict,
		periods: dict,
		holidays_by_list: dict,
		default_holiday_list,
		include_holidays: int,
		half_day_fraction: float,
	) -> None:
		"""LWP from approved Leave Applications, mirroring hrms
		`calculate_lwp_or_ppl_based_on_leave_application` (salary_slip.py:656-700) and its
		fetcher `get_lwp_or_ppl_for_date_range` (:2303).

		The hrms fetcher runs one query per employee; this runs one query for the whole
		preview and maps the rows back per employee.

		Note the deliberate asymmetry that hrms itself carries: the leave-application path
		multiplies a partially paid leave by `(1 - fraction)` while the attendance path
		multiplies by `fraction`. Both are reproduced as written so the preview matches
		whichever path the Salary Slip actually takes.
		"""
		employee_ids = list(employees.keys())
		if not employee_ids:
			return

		LeaveApplication = frappe.qb.DocType("Leave Application")
		LeaveType = frappe.qb.DocType("Leave Type")

		leaves = (
			frappe.qb.from_(LeaveApplication)
			.inner_join(LeaveType)
			.on(LeaveType.name == LeaveApplication.leave_type)
			.select(
				LeaveApplication.employee,
				LeaveApplication.from_date,
				LeaveApplication.to_date,
				LeaveApplication.half_day,
				LeaveApplication.half_day_date,
				LeaveType.is_ppl,
				LeaveType.fraction_of_daily_salary_per_leave,
				LeaveType.include_holiday,
			)
			.where(
				((LeaveType.is_lwp == 1) | (LeaveType.is_ppl == 1))
				& (LeaveApplication.docstatus == 1)
				& (LeaveApplication.status == "Approved")
				& (LeaveApplication.employee.isin(employee_ids))
				& (LeaveApplication.salary_slip.isnull() | (LeaveApplication.salary_slip == ""))
				& (LeaveApplication.from_date <= self.end_date)
				& (LeaveApplication.to_date >= self.start_date)
			)
		).run(as_dict=True)

		leave_by_employee_date = {}
		for leave in leaves:
			for offset in range(date_diff(leave.to_date, leave.from_date) + 1):
				leave_by_employee_date[(leave.employee, add_days(leave.from_date, offset))] = leave

		if not leave_by_employee_date:
			return

		period_start = getdate(self.start_date)
		period_days = date_diff(self.end_date, self.start_date) + 1

		for employee_id, employee in employees.items():
			bucket = summary.get(employee_id)
			if not bucket:
				continue

			holidays = holidays_by_list.get(employee.holiday_list or default_holiday_list, set())
			relieving_date = getdate(employee.relieving_date) if employee.relieving_date else None

			for offset in range(period_days):
				day = add_days(period_start, offset)
				if relieving_date and day > relieving_date:
					break

				# hrms drops holidays out of the working-days list up front when they are
				# not counted in total working days (salary_slip.py:475-478)
				if not include_holidays and day in holidays:
					continue

				leave = leave_by_employee_date.get((employee_id, day))
				if not leave:
					continue

				if not cint(leave.include_holiday) and day in holidays:
					continue

				is_half_day = cint(leave.half_day) and (
					getdate(leave.half_day_date) == day if leave.half_day_date else leave.from_date == leave.to_date
				)
				equivalent_lwp = (1 - half_day_fraction) if is_half_day else 1.0

				if cint(leave.is_ppl):
					fraction = flt(leave.fraction_of_daily_salary_per_leave)
					equivalent_lwp *= (1 - fraction) if fraction else 1

				bucket.lwp_days += equivalent_lwp

	def _get_leave_type_map(self) -> dict:
		leave_types = frappe.get_all(
			"Leave Type",
			or_filters={"is_ppl": 1, "is_lwp": 1},
			fields=["name", "is_lwp", "is_ppl", "fraction_of_daily_salary_per_leave", "include_holiday"],
		)
		return {leave_type.name: leave_type for leave_type in leave_types}

	def _get_holidays_by_list(self, employees: dict) -> dict:
		"""All holiday dates for every holiday list in play, in ONE query."""
		default_holiday_list = frappe.db.get_value(
			"Company", self.company, "default_holiday_list", cache=True
		)
		holiday_lists = {employee.holiday_list or default_holiday_list for employee in employees.values()}
		holiday_lists.discard(None)
		holiday_lists.discard("")

		if not holiday_lists:
			return {}

		rows = frappe.get_all(
			"Holiday",
			filters={
				"parent": ("in", list(holiday_lists)),
				"parenttype": "Holiday List",
				"holiday_date": ("between", [self.start_date, self.end_date]),
			},
			fields=["parent", "holiday_date"],
		)

		holidays_by_list = {}
		for row in rows:
			holidays_by_list.setdefault(row.parent, set()).add(getdate(row.holiday_date))

		return holidays_by_list

	def _get_period_for_employee(self, employee) -> tuple:
		"""Clamp the payroll period to joining / relieving, as hrms
		`get_payroll_dates_for_employee` does (payroll_entry.py:1219).
		"""
		start_date = getdate(self.start_date)
		if employee.date_of_joining and getdate(employee.date_of_joining) > start_date:
			start_date = getdate(employee.date_of_joining)

		end_date = getdate(self.end_date)
		if employee.relieving_date and getdate(employee.relieving_date) < end_date:
			end_date = getdate(employee.relieving_date)

		if start_date > end_date:
			start_date = end_date

		return start_date, end_date

	def _attach_payment_day_factor(self, employees: dict, attendance: dict) -> None:
		"""Stash payment_days / total_working_days on each employee.

		Every `depends_on_payment_days` component on the Salary Slip is scaled by exactly
		this ratio (salary_slip.py:1842-1852), Additional Salary rows included, so the
		allocation rows have to be able to reach it while they are being built.
		"""
		for employee_id, employee in employees.items():
			counts = attendance.get(employee_id)
			total_working_days = flt(counts.total_working_days) if counts else 0.0
			employee.payment_day_factor = (
				flt(counts.payment_days) / total_working_days if (counts and total_working_days) else 1.0
			)

	def _get_components_depending_on_payment_days(self, components: set) -> set:
		"""Which of these Salary Components the Salary Slip will prorate."""
		if not components:
			return set()

		return set(
			frappe.get_all(
				"Salary Component",
				filters={"name": ("in", list(components)), "depends_on_payment_days": 1},
				pluck="name",
			)
		)

	# -- hr_suite sources (each guarded: hr_suite may be partially installed) ---

	def _get_loan_installments(self, employee_ids: list) -> list:
		if not (
			frappe.db.exists("DocType", "Employee Loan")
			and frappe.db.exists("DocType", "Employee Loan Installment")
		):
			return []

		Loan = frappe.qb.DocType("Employee Loan")
		Installment = frappe.qb.DocType("Employee Loan Installment")

		return (
			frappe.qb.from_(Installment)
			.join(Loan)
			.on(Loan.name == Installment.parent)
			.select(
				Loan.name.as_("loan"),
				Loan.employee,
				Loan.employee_name,
				Installment.installment_number,
				Installment.due_date,
				Installment.installment_amount,
				Installment.outstanding_amount,
			)
			.where(
				(Loan.docstatus == 1)
				& (Loan.employee.isin(employee_ids))
				& (Loan.company == self.company)
				& (Installment.parenttype == "Employee Loan")
				& (Installment.deduction_status == "Pending")
				& (Installment.due_date[self.start_date : self.end_date])
			)
			.orderby(Loan.employee)
			.orderby(Installment.due_date)
		).run(as_dict=True)

	def _get_employee_penalties(self, employee_ids: list, additional_salaries: list) -> list:
		"""Penalties in the period that are NOT already represented.

		A submitted Employee Penalty creates and submits its own Additional Salary
		(hr_suite employee_penalty.py:54-81) carrying ref_doctype / ref_docname, so those
		are already listed among the Additional Salary rows. Only penalties without one are
		listed here, as information that they will not reach this payroll run.
		"""
		if not frappe.db.exists("DocType", "Employee Penalty"):
			return []

		booked = {
			row.ref_docname
			for row in additional_salaries
			if row.ref_doctype == "Employee Penalty" and row.ref_docname
		}

		rows = frappe.get_all(
			"Employee Penalty",
			filters={
				"docstatus": 1,
				"employee": ("in", employee_ids),
				"company": self.company,
				"posting_date": ("between", [self.start_date, self.end_date]),
			},
			fields=[
				"name",
				"employee",
				"employee_name",
				"penalty_type",
				"penalty_value",
				"posting_date",
				"additional_salary",
				"subject",
			],
			order_by="employee asc, posting_date asc",
		)

		return [row for row in rows if row.name not in booked and not row.additional_salary]

	def _get_overtime_requests(self, employee_ids: list) -> list:
		if not frappe.db.exists("DocType", "Overtime Request"):
			return []

		return frappe.get_all(
			"Overtime Request",
			filters={
				"docstatus": 1,
				"employee": ("in", employee_ids),
				"company": self.company,
				"approval_status": "Approved",
				"date": ("between", [self.start_date, self.end_date]),
			},
			fields=[
				"name",
				"employee",
				"employee_name",
				"date",
				"overtime_hours",
				"overtime_amount",
				"overtime_journal_entry",
			],
			order_by="employee asc, date asc",
		)

	def _get_salary_adjustments(self, employee_ids: list) -> list:
		if not frappe.db.exists("DocType", "Salary Adjustment"):
			return []

		return frappe.get_all(
			"Salary Adjustment",
			filters={
				"docstatus": 1,
				"employee": ("in", employee_ids),
				"company": self.company,
				"effective_date": ("between", [self.start_date, self.end_date]),
			},
			fields=[
				"name",
				"employee",
				"employee_name",
				"adjustment_type",
				"adjustment_amount",
				"proposed_basic_salary",
				"effective_date",
				"status",
			],
			order_by="employee asc, effective_date asc",
		)

	# -- allocation rows -------------------------------------------------------

	def _append_allocation(self, employees: dict, employee_id: str, **kwargs) -> None:
		employee = employees.get(employee_id)
		if not employee:
			return

		row = self.append("allocations", {"employee": employee_id, "employee_name": employee.employee_name})
		row.update(kwargs)

		# `amount` mirrors the source document and is never altered. `payable_amount` is
		# what the Salary Slip will actually carry after payment-day proration, and it is
		# that figure the employee totals are built from.
		if row.payable_amount is None:
			row.payable_amount = flt(row.amount)

		amount = flt(row.payable_amount)
		if row.entry_type == EARNING:
			employee.earnings += amount
		elif row.entry_type == DEDUCTION:
			employee.deductions += amount

	def _add_additional_salary_rows(self, employees: dict, additional_salaries: list) -> None:
		prorated_components = self._get_components_depending_on_payment_days(
			{entry.salary_component for entry in additional_salaries if entry.salary_component}
		)

		for entry in additional_salaries:
			if cint(entry.is_recurring):
				description = _("Recurring {0} to {1}").format(entry.from_date, entry.to_date)
			else:
				description = _("Payroll Date {0}").format(entry.payroll_date)

			overwrites = cint(entry.overwrite_salary_structure_amount)
			if overwrites:
				description += ". " + _("Overwrites the salary structure amount for this component.")

			# hrms `get_amount_based_on_payment_days` (salary_slip.py:1823-1852) skips the
			# proration for an overwriting Additional Salary, because that row carries a
			# default_amount alongside the additional_amount.
			factor = 1.0
			employee = employees.get(entry.employee)
			if employee and not overwrites and entry.salary_component in prorated_components:
				factor = flt(employee.get("payment_day_factor", 1.0))

			payable = flt(entry.amount) * factor
			if factor != 1.0:
				description += " " + _("Prorated to {0} of the period actually paid.").format(
					"{0:.2f}".format(factor)
				)

			self._append_allocation(
				employees,
				entry.employee,
				source_doctype="Additional Salary",
				source_name=entry.name,
				# `type` is a Data field on Additional Salary carrying "Earning"/"Deduction"
				entry_type=EARNING if entry.type == EARNING else DEDUCTION,
				salary_component=entry.salary_component,
				amount=flt(entry.amount),
				payable_amount=flt(payable, self.precision("total_earnings")),
				posting_date=entry.payroll_date or entry.from_date,
				origin_doctype=entry.ref_doctype,
				origin_name=entry.ref_docname,
				description=description,
			)

	def _add_benefit_claim_rows(self, employees: dict, claims: list) -> None:
		paid_note = _("Flexible benefit claimed on {0}. Paid against the claim on the Salary Slip.")
		pro_rata_note = _(
			"Flexible benefit claimed on {0}. Dispensed pro rata through the benefit component, so "
			"it adds nothing on top of the salary structure."
		)
		for claim in claims:
			pay_against_claim = cint(claim.pay_against_benefit_claim)
			description = (paid_note if pay_against_claim else pro_rata_note).format(claim.claim_date)
			if claim.salary_slip:
				description += " " + _("Already carried on Salary Slip {0}.").format(claim.salary_slip)

			self._append_allocation(
				employees,
				claim.employee,
				source_doctype="Employee Benefit Claim",
				source_name=claim.name,
				entry_type=EARNING if pay_against_claim else INFORMATION,
				salary_component=claim.earning_component,
				amount=flt(claim.claimed_amount),
				posting_date=claim.claim_date,
				description=description,
			)

	def _add_timesheet_rows(self, employees: dict, timesheets: list) -> None:
		template = _(
			"Timesheet {0} to {1}, {2} hour(s). This employee is on a timesheet-based Salary "
			"Structure, so the Salary Slip values the period from the Timesheets rather than from "
			"Base."
		)
		for timesheet in timesheets:
			self._append_allocation(
				employees,
				timesheet.employee,
				source_doctype="Timesheet",
				source_name=timesheet.name,
				entry_type=INFORMATION,
				posting_date=timesheet.start_date,
				origin_doctype="Salary Slip" if timesheet.salary_slip else None,
				origin_name=timesheet.salary_slip,
				description=template.format(
					timesheet.start_date, timesheet.end_date, flt(timesheet.total_hours)
				),
			)

	def _add_advance_rows(self, employees: dict, advances: list) -> None:
		note = _(
			"Pending advance flagged for salary recovery. It will not be deducted until an "
			"Additional Salary is raised from it."
		)
		for advance in advances:
			self._append_allocation(
				employees,
				advance.employee,
				source_doctype="Employee Advance",
				source_name=advance.name,
				entry_type=INFORMATION,
				amount=flt(advance.pending_amount),
				posting_date=advance.posting_date,
				description=note,
			)

	def _add_withholding_rows(self, employees: dict, withholdings: list) -> None:
		for withholding in withholdings:
			description = _("Salary withheld for the cycle {0} to {1}.").format(
				withholding.from_date, withholding.to_date
			)
			reason = cstr(withholding.reason_for_withholding_salary).strip()
			if reason:
				description += " " + reason

			self._append_allocation(
				employees,
				withholding.employee,
				source_doctype="Salary Withholding",
				source_name=withholding.name,
				entry_type=INFORMATION,
				posting_date=withholding.from_date,
				description=description,
			)

	def _add_loan_installment_rows(self, employees: dict, installments: list) -> None:
		template = _(
			"Loan installment {0} due {1}. hr_suite recovers loan installments through Monthly "
			"Payroll, so this is not deducted by Payroll Entry."
		)
		for installment in installments:
			self._append_allocation(
				employees,
				installment.employee,
				source_doctype="Employee Loan",
				source_name=installment.loan,
				entry_type=INFORMATION,
				amount=flt(installment.installment_amount),
				posting_date=installment.due_date,
				description=template.format(cint(installment.installment_number), installment.due_date),
			)

	def _add_penalty_rows(self, employees: dict, penalties: list) -> None:
		template = _(
			"Penalty {0} ({1} day(s)) has no Additional Salary, so it will not be deducted by this "
			"payroll run."
		)
		for penalty in penalties:
			description = template.format(cstr(penalty.penalty_type), flt(penalty.penalty_value))
			subject = cstr(penalty.subject).strip()
			if subject:
				description += " " + subject

			self._append_allocation(
				employees,
				penalty.employee,
				source_doctype="Employee Penalty",
				source_name=penalty.name,
				entry_type=INFORMATION,
				posting_date=penalty.posting_date,
				description=description,
			)

	def _add_overtime_rows(self, employees: dict, overtime_requests: list) -> None:
		template = _(
			"{0} approved overtime hour(s), paid by Journal Entry rather than through the Salary Slip."
		)
		for request in overtime_requests:
			self._append_allocation(
				employees,
				request.employee,
				source_doctype="Overtime Request",
				source_name=request.name,
				entry_type=INFORMATION,
				amount=flt(request.overtime_amount),
				posting_date=request.date,
				origin_doctype="Journal Entry" if request.overtime_journal_entry else None,
				origin_name=request.overtime_journal_entry,
				description=template.format(flt(request.overtime_hours)),
			)

	def _add_salary_adjustment_rows(self, employees: dict, adjustments: list) -> None:
		template = _(
			"{0} effective {1} (status {2}). It changes the Salary Structure Assignment, not this "
			"payroll run directly."
		)
		for adjustment in adjustments:
			self._append_allocation(
				employees,
				adjustment.employee,
				source_doctype="Salary Adjustment",
				source_name=adjustment.name,
				entry_type=INFORMATION,
				amount=flt(adjustment.adjustment_amount),
				posting_date=adjustment.effective_date,
				description=template.format(
					cstr(adjustment.adjustment_type),
					adjustment.effective_date,
					cstr(adjustment.status),
				),
			)

	# -- blocking issues -------------------------------------------------------

	def _get_structure_components(self, assignments: dict) -> dict:
		"""Every Salary Component each employee's assigned Salary Structure will post.

		The accrual JV is built from the Salary Slip's own earnings and deductions
		(payroll_entry.py `make_accrual_jv_entry`), which come from the STRUCTURE first and
		Additional Salary second. Checking only the allocation rows therefore misses the
		components that actually carry most of the payroll, so both are collected.
		One query for every structure in play, not one per employee.
		"""
		structures = {row.salary_structure for row in assignments.values() if row.salary_structure}
		if not structures:
			return {}

		rows = frappe.get_all(
			"Salary Detail",
			filters={
				"parent": ("in", list(structures)),
				"parenttype": "Salary Structure",
				"statistical_component": 0,
				"do_not_include_in_accounts": 0,
			},
			fields=["parent", "salary_component"],
		)

		by_structure = {}
		for row in rows:
			if row.salary_component:
				by_structure.setdefault(row.parent, set()).add(row.salary_component)

		return {
			employee: by_structure.get(assignment.salary_structure, set())
			for employee, assignment in assignments.items()
		}

	def _get_components_without_account(self, structure_components: dict) -> set:
		"""Salary Components in play that have no Salary Component Account row for this
		company.

		This is the exact failure that rolls a whole Payroll Entry run back at accrual
		time, so it is surfaced here before a single Salary Slip is created.
		"""
		components = {row.salary_component for row in self.allocations if row.salary_component}
		for employee_components in structure_components.values():
			components |= employee_components

		if not components:
			return set()

		mapped = frappe.get_all(
			"Salary Component Account",
			filters={
				"parent": ("in", list(components)),
				"parenttype": "Salary Component",
				"company": self.company,
			},
			pluck="parent",
		)

		return components - set(mapped)

	def _build_employee_rows(
		self,
		employees: dict,
		assignments: dict,
		attendance: dict,
		withholdings: list,
		unmapped_components: set,
		timesheet_based: dict,
		structure_components: dict | None = None,
	) -> None:
		precision = self.precision("total_earnings")
		withheld_employees = {row.employee for row in withholdings}
		attendance_driven = (
			frappe.db.get_single_value("Payroll Settings", "payroll_based_on") == "Attendance"
		)
		default_holiday_list = frappe.db.get_value(
			"Company", self.company, "default_holiday_list", cache=True
		)

		components_by_employee = {}
		for employee_id, components in (structure_components or {}).items():
			if components:
				components_by_employee.setdefault(employee_id, set()).update(components)
		for row in self.allocations:
			if row.salary_component:
				components_by_employee.setdefault(row.employee, set()).add(row.salary_component)

		for employee_id, employee in employees.items():
			assignment = assignments.get(employee_id)
			counts = attendance.get(employee_id) or frappe._dict(
				{
					"lwp_days": 0.0,
					"absent_days": 0.0,
					"unmarked_days": 0.0,
					"total_working_days": 0.0,
					"payment_days": 0.0,
				}
			)

			base = flt(assignment.base) if assignment else 0.0
			earnings = flt(employee.earnings, precision)
			deductions = flt(employee.deductions, precision)

			# The Salary Slip scales every `depends_on_payment_days` component by
			# payment_days / total_working_days (salary_slip.py:1842-1852). Showing an
			# unscaled base next to an LWP figure the screen itself computed would state a
			# net the run cannot produce, which is the one thing a preview must never do.
			total_working_days = flt(counts.total_working_days)
			payable_base = base
			if total_working_days:
				payable_base = flt(base * flt(counts.payment_days) / total_working_days, precision)

			net_estimate = flt(payable_base + earnings - deductions, precision)

			blocking, advisory = self._collect_issues(
				employee=employee,
				assignment=assignment,
				counts=counts,
				net_estimate=net_estimate,
				is_withheld=employee_id in withheld_employees,
				unmapped=components_by_employee.get(employee_id, set()) & unmapped_components,
				is_timesheet_based=employee_id in timesheet_based,
				attendance_driven=attendance_driven,
				has_holiday_list=bool(employee.holiday_list or default_holiday_list),
			)

			self.append(
				"employees",
				{
					"employee": employee_id,
					"employee_name": employee.employee_name,
					"department": employee.department,
					"designation": employee.designation,
					"branch": employee.branch,
					"base": base,
					"earnings": earnings,
					"deductions": deductions,
					"lwp_days": flt(counts.lwp_days, 2),
					"absent_days": flt(counts.absent_days, 2),
					"unmarked_days": flt(counts.unmarked_days, 2),
					"total_working_days": flt(counts.total_working_days, 2),
					"payment_days": flt(counts.payment_days, 2),
					"net_estimate": net_estimate,
					"has_issues": 1 if blocking else 0,
					"blocking_issues": "\n".join(blocking),
					"advisory_notes": "\n".join(advisory),
				},
			)

	def _collect_issues(
		self,
		employee,
		assignment,
		counts,
		net_estimate,
		is_withheld,
		unmapped,
		is_timesheet_based=False,
		attendance_driven=False,
		has_holiday_list=True,
	) -> tuple:
		"""Split what stops payroll from what merely needs a human to look.

		BLOCKING is reserved for conditions under which running the Payroll Entry produces
		a missing or wrong Salary Slip. Everything else is advisory: it is shown, but it
		does not hold the run, because a gate that fires on conditions payroll tolerates
		is a gate people learn to route around.
		"""
		blocking = []
		advisory = []

		if not assignment:
			# No assignment => hrms `get_filtered_employees` drops the employee entirely
			# and no Salary Slip is ever produced for them.
			blocking.append(
				_("No submitted Salary Structure Assignment on or before {0}.").format(self.end_date)
			)

		if not has_holiday_list:
			# erpnext `get_holiday_list_for_employee` (employee.py:271-286) throws, and
			# Salary Slip calls it before it can count a single working day, so the slip is
			# never created at all.
			blocking.append(
				_("No Holiday List on the Employee and no Default Holiday List on {0}.").format(self.company)
			)

		for component in sorted(unmapped):
			# Accrual fails and rolls the whole run back.
			blocking.append(
				_("Salary Component {0} has no account mapped for {1}.").format(component, self.company)
			)

		if net_estimate < 0:
			blocking.append(_("Net estimate is negative."))

		if flt(counts.unmarked_days) > 0:
			# hrms only surfaces unmarked attendance when the Payroll Entry has
			# `validate_attendance` ticked, and payment days are only reduced by it when
			# Payroll Settings is Attendance based (salary_slip.py:512-529). Anywhere else
			# it changes nothing about the slip, so it must not hold the run.
			message = _("{0} unmarked attendance day(s) in the period.").format(
				flt(counts.unmarked_days, 2)
			)
			(blocking if attendance_driven else advisory).append(message)

		if not (employee.iban or employee.bank_ac_no):
			# Needed for the bank payment file, not for the Salary Slip.
			advisory.append(_("No IBAN or bank account number on the Employee record."))

		if employee.has_identity_field and not cstr(employee.identity_number).strip():
			advisory.append(_("No identity number (CPR / national ID) on the Employee record."))

		if is_withheld:
			# Withholding is a supported hrms path: the slip is still created and the
			# payment is held (payroll_entry.py:1689). Blocking it would mean a withheld
			# employee could never be processed at all.
			advisory.append(_("Salary is withheld for this period."))

		if is_timesheet_based:
			advisory.append(
				_("Timesheet-based Salary Structure: the Salary Slip is valued from Timesheets, not Base.")
			)

		return blocking, advisory

	def _warn_about_lending_app(self) -> None:
		"""The lending app is not installed on this bench, so hrms's `salary_slip_loan`
		table is inert. If someone installs it later, say plainly that its repayments are
		outside this preview rather than silently under-reporting deductions.
		"""
		if not frappe.db.exists("DocType", "Loan"):
			return

		frappe.msgprint(
			_(
				"The Loan (lending) app is installed. Loan repayments booked through it are not "
				"read by this preview; review them on the Salary Slip."
			),
			title=_("Lending App Detected"),
			indicator="orange",
		)

	def _warn_if_payroll_not_attendance_based(self) -> None:
		payroll_based_on = frappe.db.get_single_value("Payroll Settings", "payroll_based_on")
		if payroll_based_on == "Attendance":
			return

		frappe.msgprint(
			_(
				"Payroll Settings computes payment days on {0}, not Attendance, so LWP Days here is "
				"read from approved Leave Applications and Absent Days is always zero. Attendance is "
				"still shown as Unmarked Days for information; switch Payroll Based On to Attendance "
				"if absence should reduce pay."
			).format(frappe.bold(cstr(payroll_based_on) or _("Leave"))),
			title=_("Payroll Not Attendance Based"),
			indicator="blue",
		)

	def _warn_about_company_payroll_setup(self) -> None:
		"""Company-level gaps that stop the Payroll Entry itself, not any one employee.

		Both of these surface as raw framework errors on a form the user has not managed to
		save yet -- a mandatory-field error for the payable account, a FiscalYearError deep
		inside Salary Slip creation for the period -- so they are named here, on the screen
		whose job is to be the last thing checked before a run.
		"""
		messages = self._get_company_setup_gaps()
		if not messages:
			return

		frappe.msgprint(
			"<ul>" + "".join(f"<li>{message}</li>" for message in messages) + "</ul>",
			title=_("Company Payroll Setup Incomplete"),
			indicator="red",
		)

	def _get_company_setup_gaps(self) -> list:
		"""Return the company / period setup problems that would break the Payroll Entry."""
		messages = []

		if not frappe.db.get_value("Company", self.company, "default_payroll_payable_account"):
			# Payroll Entry.payroll_payable_account is mandatory and hrms only ever fills it
			# from this company default (payroll_entry.js `set_payable_account_and_currency`).
			messages.append(
				_("Company {0} has no Default Payroll Payable Account, so the Payroll Entry cannot be saved.").format(
					get_link_to_form("Company", self.company)
				)
			)

		for fieldname, label in (("start_date", _("Start Date")), ("end_date", _("End Date"))):
			date_value = self.get(fieldname)
			if not date_value or self._has_active_fiscal_year(date_value):
				continue

			# Salary Slip.compute_year_to_date -> erpnext get_fiscal_year raises
			# FiscalYearError, which aborts every slip the Payroll Entry tries to create.
			messages.append(
				_("{0} {1} is not inside an active Fiscal Year for {2}, so no Salary Slip can be created.").format(
					label, frappe.bold(cstr(date_value)), self.company
				)
			)

		return messages

	def _has_active_fiscal_year(self, date_value) -> bool:
		FiscalYear = frappe.qb.DocType("Fiscal Year")
		FiscalYearCompany = frappe.qb.DocType("Fiscal Year Company")

		rows = (
			frappe.qb.from_(FiscalYear)
			.left_join(FiscalYearCompany)
			.on(FiscalYearCompany.parent == FiscalYear.name)
			.select(FiscalYear.name)
			.where(
				(FiscalYear.disabled == 0)
				& (FiscalYear.year_start_date <= date_value)
				& (FiscalYear.year_end_date >= date_value)
				& (
					FiscalYearCompany.company.isnull()
					| (FiscalYearCompany.company == self.company)
				)
			)
			.limit(1)
		).run()

		return bool(rows)


# -- creating the Payroll Entry -----------------------------------------------


@frappe.whitelist()
def make_payroll_entry(source_name: str, target_doc=None):
	"""Map a Payroll Preview onto a NEW DRAFT Payroll Entry.

	Refuses while any employee still carries a blocking issue. Never submits and never
	inserts: the mapped document is returned for the client to open and save.
	"""
	if not isinstance(source_name, str) or not source_name.strip():
		frappe.throw(_("Invalid Payroll Preview reference."))

	frappe.has_permission("Payroll Preview", ptype="read", doc=source_name, throw=True)
	frappe.has_permission("Payroll Entry", ptype="create", throw=True)

	preview = frappe.get_doc("Payroll Preview", source_name)

	if not preview.last_refreshed_on:
		# The employee rows are cleared whenever the scope changes, so an unrefreshed
		# preview has never been checked against the source documents at all.
		frappe.throw(
			_("This preview has not been refreshed. Click Refresh Allocations first."),
			title=_("Nothing to Process"),
		)

	if not preview.employees:
		frappe.throw(
			_("This preview has no employees. Refresh the allocations first."),
			title=_("Nothing to Process"),
		)

	setup_gaps = preview._get_company_setup_gaps()
	if setup_gaps:
		# Without this the user gets a bare "payroll_payable_account is mandatory" on a form
		# they cannot save, or a FiscalYearError at submit, with nothing naming the cause.
		frappe.throw(
			"<ul>" + "".join(f"<li>{message}</li>" for message in setup_gaps) + "</ul>",
			title=_("Company Payroll Setup Incomplete"),
		)

	blocked = [row for row in preview.employees if cint(row.has_issues)]
	if blocked:
		lines = []
		for row in blocked[:20]:
			lines.append(
				"<li><b>{0}</b> ({1}): {2}</li>".format(
					escape_html(cstr(row.employee_name)),
					escape_html(cstr(row.employee)),
					escape_html(cstr(row.blocking_issues).replace("\n", "; ")),
				)
			)

		message = _("{0} employee(s) still have blocking issues:").format(len(blocked))
		message += "<br><br><ul>" + "".join(lines) + "</ul>"
		if len(blocked) > 20:
			message += _("...and {0} more.").format(len(blocked) - 20)

		frappe.throw(message, title=_("Blocking Issues"))

	def set_missing_values(source, target):
		company_defaults = (
			frappe.db.get_value(
				"Company",
				source.company,
				["default_currency", "default_payroll_payable_account", "cost_center"],
				as_dict=True,
			)
			or frappe._dict()
		)

		target.posting_date = source.end_date
		target.currency = source.currency or company_defaults.default_currency
		target.exchange_rate = 1
		target.payroll_payable_account = company_defaults.default_payroll_payable_account
		target.cost_center = company_defaults.cost_center
		target.number_of_employees = len(target.employees)

	return get_mapped_doc(
		"Payroll Preview",
		source_name,
		{
			"Payroll Preview": {
				"doctype": "Payroll Entry",
				"field_map": {"employee_grade": "grade"},
				# Every amount stays behind. Payroll Entry recomputes from the Salary
				# Structure; nothing this preview read may be carried into it as a figure.
				"field_no_map": [
					"naming_series",
					"total_base",
					"total_earnings",
					"total_deductions",
					"net_estimate",
					"number_of_employees",
					"employees_with_issues",
					"last_refreshed_on",
				],
			},
			"Payroll Preview Employee": {
				"doctype": "Payroll Employee Detail",
				"field_map": {
					"employee": "employee",
					"employee_name": "employee_name",
					"department": "department",
					"designation": "designation",
				},
				# `Payroll Employee Detail` carries employee / employee_name / department /
				# designation / is_salary_withheld and no amounts at all, so these are
				# named to stop a future field of the same name from ever picking one up.
				"field_no_map": [
					"base",
					"earnings",
					"deductions",
					"net_estimate",
					"lwp_days",
					"absent_days",
					"unmarked_days",
					"has_issues",
					"blocking_issues",
					"advisory_notes",
					"branch",
				],
			},
		},
		target_doc,
		set_missing_values,
	)
