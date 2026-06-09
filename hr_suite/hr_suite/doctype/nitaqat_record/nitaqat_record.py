import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from hr_suite.hr_suite.utils import get_contract_nationality_lookup, is_saudi_nationality


# Nitaqat band thresholds — approximate general industry values.
# These should be configured per sector in Hr Suite Settings.
NITAQAT_BANDS = {
	"Platinum":     (40, None),
	"High Green":   (30, 40),
	"Medium Green": (20, 30),
	"Low Green":    (10, 20),
	"Yellow":       (4, 10),
	"Red":          (0, 4),
}


class NitaqatRecord(Document):

	def validate(self):
		self._count_employees()
		self._calculate_saudization()
		self._classify_nitaqat()

	def _count_employees(self):
		"""Calculate the count of Saudi and non-Saudi employees from the Employee table."""
		all_employees = frappe.get_all(
			"Employee",
			filters={"company": self.company, "status": "Active"},
			fields=_get_employee_fetch_fields(),
		)
		contract_nationalities = get_contract_nationality_lookup([employee.name for employee in all_employees])

		saudi = sum(
			1 for e in all_employees
			if is_saudi_nationality(e.get("nationality") or contract_nationalities.get(e.name))
		)

		self.total_employees = len(all_employees)
		self.saudi_employees = saudi
		self.non_saudi_employees = self.total_employees - saudi

	def _calculate_saudization(self):
		if self.total_employees > 0:
			self.saudization_percentage = round(
				(self.saudi_employees / self.total_employees) * 100, 2
			)
		else:
			self.saudization_percentage = 0.0

	def _classify_nitaqat(self):
		"""Classify the Nitaqat band based on the Saudization ratio."""
		pct = flt(self.saudization_percentage)
		required = flt(self.required_saudization_percentage) or 0.0

		category = "Red"
		color = "Red"

		if pct >= 40:
			category, color = "Platinum", "Platinum"
		elif pct >= 30:
			category, color = "High Green", "Green"
		elif pct >= 20:
			category, color = "Medium Green", "Green"
		elif pct >= 10:
			category, color = "Low Green", "Green"
		elif pct >= 4:
			category, color = "Yellow", "Yellow"
		else:
			category, color = "Red", "Red"

		self.nitaqat_category = category
		self.nitaqat_color = color


		if required and pct < required:
			self.compliance_status = "Non-Compliant"
		elif required and pct < required * 1.1:
			self.compliance_status = "At Risk"
		else:
			self.compliance_status = "Compliant"


		next_band_threshold = self._next_band_threshold(pct)
		self.gap_to_next_band = round(max(0, next_band_threshold - pct), 2) if next_band_threshold else 0.0

	def _next_band_threshold(self, pct):
		thresholds = sorted([40, 30, 20, 10, 4])
		for t in thresholds:
			if pct < t:
				return t
		return None


def _get_employee_fetch_fields():
	fields = ["name"]
	if frappe.get_meta("Employee").has_field("nationality"):
		fields.append("nationality")
	return fields
