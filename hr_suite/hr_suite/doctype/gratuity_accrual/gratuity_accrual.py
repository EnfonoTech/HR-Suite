# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""One row per employee per gratuity event: the Opening balance, each month's provision, the finalisation.

HR enters only Opening rows (what Finance booked by hand before the provision start date). Monthly and
Finalisation rows are written by HR Suite with their Journal Entry and cannot be made or changed by hand.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class GratuityAccrual(Document):
	def validate(self):
		if self.flags.from_hr_suite:
			return
		if self.source != "Opening":
			frappe.throw(
				_("Only Opening rows are entered by hand. Monthly rows come from posting the gratuity provision, and "
				  "Finalisation rows from the Gratuity Finalisation."),
				title=_("Opening Rows Only"),
			)
		other = frappe.db.exists("Gratuity Accrual", {"employee": self.employee, "source": "Opening", "name": ["!=", self.name]})
		if other:
			frappe.throw(_("{0} already has an Opening row ({1}). Change that one.").format(self.employee, other), title=_("One Opening Per Employee"))
		if self.journal_entry or self.gratuity_finalisation:
			frappe.throw(_("An Opening row posts nothing and links no entry."))

	def on_trash(self):
		if self.source != "Opening" and not self.flags.from_hr_suite:
			frappe.throw(_("Cancel the Journal Entry or the Gratuity Finalisation instead: this row goes with it."))
