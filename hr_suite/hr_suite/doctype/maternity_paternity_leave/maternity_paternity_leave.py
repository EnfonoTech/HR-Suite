import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt

from hr_suite.hr_suite.utils import get_employee_basic_salary


LEAVE_DAYS = {
	"Maternity": 70,
	"Paternity": 3,
	"Miscarriage after 6 months": 60,
}


class MaternityPaternityLeave(Document):

	def validate(self):
		self._set_entitled_days()
		self._calculate_end_date()
		self._calculate_pay()
		self._validate_certificate()

	def _set_entitled_days(self):
		self.entitled_days = LEAVE_DAYS.get(self.leave_type, 0)
		if not self.entitled_days:
			frappe.throw(
				_("Unknown leave type. Please select a valid type.<br>"
				  "Unknown leave type. Please select a valid type."),
				title=_("Invalid Leave Type"),
			)

	def _calculate_end_date(self):
		if self.leave_start_date and self.entitled_days:
			self.leave_end_date = add_days(self.leave_start_date, self.entitled_days - 1)

	def _calculate_pay(self):
		"""Full pay for all maternity/paternity leave types under Art.151."""
		self.full_pay = 1
		self.pay_note = "Full pay per Saudi Labor Law Art. 151"

		monthly = get_employee_basic_salary(self.employee)
		self.daily_salary = round(monthly / 30, 2)
		self.total_leave_pay = round(self.daily_salary * (self.entitled_days or 0), 2)

	def _validate_certificate(self):
		"""Verify medical certificate is attached on approval."""
		if self.docstatus == 1 and not self.medical_certificate_attached:
			frappe.throw(
				_("Medical certificate must be attached before submitting.<br>"
				  "Medical certificate must be attached before approval."),
				title=_("Certificate Required"),
			)


@frappe.whitelist()
def get_daily_salary(employee):
	"""Return daily salary (monthly_basic / 30) for JS auto-fill."""
	monthly = get_employee_basic_salary(employee)
	return round(monthly / 30, 2)
