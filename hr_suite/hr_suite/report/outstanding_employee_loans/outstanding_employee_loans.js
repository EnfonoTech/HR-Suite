// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Outstanding Employee Loans"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			get_query() {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
		{
			// Raw values: compared server-side to the stored English value.
			fieldname: "status",
			label: __("Loan Status"),
			fieldtype: "Select",
			options: "\nDraft\nActive\nClosed\nCancelled",
		},
		{
			fieldname: "include_settled",
			label: __("Include Fully Repaid Loans"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
