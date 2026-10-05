import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_first_day, get_last_day, getdate

from hr_suite.hr_suite.utils import get_employee_work_country

# Sources that move the employee's HRMS annual-leave balance. A Settlement row carries leave
# SALARY days only: the leave days themselves are taken through a Leave Application.
HRMS_SOURCES = ("Accrual", "Opening", "Adjustment")


class LeaveAccrualLedger(Document):
	def validate(self):
		self.country = get_employee_work_country(self.employee)
		self._set_period()
		self._guard_duplicates()
		if self.source == "Accrual" and (flt(self.leave_days) < 0 or flt(self.salary_days) < 0):
			frappe.throw(_("An accrual cannot be negative. Record a correction as an Adjustment."))
		if not flt(self.leave_days) and not flt(self.salary_days):
			if self.source != "Accrual":
				frappe.throw(_("Enter leave days, leave-salary days, or both."))

	def _set_period(self):
		if self.source == "Accrual":
			self.period_start = get_first_day(self.period_end)
			self.period_end = get_last_day(self.period_end)
		else:
			self.period_start = self.period_end

	def _guard_duplicates(self):
		others = {"employee": self.employee, "name": ["!=", self.name or ""]}
		if self.source == "Accrual":
			if frappe.db.exists("Leave Accrual Ledger", {**others, "source": "Accrual", "period_start": self.period_start}):
				frappe.throw(
					_("{0} has already accrued leave for the month starting {1}.").format(self.employee, self.period_start)
				)
		elif self.source == "Opening":
			if frappe.db.exists("Leave Accrual Ledger", {**others, "source": "Opening"}):
				frappe.throw(
					_("{0} already has an opening balance. It is imported once; correct it with an Adjustment.").format(
						self.employee
					)
				)
			if frappe.db.exists("Leave Accrual Ledger", {**others, "source": "Accrual"}):
				frappe.throw(
					_("Accrual has already run for {0}, so an opening balance would count those months twice. "
					  "Correct the balance with an Adjustment.").format(self.employee)
				)

	def after_insert(self):
		if self.source not in HRMS_SOURCES or not flt(self.leave_days) or self.flags.skip_hrms_sync:
			return

		from hr_suite.hr_suite.leave_accrual import post_to_hrms
		from hr_suite.hr_suite.policy import get_country_policy

		policy = get_country_policy(self.country) if self.country else None
		leave_type = policy.annual_leave_type if policy else "Annual Leave"
		allocation = post_to_hrms(self.employee, leave_type, self.leave_days, self.period_end)
		if allocation:
			self.db_set("leave_allocation", allocation, update_modified=False)

	def on_trash(self):
		if not self.flags.allow_delete:
			frappe.throw(
				_("A ledger row is never deleted: it has already moved the leave balance. "
				  "Post an Adjustment with the opposite days instead."),
				title=_("Cannot delete"),
			)
