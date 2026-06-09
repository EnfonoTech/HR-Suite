# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document


class HRLetterTemplate(Document):
	pass


@frappe.whitelist()
def get_rendered_terms(template_name, doc):
	"""Render the template terms with the HR Letter document context."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	template_doc = frappe.get_doc("HR Letter Template", template_name)
	terms = None

	if template_doc.terms:
		terms = frappe.render_template(template_doc.terms, doc)

	return {"template": template_doc.as_dict(), "terms": terms}
