import frappe
from frappe.model.document import Document
from frappe.utils import flt


class SalaryAdjustment(Document):
	APPROVED_STATUSES = {"Approved", "Implemented"}

	def validate(self):
		self.current_basic_salary = flt(self.current_basic_salary)
		self.proposed_basic_salary = flt(self.proposed_basic_salary)

		if not self.status:
			self.status = "Draft"

		if self.proposed_basic_salary and self.current_basic_salary < 0:
			frappe.throw("Current basic salary cannot be negative.")

		if self.proposed_basic_salary and self.proposed_basic_salary < 0:
			frappe.throw("Proposed basic salary cannot be negative.")

		self.adjustment_amount = round(self.proposed_basic_salary - self.current_basic_salary, 2)

		if self.current_basic_salary:
			self.adjustment_percentage = round((self.adjustment_amount / self.current_basic_salary) * 100, 2)
		else:
			self.adjustment_percentage = 0

		if self.status == "Implemented" and not self.implementation_date:
			self.implementation_date = self.effective_date

		if self.appraisal:
			self._sync_review_recommendation()

	def on_update(self):
		if self.appraisal:
			self._sync_review_recommendation()

	def _sync_review_recommendation(self):
		if not frappe.db.exists("Appraisal", self.appraisal):
			return

		frappe.db.set_value(
			"Appraisal",
			self.appraisal,
			{
				"hrsuite_salary_adjustment_recommended": 1,
				"hrsuite_salary_adjustment": self.name,
			},
			update_modified=False,
		)
