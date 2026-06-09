import frappe
from frappe import _
from frappe.model.document import Document


class HiringRequisition(Document):
	def validate(self):
		if not self.status:
			self.status = "Draft"

		if not self.approval_status:
			self.approval_status = "Pending"

		if (self.open_positions or 0) <= 0:
			frappe.throw(_("Open positions must be greater than zero"))

		if self.approval_status == "Approved" and self.status == "Draft":
			self.status = "Open"
