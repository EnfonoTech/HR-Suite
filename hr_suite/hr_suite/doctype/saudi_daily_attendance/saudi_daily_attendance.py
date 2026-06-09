import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, get_datetime

from hr_suite.hr_suite.attendance_policy import calculate_attendance_variance


class SaudiDailyAttendance(Document):

	def validate(self):
		self._calculate_working_hours()
		self._calculate_schedule_flags()

	def _calculate_working_hours(self):
		if self.in_time and self.out_time:
			self.working_hours = round(
				time_diff_in_hours(get_datetime(self.out_time), get_datetime(self.in_time)), 2
			)

	def _calculate_schedule_flags(self):
		if not self.in_time:
			return

		if self.late_minutes in (None, ""):
			in_variance = calculate_attendance_variance(
				"IN",
				get_datetime(self.in_time),
				{
					"expected_start": get_datetime(self.expected_start_time) if self.expected_start_time else None,
					"late_after": get_datetime(self.expected_start_time) if self.expected_start_time else None,
				},
			)
			self.late_entry = in_variance["late_entry"]
			self.late_minutes = in_variance["late_minutes"]

		if self.out_time and self.early_exit_minutes in (None, ""):
			out_variance = calculate_attendance_variance(
				"OUT",
				get_datetime(self.out_time),
				{
					"expected_end": get_datetime(self.expected_end_time) if self.expected_end_time else None,
					"early_before": get_datetime(self.expected_end_time) if self.expected_end_time else None,
				},
			)
			self.early_exit = out_variance["early_exit"]
			self.early_exit_minutes = out_variance["early_exit_minutes"]
