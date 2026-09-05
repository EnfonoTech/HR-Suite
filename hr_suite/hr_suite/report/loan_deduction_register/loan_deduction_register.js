// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Loan Deduction Register"] = {
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
			fieldname: "from_date",
			label: __("Deducted From"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("Deducted To"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
		},
	],
};
