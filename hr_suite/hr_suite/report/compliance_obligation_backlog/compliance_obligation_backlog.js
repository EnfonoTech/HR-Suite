// Copyright (c) 2026, siva@enfono.com and contributors
// For license information, please see LICENSE

// The Python side reads priority and status. Leaving the filter list empty made
// both unreachable from the UI.
frappe.query_reports["Compliance Obligation Backlog"] = {
	filters: [
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: "\nP0\nP1\nP2",
		},
		{
			// Raw values: compared server-side to the stored English constant.
			fieldname: "status",
			label: __("Implementation Status"),
			fieldtype: "Select",
			options: "\nImplemented\nPartially Implemented\nGap\nNeeds Legal Scope",
		},
	],
};
