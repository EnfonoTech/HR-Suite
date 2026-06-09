import frappe
from frappe.model.document import Document


class ExitInterview(Document):
	COMPLETED_STATUSES = {"Completed", "Closed"}

	def validate(self):
		if not self.status:
			self.status = "Scheduled"

		if self.exit_clearance:
			clearance = frappe.db.get_value(
				"Exit Clearance",
				self.exit_clearance,
				["employee", "termination_notice"],
				as_dict=True,
			)
			if clearance and clearance.employee and clearance.employee != self.employee:
				frappe.throw("Selected Exit Clearance belongs to a different employee.")

			if clearance and clearance.termination_notice and not self.termination_notice:
				self.termination_notice = clearance.termination_notice

	def on_update(self):
		self._sync_exit_clearance_completion_flag()

	def on_trash(self):
		self._sync_exit_clearance_completion_flag(force_incomplete=True)

	def _sync_exit_clearance_completion_flag(self, force_incomplete=False):
		if not self.exit_clearance or not frappe.db.exists("Exit Clearance", self.exit_clearance):
			return

		is_completed = 0 if force_incomplete else int(self.status in self.COMPLETED_STATUSES)
		frappe.db.set_value(
			"Exit Clearance",
			self.exit_clearance,
			"exit_interview_completed",
			is_completed,
			update_modified=False,
		)
