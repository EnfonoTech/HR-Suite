import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "policy_document", "label": _("Policy"), "fieldtype": "Link", "options": "HR Policy Document", "width": 180},
		{"fieldname": "policy_title", "label": _("Policy Title"), "fieldtype": "Data", "width": 220},
		{"fieldname": "policy_category", "label": _("Category"), "fieldtype": "Data", "width": 150},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150},
		{"fieldname": "policy_status", "label": _("Policy Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "effective_date", "label": _("Effective Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "review_date", "label": _("Review Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "legal_reference_matrix", "label": _("Legal Reference"), "fieldtype": "Link", "options": "Legal Reference Matrix", "width": 180},
		{"fieldname": "legal_status", "label": _("Reference Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "article_number", "label": _("Article"), "fieldtype": "Data", "width": 100},
		{"fieldname": "risk_level", "label": _("Risk"), "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("pol.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("policy_status"):
		conditions.append("pol.status = %(policy_status)s")
		values["policy_status"] = filters["policy_status"]
	if filters.get("policy_category"):
		conditions.append("pol.policy_category = %(policy_category)s")
		values["policy_category"] = filters["policy_category"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			pol.name AS policy_document,
			pol.policy_title,
			pol.policy_category,
			pol.company,
			pol.status AS policy_status,
			pol.effective_date,
			pol.review_date,
			lrm.name AS legal_reference_matrix,
			lrm.status AS legal_status,
			lrm.article_number,
			lrm.risk_level
		FROM `tabHR Policy Document` pol
		LEFT JOIN `tabLegal Reference Matrix` lrm
			ON lrm.linked_policy = pol.name
		{where}
		ORDER BY pol.modified DESC
		""",
		values,
		as_dict=True,
	)