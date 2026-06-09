import frappe
from frappe.model.document import Document


class PromotionTransfer(Document):
	APPROVED_STATUSES = {"Approved", "Implemented"}

	def validate(self):
		if not self.status:
			self.status = "Draft"

		if self.new_designation and self.current_designation and self.movement_type == "Promotion":
			if self.new_designation == self.current_designation:
				frappe.throw("New designation must differ from current designation for promotions.")

		if self.new_department and self.current_department and self.movement_type == "Department Transfer":
			if self.new_department == self.current_department:
				frappe.throw("New department must differ from current department for transfers.")

		if self.status == "Implemented" and not self.implementation_date:
			self.implementation_date = self.effective_date

		if self.performance_review:
			self._sync_performance_review()

	def on_update(self):
		if self.performance_review:
			self._sync_performance_review()

	def _sync_performance_review(self):
		if not frappe.db.exists("Performance Review", self.performance_review):
			return

		frappe.db.set_value(
			"Performance Review",
			self.performance_review,
			{
				"promotion_recommended": 1,
				"promotion_transfer": self.name,
			},
			update_modified=False,
		)
