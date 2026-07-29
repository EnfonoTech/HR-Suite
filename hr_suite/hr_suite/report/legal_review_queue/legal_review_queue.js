// Copyright (c) 2026, siva@enfono.com and contributors
// For license information, please see LICENSE

frappe.query_reports["Legal Review Queue"] = {
	filters: [
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: "\nP0\nP1\nP2",
		},
		{
			fieldname: "doctype_filter",
			label: __("Document Type"),
			fieldtype: "Select",
			options: "\nWork Regulation\nFinal Settlement SLA\nEnd of Service Benefit\nDisciplinary Violation Catalog\nDisciplinary Procedure\nEmployee Document Custody Log\nHoliday Leave Overlap Rule",
		},
	],
};
