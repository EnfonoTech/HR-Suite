# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HRLetter(Document):

	def on_submit(self):
		self.status = "Issued"
		self.db_set("status", "Issued")

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")
