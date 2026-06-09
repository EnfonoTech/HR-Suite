import frappe
from frappe.model.document import Document


class EmployeeOnboarding(Document):
	CHECKLIST_FIELDS = (
		"government_registration_completed",
		"medical_exam_completed",
		"policy_acknowledged",
		"equipment_issued",
		"workstation_ready",
		"training_plan_assigned",
	)

	def validate(self):
		completed = sum(1 for fieldname in self.CHECKLIST_FIELDS if self.get(fieldname))
		self.completion_percentage = round((completed / len(self.CHECKLIST_FIELDS)) * 100, 2)

		if not self.status:
			self.status = "Draft"

		if self.completion_percentage >= 100:
			self.status = "Completed"
		elif self.completion_percentage > 0 and self.status == "Draft":
			self.status = "In Progress"
