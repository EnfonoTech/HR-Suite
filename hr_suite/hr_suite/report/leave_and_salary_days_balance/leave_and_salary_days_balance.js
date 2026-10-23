frappe.query_reports["Leave and Salary Days Balance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "ledger_only", label: __("Ledger Engine Only"), fieldtype: "Check", default: 0 },
	],
};
