from statistics import mean

import frappe
from frappe.model.document import Document


class PerformanceReview(Document):
	RATING_FIELDS = ("attendance_rating", "compliance_rating", "productivity_rating", "collaboration_rating")

	def validate(self):
		ratings = [float(self.get(fieldname) or 0) for fieldname in self.RATING_FIELDS if self.get(fieldname) is not None]
		if ratings:
			self.overall_rating = round(mean(ratings), 2)

		if self.salary_adjustment and not self.salary_adjustment_recommended:
			self.salary_adjustment_recommended = int(
				frappe.db.exists("Salary Adjustment", self.salary_adjustment)
			)

		if self.promotion_transfer and not self.promotion_recommended:
			self.promotion_recommended = int(
				frappe.db.exists("Promotion Transfer", self.promotion_transfer)
			)

		if not self.status:
			self.status = "Draft"

		if self.overall_rating and self.status == "Draft":
			self.status = "Completed"
