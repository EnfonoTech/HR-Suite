import frappe
from frappe.model.document import Document


class ExitClearance(Document):
	CHECKLIST_FIELDS = (
		"access_revoked",
		"assets_returned",
		"final_attendance_verified",
		"payroll_closed",
		"eosb_completed",
		"annual_leave_disbursement_completed",
		"exit_interview_completed",
		"handover_completed",
	)

	def validate(self):
		if self.exit_interview and not self.exit_interview_completed:
			self.exit_interview_completed = int(
				frappe.db.get_value("Exit Interview", self.exit_interview, "status")
				in {"Completed", "Closed"}
			)

		completed = sum(1 for fieldname in self.CHECKLIST_FIELDS if self.get(fieldname))
		self.clearance_percentage = round((completed / len(self.CHECKLIST_FIELDS)) * 100, 2)

		if not self.status:
			self.status = "Draft"

		if self.clearance_percentage >= 100:
			self.status = "Cleared"
		elif self.clearance_percentage > 0 and self.status == "Draft":
			self.status = "In Progress"
