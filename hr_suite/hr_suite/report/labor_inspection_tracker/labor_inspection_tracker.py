import frappe
from frappe import _


OPEN_VIOLATION_STATUSES = {
	"Open",
	"Under Review",
	"Corrective Action In Progress",
}


def execute(filters=None):
	data = get_data(filters or {})
	return get_columns(), data, None, get_chart(data), get_report_summary(data)


def get_columns():
	return [
		{"fieldname": "labor_inspection", "label": _("Inspection"), "fieldtype": "Link", "options": "Labor Inspection", "width": 160},
		{"fieldname": "inspection_date", "label": _("Inspection Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "inspection_authority", "label": _("Authority"), "fieldtype": "Data", "width": 180},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
		{"fieldname": "inspection_status", "label": _("Inspection Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "violation_category", "label": _("Violation Category"), "fieldtype": "Data", "width": 170},
		{"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 110},
		{"fieldname": "violation_status", "label": _("Violation Status"), "fieldtype": "Data", "width": 160},
		{"fieldname": "correction_due_date", "label": _("Correction Due Date"), "fieldtype": "Date", "width": 115},
		{"fieldname": "fine_amount", "label": _("Fine Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "action_log", "label": _("Compliance Action"), "fieldtype": "Link", "options": "HR Compliance Action Log", "width": 180},
		{"fieldname": "document_status", "label": _("Doc Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	# Labor Inspection is submittable: a cancelled inspection is not a live finding.
	conditions = ["li.docstatus < 2"]
	values = {}

	if filters.get("company"):
		conditions.append("li.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("inspection_authority"):
		conditions.append("li.inspection_authority = %(inspection_authority)s")
		values["inspection_authority"] = filters["inspection_authority"]
	if filters.get("inspection_status"):
		conditions.append("li.status = %(inspection_status)s")
		values["inspection_status"] = filters["inspection_status"]
	if filters.get("violation_status"):
		conditions.append("liv.status = %(violation_status)s")
		values["violation_status"] = filters["violation_status"]
	if filters.get("severity"):
		conditions.append("liv.severity = %(severity)s")
		values["severity"] = filters["severity"]
	if filters.get("from_date"):
		conditions.append("li.inspection_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("li.inspection_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			li.docstatus,
			li.name AS labor_inspection,
			li.inspection_date,
			li.inspection_authority,
			li.company,
			li.status AS inspection_status,
			liv.violation_category,
			liv.severity,
			liv.status AS violation_status,
			liv.correction_due_date,
			liv.fine_amount,
			liv.action_log,
			comp.default_currency AS currency
		FROM `tabLabor Inspection` li
		LEFT JOIN `tabCompany` comp ON comp.name = li.company
		LEFT JOIN `tabLabor Inspection Violation` liv
			ON liv.parent = li.name AND liv.parenttype = 'Labor Inspection' AND liv.parentfield = 'violations'
		{where}
		ORDER BY li.inspection_date DESC, liv.idx ASC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		# Drafts are kept on purpose, but a draft inspection carries fine amounts and
		# reads exactly like a submitted one without this column. Raw English values,
		# not translated: a UI filter would compare them server-side.
		row["document_status"] = "Draft" if not row.pop("docstatus", 0) else "Submitted"

	return rows


def get_chart(data):
	counts = {}
	for row in data:
		status = row.get("violation_status") or _("Unspecified")
		counts[status] = counts.get(status, 0) + 1

	labels = list(counts.keys())
	values = [counts[label] for label in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Violations"), "values": values}],
		},
		"type": "bar",
		"colors": ["#C92A2A", "#F08C00", "#2F9E44", "#1C7ED6", "#495057", "#868E96"],
	}


def get_report_summary(data):
	inspection_count = len({row["labor_inspection"] for row in data if row.get("labor_inspection")})
	open_violations = sum(1 for row in data if row.get("violation_status") in OPEN_VIOLATION_STATUSES)
	total_fines = sum(row.get("fine_amount") or 0 for row in data)

	return [
		{
			"label": _("Total Inspections"),
			"value": inspection_count,
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": _("Open Violations"),
			"value": open_violations,
			"indicator": "Red",
			"datatype": "Int",
		},
		{
			"label": _("Total Fines"),
			"value": total_fines,
			"indicator": "Orange",
			"datatype": "Currency",
		},
	]