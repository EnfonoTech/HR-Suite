import frappe
from frappe import _
from frappe.model.document import Document


class SaudiShiftAssignmentTool(Document):
	pass


@frappe.whitelist()
def create_assignments(shift_type, start_date, end_date=None, employees=None, status="Active"):
	if isinstance(employees, str):
		import json

		employees = json.loads(employees)

	if not employees:
		frappe.throw(_("Select at least one employee."))

	created = []
	for employee in employees:
		doc = frappe.get_doc(
			{
				"doctype": "Saudi Shift Assignment",
				"employee": employee,
				"shift_type": shift_type,
				"status": status or "Active",
				"start_date": start_date,
				"end_date": end_date,
			}
		)
		doc.insert(ignore_permissions=False)
		doc.submit()
		created.append(doc.name)

	return {"created": created, "count": len(created)}
