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

		if self.appraisal:
			self._sync_appraisal()

	def on_update(self):
		if self.appraisal:
			self._sync_appraisal()

	def _sync_appraisal(self):
		if not frappe.db.exists("Appraisal", self.appraisal):
			return

		frappe.db.set_value(
			"Appraisal",
			self.appraisal,
			{
				"hrsuite_promotion_recommended": 1,
				"hrsuite_promotion_transfer": self.name,
			},
			update_modified=False,
		)
