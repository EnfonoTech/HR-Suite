// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

// Every Select below must list the FULL option set of the underlying field. A
// truncated list silently makes most of the data unreachable through the filter.
frappe.query_reports["Labor Inspection Tracker"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			// Raw values: compared server-side to the stored English value.
			fieldname: "inspection_authority",
			label: __("Authority"),
			fieldtype: "Select",
			options: "\nMinistry of Human Resources\nGOSI\nMunicipality\nCivil Defense\nInternal Audit\nOther",
		},
		{
			fieldname: "inspection_status",
			label: __("Inspection Status"),
			fieldtype: "Select",
			options: "\nDraft\nOpen Findings\nUnder Follow-up\nCorrected\nClosed",
		},
		{
			fieldname: "violation_status",
			label: __("Violation Status"),
			fieldtype: "Select",
			options: "\nOpen\nUnder Review\nCorrective Action In Progress\nCorrected\nWaived\nClosed",
		},
		{
			fieldname: "severity",
			label: __("Severity"),
			fieldtype: "Select",
			options: "\nLow\nMedium\nHigh\nCritical",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
