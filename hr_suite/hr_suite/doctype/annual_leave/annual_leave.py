import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, nowdate

from hr_suite.hr_suite.utils import get_annual_leave_balance


class AnnualLeave(Document):
	def validate(self):
		self._set_status()
		self._calculate_days()
		self._calculate_balance()

	def on_submit(self):
		self.db_set("status", "Approved")
		self.db_set("approved_by", frappe.session.user)
		self.db_set("approval_date", nowdate())

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def _set_status(self):
		if not self.status:
			self.status = "Draft"

	def _calculate_days(self):
		if not self.leave_start_date or not self.leave_end_date:
			return

		start_date = getdate(self.leave_start_date)
		end_date = getdate(self.leave_end_date)
		if end_date < start_date:
			frappe.throw(_("Leave end date must be on or after the start date."))
		if start_date.year != end_date.year:
			frappe.throw(
				_("Annual leave request must stay within one calendar year."),
				title=_("Invalid Leave Period"),
			)

		if self.half_day and start_date != end_date:
			frappe.throw(_("Half-day leave is only available when the leave start and end date are the same day."))

		self.total_leave_days = 0.5 if self.half_day else flt(date_diff(end_date, start_date) + 1)

	def _calculate_balance(self):
		if not self.employee or not self.leave_start_date:
			return

		joining_date = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if joining_date and getdate(self.leave_start_date) < getdate(joining_date):
			frappe.throw(
				_("Annual leave cannot start before the employee joining date."),
				title=_("Invalid Leave Date"),
			)

		balance = get_annual_leave_balance(self.employee, self.leave_start_date, exclude_name=self.name)
		self.leave_balance_before = balance["balance"]
		self.leave_balance_after = flt(balance["balance"]) - flt(self.total_leave_days)

		if self.leave_balance_after < 0:
			frappe.throw(_("Insufficient annual leave balance for this request."), title=_("Insufficient Balance"))
