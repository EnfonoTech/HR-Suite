// Copyright (c) 2026, siva@enfono.com and contributors
// For license information, please see LICENSE

// The Python side reads implementation_status and coverage_area. Leaving the filter
// list empty made both unreachable from the UI.
frappe.query_reports["Labor Coverage Matrix"] = {
	filters: [
		{
			// Raw values: compared server-side to the stored English constant.
			fieldname: "implementation_status",
			label: __("Implementation Status"),
			fieldtype: "Select",
			options: "\nImplemented\nPartial\nGap",
		},
		{
			fieldname: "coverage_area",
			label: __("Coverage Area"),
			fieldtype: "Select",
			options: [
				"",
				"Employment",
				"Payroll & Benefits",
				"Leave Management",
				"Compliance",
				"Work Regulations",
				"Official Records",
				"Government Filings",
				"Document Custody",
				"Saudization & Inclusion",
				"Exit",
				"Alternative Work",
				"Working Time",
				"Safety",
				"Contract Evidence",
				"Recruitment Providers",
				"Special Categories",
				"Government Relations",
				"Training",
			].join("\n"),
		},
	],
};
