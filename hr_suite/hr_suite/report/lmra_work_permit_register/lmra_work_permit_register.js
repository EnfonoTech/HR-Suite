// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["LMRA Work Permit Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			// Raw ISO-2 codes: the same option list as Employee.work_country and
			// Country Employment Contract.work_country, compared server-side.
			fieldname: "work_country",
			label: __("Work Country"),
			fieldtype: "Select",
			options: "\nSA\nAE\nBH\nIN\nOM",
			default: "BH",
			reqd: 1,
		},
		{
			fieldname: "expiring_within_days",
			label: __("Expiring Within (Days)"),
			fieldtype: "Int",
			default: 0,
			description: __("0 uses the country's own window from Country Config."),
		},
		{
			fieldname: "permit_status",
			label: __("Permit Status"),
			fieldtype: "Select",
			options: "\nActive\nExpiring Soon\nExpired\nNo Permit Record",
		},
		{
			fieldname: "employee_status",
			label: __("Employee Status"),
			fieldtype: "Select",
			options: "Active\nInactive\nSuspended\nLeft\nAll",
			default: "Active",
		},
		{
			fieldname: "show_employees_without_permit",
			label: __("Include employees with no permit record"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "permit_status" && data) {
			const colours = {
				"Expired": "red",
				"No Permit Record": "red",
				"Expiring Soon": "orange",
				"Active": "green",
			};
			const colour = colours[data.permit_status];
			if (colour) value = `<span style="color:var(--text-on-light-${colour}, ${colour});">${value}</span>`;
		}
		if (column.fieldname === "days_to_expiry" && data && data.days_to_expiry !== null && data.days_to_expiry < 0) {
			value = `<span style="color:red;">${value}</span>`;
		}
		return value;
	},
};
