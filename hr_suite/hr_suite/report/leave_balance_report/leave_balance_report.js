// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Leave Balance Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
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
			// Real Leave Type link. The Select that used to sit here offered a single
			// hardcoded "Annual Leave" option that the server never read.
			fieldname: "leave_type",
			label: __("Leave Type (Leave Ledger)"),
			fieldtype: "Link",
			options: "Leave Type",
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
		},
		{
			fieldname: "include_inactive",
			label: __("Include Inactive Employees"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
