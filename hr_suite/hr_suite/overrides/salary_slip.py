# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Leave days that a Leave Salary Settlement already paid are left out of the Salary Slip.

The settlement pays the leave salary in advance (Journal Entry accrual, HR Payment Advice, Payment Entry).
Annual leave is a paid day to HRMS, so month-end payroll would pay those days a second time. This class takes
them out of the payment days, so the components that depend on payment days scale down exactly as they would
for any other day not paid by payroll. It is not leave without pay, adds no Additional Salary row and no line
on the slip, and changes nothing for an employee without such a settlement.

A slip for the days AFTER the leave is held until the return is confirmed (Record Rejoin on the settlement) or
the employee has attendance after the leave: salary is not paid for days nobody has confirmed were worked.

Settlements made before this design carry their own payroll deductions and are not touched here (they have no
accrual Journal Entry, which is what marks a settlement as using this mechanism).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, formatdate, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

PRESENT_STATUSES = ("Present", "Work From Home", "Half Day")


def settled_leave_ranges(employee, start, end) -> list:
	"""[{"name", "from", "to", "leave_to", "rejoin_date"}] of leave settled in advance that touches [start, end].

	"to" is where payroll stops excluding: the leave's last day, or the day before the employee came back early.
	"""
	rows = frappe.get_all(
		"Leave Salary Settlement",
		filters={
			"employee": employee,
			"docstatus": 1,
			"settlement_type": ["!=", "Final Settlement"],
			"accrual_journal_entry": ["is", "set"],
			"leave_from_date": ["<=", getdate(end)],
			"leave_to_date": [">=", getdate(start)],
		},
		fields=["name", "leave_from_date", "leave_to_date", "rejoin_date"],
	)
	out = []
	for row in rows:
		leave_from, leave_to = getdate(row.leave_from_date), getdate(row.leave_to_date)
		effective_to = leave_to
		if row.rejoin_date and getdate(row.rejoin_date) <= leave_to:
			effective_to = add_days(getdate(row.rejoin_date), -1)
		out.append(
			{"name": row.name, "from": leave_from, "to": effective_to, "leave_to": leave_to, "rejoin_date": row.rejoin_date}
		)
	return out


def count_excluded_days(ranges, start, end, holidays=()) -> int:
	"""Days in [start, end] inside a settled leave and not a holiday that payroll does not count."""
	holidays = {getdate(h) for h in holidays}
	days = 0
	for offset in range(date_diff(getdate(end), getdate(start)) + 1):
		day = add_days(getdate(start), offset)
		if day in holidays:
			continue
		if any(r["from"] <= day <= r["to"] for r in ranges):
			days += 1
	return days


def return_confirmed(employee, settlement: dict) -> bool:
	"""The employee's return after this leave is on record: a rejoin on the settlement, or attendance after it."""
	if settlement.get("rejoin_date"):
		return True
	return bool(
		frappe.db.exists(
			"Attendance",
			{
				"employee": employee,
				"docstatus": 1,
				"status": ["in", list(PRESENT_STATUSES)],
				"attendance_date": [">", settlement["leave_to"]],
			},
		)
	)


class HRSuiteSalarySlip(SalarySlip):
	def validate(self):
		self._hrs_require_confirmed_return()
		super().validate()

	def get_working_days_details(self, lwp=None, for_preview=0):
		super().get_working_days_details(lwp=lwp, for_preview=for_preview)
		if for_preview or not self.employee:
			return

		start = getdate(self.actual_start_date or self.start_date)
		end = getdate(self.actual_end_date or self.end_date)
		ranges = settled_leave_ranges(self.employee, start, end)
		if not ranges:
			return

		holidays = ()
		if not cint(frappe.get_cached_value("Payroll Settings", None, "include_holidays_in_total_working_days")):
			holidays = self.get_holidays_for_employee(start, end)
		settled = count_excluded_days(ranges, start, end, holidays)
		if settled:
			self.payment_days = max(flt(self.payment_days) - settled, 0)

	def _hrs_require_confirmed_return(self):
		if not self.employee or not self.start_date or not self.end_date or self.docstatus == 2:
			return
		start, end = getdate(self.start_date), getdate(self.end_date)
		for settlement in settled_leave_ranges(self.employee, start, end):
			if settlement["to"] >= end:
				continue  # the leave covers the rest of this period: no days after it to pay yet
			if return_confirmed(self.employee, settlement):
				continue
			frappe.throw(
				_("{0} was on annual leave until {1} (settlement {2}). Payroll for the days after it waits until the "
				  "return is confirmed: record it on the settlement (Actions > Record Rejoin) or add the employee's "
				  "attendance, then run payroll again.").format(
					self.employee_name or self.employee, formatdate(settlement["leave_to"]), settlement["name"]
				),
				title=_("Return From Leave Not Confirmed"),
			)
