import frappe
from frappe import _
from frappe.utils import getdate, today


LEGAL_STATUS_TOKENS = ("Legal Review", "Legal Review")


def execute(filters=None):
	filters = filters or {}
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_report_summary(data)


def get_columns():
	return [
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 80},
		{"fieldname": "doctype", "label": _("Document Type"), "fieldtype": "Link", "options": "DocType", "width": 190},
		{"fieldname": "document_name", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "doctype", "width": 210},
		{"fieldname": "record_title", "label": _("Title"), "fieldtype": "Data", "width": 220},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "legal_reference", "label": _("Legal Reference"), "fieldtype": "Data", "width": 190},
		{"fieldname": "reason", "label": _("Review Reason"), "fieldtype": "Small Text", "width": 320},
		{"fieldname": "next_action", "label": _("Next Action"), "fieldtype": "Small Text", "width": 320},
	]


def get_data(filters):
	rows = []
	rows.extend(get_work_regulation_rows())
	rows.extend(get_final_settlement_rows())
	rows.extend(get_eosb_rows())
	rows.extend(get_disciplinary_catalog_rows())
	rows.extend(get_disciplinary_procedure_rows())
	rows.extend(get_document_custody_rows())
	rows.extend(get_holiday_overlap_rows())

	if filters.get("priority"):
		rows = [row for row in rows if row["priority"] == filters["priority"]]
	if filters.get("doctype_filter"):
		rows = [row for row in rows if row["doctype"] == filters["doctype_filter"]]

	rows.sort(key=_sort_key)
	return rows


def get_work_regulation_rows():
	doctype = "Work Regulation"
	if not _doctype_exists(doctype):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("regulation_title"),
			status=record.get("status"),
			due_date=record.get("next_review_date"),
			priority="P0",
			legal_reference=record.get("legal_reference") or _("Labor Law Art.12-13; Executive Reg. Art.3-4"),
			reason=_("Work regulation is explicitly under legal review before approval or publication."),
			next_action=_("Attach legal/ministry approval evidence and move the regulation to Approved or Published."),
		)
		for record in _get_records(
			doctype,
			["name", "regulation_title", "status", "next_review_date", "legal_reference", "modified"],
			filters={"status": "Under Legal Review"},
		)
	]


def get_final_settlement_rows():
	doctype = "Final Settlement SLA"
	if not _doctype_exists(doctype):
		return []

	records = _get_records(
		doctype,
		["name", "employee_name", "status", "settlement_due_date", "risk_level", "legal_review_required", "notes", "modified"],
		or_filters=_legal_review_or_filters(doctype, "status"),
	)
	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("employee_name"),
			status=record.get("status"),
			due_date=record.get("settlement_due_date"),
			priority="P0",
			legal_reference=_("Labor Law Art.75-76, Art.84"),
			reason=_("Final settlement or EOSB wage basis is marked for legal review."),
			next_action=_("Confirm settlement deadline, document return, wage basis, and legal approval before closure."),
		)
		for record in records
	]


def get_eosb_rows():
	doctype = "End of Service Benefit"
	if not _doctype_exists(doctype) or not _has_field(doctype, "legal_review_required"):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("employee_name"),
			status=record.get("payment_status"),
			due_date=record.get("termination_date"),
			priority="P0",
			legal_reference=_("Labor Law Art.84"),
			reason=_("EOSB calculation is flagged for manual legal review of wage basis."),
			next_action=_("Validate whether the calculation should use basic salary, total contract wage, or a documented exception."),
		)
		for record in _get_records(
			doctype,
			["name", "employee_name", "payment_status", "termination_date", "legal_review_required", "legal_review_notes", "modified"],
			filters={"legal_review_required": 1},
		)
	]


def get_disciplinary_catalog_rows():
	doctype = "Disciplinary Violation Catalog"
	if not _doctype_exists(doctype):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("violation_name"),
			status=record.get("status"),
			due_date=None,
			priority="P1",
			legal_reference=record.get("legal_reference") or _("Annex 1 - Unified Work Regulation Violation Table"),
			reason=_("Violation row can lead to termination or has been marked as needing legal review."),
			next_action=_("Confirm the penalty sequence and termination preconditions before using it in an employee case."),
		)
		for record in _get_records(
			doctype,
			["name", "violation_name", "status", "requires_termination_review", "legal_reference", "modified"],
			or_filters=_legal_review_or_filters(doctype, "status", "requires_termination_review"),
		)
	]


def get_disciplinary_procedure_rows():
	doctype = "Disciplinary Procedure"
	if not _doctype_exists(doctype) or not _has_field(doctype, "catalog_requires_review"):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("employee_name"),
			status=record.get("status"),
			due_date=record.get("incident_date"),
			priority="P0",
			legal_reference=record.get("catalog_legal_reference") or record.get("legal_reference_matrix"),
			reason=_("Applied disciplinary catalog row requires legal review."),
			next_action=_("Review investigation evidence, employee response, recurrence number, and penalty before decision."),
		)
		for record in _get_records(
			doctype,
			["name", "employee_name", "status", "incident_date", "catalog_requires_review", "catalog_legal_reference", "legal_reference_matrix", "modified"],
			filters={"catalog_requires_review": 1},
		)
	]


def get_document_custody_rows():
	doctype = "Employee Document Custody Log"
	if not _doctype_exists(doctype):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("employee_name"),
			status=record.get("custody_status"),
			due_date=record.get("return_due_date"),
			priority="P0",
			legal_reference=record.get("legal_reference") or _("Executive Regulations Art.6"),
			reason=_("Original worker document custody has an exception under legal review."),
			next_action=_("Return the original document or attach documented worker/legal approval for the temporary exception."),
		)
		for record in _get_records(
			doctype,
			["name", "employee_name", "custody_status", "return_due_date", "legal_reference", "modified"],
			filters={"custody_status": "Exception Under Legal Review"},
		)
	]


def get_holiday_overlap_rows():
	doctype = "Holiday Leave Overlap Rule"
	if not _doctype_exists(doctype):
		return []

	return [
		_review_row(
			doctype=doctype,
			record=record,
			title=record.get("holiday_name"),
			status=record.get("status"),
			due_date=record.get("holiday_date"),
			priority="P1",
			legal_reference=record.get("legal_reference"),
			reason=_("Holiday or leave overlap requires a legal decision before applying compensation or extension."),
			next_action=_("Confirm the correct leave/holiday treatment and close the overlap rule with evidence."),
		)
		for record in _get_records(
			doctype,
			["name", "holiday_name", "status", "holiday_date", "required_action", "legal_reference", "modified"],
			or_filters=_holiday_overlap_filters(doctype),
		)
	]


def _review_row(doctype, record, title, status, due_date, priority, legal_reference, reason, next_action):
	return {
		"priority": priority,
		"doctype": doctype,
		"document_name": record.get("name"),
		"record_title": title or record.get("name"),
		"status": status,
		"due_date": due_date,
		"legal_reference": legal_reference,
		"reason": reason,
		"next_action": next_action,
	}


def _get_records(doctype, fields, filters=None, or_filters=None):
	fields = [field for field in fields if _has_field(doctype, field)]
	if "name" not in fields:
		fields.insert(0, "name")

	return frappe.get_all(
		doctype,
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		order_by="modified desc",
		limit_page_length=500,
	)


def _legal_review_or_filters(doctype, status_field=None, flag_field=None):
	or_filters = []
	if status_field and _has_field(doctype, status_field):
		or_filters.extend([[status_field, "like", f"%{token}%"] for token in LEGAL_STATUS_TOKENS])
	if flag_field and _has_field(doctype, flag_field):
		or_filters.append([flag_field, "=", 1])
	if _has_field(doctype, "legal_review_required"):
		or_filters.append(["legal_review_required", "=", 1])
	return or_filters


def _holiday_overlap_filters(doctype):
	or_filters = []
	for fieldname in ("status", "required_action"):
		if _has_field(doctype, fieldname):
			or_filters.extend([[fieldname, "like", f"%{token}%"] for token in LEGAL_STATUS_TOKENS])
	return or_filters


def _sort_key(row):
	priority_order = {"P0": 0, "P1": 1, "P2": 2}
	due_date = row.get("due_date")
	due_value = getdate(due_date) if due_date else getdate("2999-12-31")
	overdue_rank = 0 if due_date and due_value < getdate(today()) else 1
	return (priority_order.get(row.get("priority"), 99), overdue_rank, due_value, row.get("doctype"), row.get("document_name"))


def _doctype_exists(doctype):
	return bool(frappe.db.exists("DocType", doctype))


def _has_field(doctype, fieldname):
	if fieldname in {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}:
		return True
	return bool(frappe.get_meta(doctype).get_field(fieldname))


def get_chart(data):
	counts = {}
	for row in data:
		counts[row["priority"]] = counts.get(row["priority"], 0) + 1
	return {
		"data": {
			"labels": list(counts),
			"datasets": [{"name": _("Legal Review Items"), "values": list(counts.values())}],
		},
		"type": "bar",
	}


def get_report_summary(data):
	p0 = sum(1 for row in data if row["priority"] == "P0")
	p1 = sum(1 for row in data if row["priority"] == "P1")
	p2 = sum(1 for row in data if row["priority"] == "P2")
	overdue = sum(1 for row in data if row.get("due_date") and getdate(row["due_date"]) < getdate(today()))
	return [
		{"label": _("P0 Legal Reviews"), "value": p0, "indicator": "Red", "datatype": "Int"},
		{"label": _("P1 Legal Reviews"), "value": p1, "indicator": "Orange", "datatype": "Int"},
		{"label": _("P2 Legal Reviews"), "value": p2, "indicator": "Blue", "datatype": "Int"},
		{"label": _("Overdue"), "value": overdue, "indicator": "Red", "datatype": "Int"},
	]
