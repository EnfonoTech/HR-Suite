// HR Suite — Pre-Payroll Allocation Register

frappe.query_reports["Pre-Payroll Allocation Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
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
			fieldname: "entry_type",
			label: __("Entry Type"),
			// Raw values: the selected string is sent to the server and compared to the
			// stored English value, so these must NOT be translated.
			fieldtype: "Select",
			options: "\nEarning\nDeduction\nInformation",
		},
		{
			fieldname: "payroll_preview",
			label: __("Payroll Preview"),
			fieldtype: "Link",
			options: "Payroll Preview",
			get_query() {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "entry_type" && data) {
			const colours = { Earning: "green", Deduction: "orange", Information: "blue" };
			const colour = colours[data.entry_type];
			if (colour) value = `<span class="indicator ${colour}">${value}</span>`;
		}

		return value;
	},
};
