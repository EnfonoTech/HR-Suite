// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Nitaqat Compliance Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
		},
		{
			// Raw values: compared server-side to the stored English value.
			fieldname: "compliance_status",
			label: __("Compliance Status"),
			fieldtype: "Select",
			options: "\nCompliant\nNon-Compliant\nAt Risk",
		},
	],
};
